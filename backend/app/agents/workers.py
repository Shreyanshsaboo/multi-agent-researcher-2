"""The three research workers: HN scout, web researcher and article reader.

They share one protocol. A worker gets a task from the coordinator, works it
with its own tools in a reasoning loop (searching, reformulating when a search
comes back empty, reading), and ends with a report: a status line, a short
summary, and its findings in a plain line format.

Findings are reported as text rather than through a tool call because nested
tool arguments are where smaller models most often emit malformed JSON, and a
malformed tool call fails the whole agent run. Every finding is still checked
against what the worker's tools actually returned before it is saved.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from agno.agent import Agent

from app.agents.runtime import AgentFailure, run_agent
from app.config import Budget, Settings
from app.events import RunChannel
from app.evidence import EvidenceStore
from app.llm import build_model_chain
from app.schemas import TaskResult, TaskSpec
from app.tools import Finding, ToolContext, make_article_tools, make_hn_tools, make_web_tools

_STATUS_RE = re.compile(r"STATUS\W*\s*(success|partial|failed)", re.IGNORECASE)
_FINDING_RE = re.compile(r"^\W*FINDING\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s)>\]\"'`]+")
_TITLE_RE = re.compile(r"^\W*TITLE\s*:\s*(.+)", re.IGNORECASE)
_POINT_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)")
_REPORT_RE = re.compile(r"^\W*(?:REPORT|SUMMARY)\s*:\s*", re.IGNORECASE)

PROTOCOL = """\
You are the {name} on a six-agent research team. The Coordinator has given you one task;
other agents cover everything else.

{specialty}

HOW TO WORK
- You have {tool_calls} tool calls in total for this task. Plan them and make them together in
  one step (parallel calls), rather than one at a time: every extra step resends everything so
  far and costs the team time. Only if a search returns nothing useful, adapt in one more
  round with reformulated queries (fewer or broader keywords, synonyms, a different time range).
- When your tool calls are used up, or you have enough, write your final answer.
- If a tool errors, try once more in a different way, then report it. Never invent sources.
- Report at most {max_findings} findings; prefer relevant, diverse and recent sources.
- Key points must be specific (figures, dates, names, opinions with who holds them) and must
  come from your tool output, never from memory. Points with figures that are not in the
  retrieved text are rejected.

FINAL ANSWER FORMAT (exactly this, no tables):
STATUS: success | partial | failed
REPORT: 1-3 sentences on what you found, what did not work, and what the Coordinator should
do next.
FINDING: <exact url from your tool output>
TITLE: <short title>
- <key point>
- <key point>
FINDING: <next url>
...
"""


@dataclass(frozen=True)
class WorkerProfile:
    name: str
    specialty: str
    make_tools: Callable[[ToolContext], list]
    tool_call_limit: int


PROFILES: dict[str, WorkerProfile] = {
    "hn_scout": WorkerProfile(
        name="HN Scout",
        specialty=(
            "You find Hacker News stories and read their comment threads to capture what\n"
            "practitioners think. Read the comments of the 1-2 most discussed relevant stories.\n"
            "Report opinions as opinions (\"HN commenters argue ...\"), not as facts.\n"
            "Use get_front_page only when the task is about what is trending right now."
        ),
        make_tools=make_hn_tools,
        tool_call_limit=4,
    ),
    "web_researcher": WorkerProfile(
        name="Web Researcher",
        specialty=(
            "You search the web and the news for facts, official sources and recent developments.\n"
            "Use news_search for anything time-sensitive and web_search for background,\n"
            "documentation and official pages. Prefer primary sources over listicles and SEO pages.\n"
            "Search engines want short keyword queries (3-6 words), not sentences."
        ),
        make_tools=make_web_tools,
        tool_call_limit=3,
    ),
    "article_reader": WorkerProfile(
        name="Article Reader",
        specialty=(
            "You read the full text of the specific pages the Coordinator assigns and extract\n"
            "concrete facts, figures, dates and quotes. You cannot search. Call read_article for\n"
            "each URL with a focus that says what the task needs. If a page fails (paywall,\n"
            "timeout, no text), say so and continue with the next URL."
        ),
        make_tools=make_article_tools,
        tool_call_limit=3,
    ),
}


@dataclass
class WorkerReport:
    status: str | None
    summary: str
    findings: list[Finding]


def _clean_point(text: str) -> str:
    return text.replace("**", "").replace("`", "").strip()


def parse_report(text: str) -> WorkerReport:
    """Parse the worker's final answer, tolerating markdown and small format slips."""
    status_match = _STATUS_RE.search(text or "")
    status = status_match.group(1).lower() if status_match else None

    summary_lines: list[str] = []
    findings: list[dict] = []
    current: dict | None = None
    for line in (text or "").splitlines():
        if _FINDING_RE.match(line):
            url = _URL_RE.search(line)
            current = {"url": url.group(0).rstrip(".,;") if url else None, "title": "", "points": []}
            findings.append(current)
            continue
        if current is None:
            if line.strip() and not _STATUS_RE.search(line) and "FINDINGS" not in line.upper():
                summary_lines.append(_REPORT_RE.sub("", line).strip())
            continue
        if current["url"] is None and (url := _URL_RE.search(line)):
            current["url"] = url.group(0).rstrip(".,;")
        elif title := _TITLE_RE.match(line):
            current["title"] = _clean_point(title.group(1))
        elif point := _POINT_RE.match(line):
            current["points"].append(_clean_point(point.group(1)))

    summary = " ".join(" ".join(summary_lines).split())[:600]
    parsed = [
        Finding(url=f["url"], title=f["title"] or f["url"], key_points=f["points"])
        for f in findings
        if f["url"] and f["points"]
    ]
    return WorkerReport(status=status, summary=summary, findings=parsed)


def decide_status(claimed: str | None, saved: int, errors: int) -> str:
    """Use the worker's own status, but never accept "success" with nothing saved."""
    if saved == 0:
        return "failed"
    if claimed:
        return claimed
    return "partial" if errors else "success"


class WorkerAgent:
    def __init__(
        self,
        agent_id: str,
        *,
        settings: Settings,
        channel: RunChannel,
        evidence: EvidenceStore,
        http: httpx.AsyncClient,
        budget: Budget,
        simulate_failure: bool = False,
    ) -> None:
        self.agent_id = agent_id
        self.profile = PROFILES[agent_id]
        self.settings = settings
        self.channel = channel
        self.evidence = evidence
        self.http = http
        self.budget = budget
        self.simulate_failure = simulate_failure

    def _prompt(self, task: TaskSpec, query: str) -> str:
        parts = [f"OVERALL RESEARCH QUESTION: {query}", f"YOUR TASK: {task.instruction}"]
        if task.rationale:
            parts.append(f"WHY THE COORDINATOR WANTS THIS: {task.rationale}")
        if task.urls:
            parts.append("URLS TO READ:\n" + "\n".join(f"- {u}" for u in task.urls))
        return "\n".join(parts)

    def _make_agent(self, ctx: ToolContext) -> Agent:
        model, fallbacks = build_model_chain(self.agent_id, self.settings, self.channel)
        return Agent(
            name=self.profile.name,
            model=model,
            fallback_config=fallbacks,
            instructions=PROTOCOL.format(name=self.profile.name, specialty=self.profile.specialty,
                                         tool_calls=self.profile.tool_call_limit,
                                         max_findings=self.budget.max_findings_per_task),
            tools=self.profile.make_tools(ctx),
            tool_call_limit=self.profile.tool_call_limit,
            add_datetime_to_context=True,
            telemetry=False,
        )

    async def execute(
        self, task: TaskSpec, task_id: str, query: str, allowed_urls: set[str] | None = None
    ) -> TaskResult:
        ctx = ToolContext(
            channel=self.channel,
            agent_id=self.agent_id,
            task_id=task_id,
            evidence=self.evidence,
            http=self.http,
            max_findings=self.budget.max_findings_per_task,
            simulate_failure=self.simulate_failure,
            allowed_urls=allowed_urls,
        )
        self.channel.status(self.agent_id, "working", f"{task_id}: {task.instruction[:120]}")
        started = time.monotonic()
        try:
            reply = await run_agent(self._make_agent(ctx), self._prompt(task, query),
                                    channel=self.channel, agent_id=self.agent_id,
                                    timeout=self.settings.agent_timeout_s)
            report = parse_report(str(reply.content or ""))
            ctx.save_findings(report.findings)
            status = decide_status(report.status, len(ctx.evidence_ids), len(ctx.errors))
            summary = report.summary or "(no report)"
            if ctx.rejected:
                summary += f" [{ctx.rejected} finding(s) rejected by source checks]"
        except AgentFailure as exc:
            ctx.errors.append(str(exc))
            # Keep what the tools already retrieved rather than throwing the task away.
            salvaged = ctx.salvage()
            status = "partial" if ctx.evidence_ids else "failed"
            summary = str(exc)
            if salvaged:
                summary += f" Saved {len(ctx.evidence_ids)} raw source(s) from its tool results."
                self.channel.emit("guardrail", agent=self.agent_id, task_id=task_id,
                                  rule="salvaged", detail=f"Kept {len(ctx.evidence_ids)} source(s) "
                                  "retrieved before the agent failed.")
        finally:
            self.channel.status(self.agent_id, "idle")

        return TaskResult(
            task_id=task_id,
            agent=self.agent_id,
            instruction=task.instruction,
            status=status,
            summary=summary,
            evidence_ids=list(ctx.evidence_ids),
            tool_calls=ctx.tool_calls,
            errors=ctx.errors[:5],
            duration_s=round(time.monotonic() - started, 1),
        )
