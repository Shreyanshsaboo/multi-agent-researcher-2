"""The writer: turns the evidence store into a cited report and revises it.

On a revision it answers every critic issue, either fixing it or disputing it
with a reason. Disputes go back to the critic for a ruling, and the
coordinator settles anything still contested.
"""

import re

from agno.agent import Agent

from app.agents.runtime import run_structured
from app.config import Settings
from app.events import RunChannel
from app.llm import build_model_chain
from app.schemas import Draft, WriterOutput
from app.state import RunState

INSTRUCTIONS = """\
You are the Writer on a six-agent research team. You turn the team's evidence into a clear,
well-organised research report in Markdown.

RULES
- Use only the evidence provided. Every sentence with a fact, figure or opinion ends with
  citations like [E3] or [E1][E4]. Cite only ids that appear in the evidence list.
- Structure: open with a 2-3 sentence summary paragraph (no heading), then 2-4 "##" sections
  organised by theme, then "## Open questions and limitations" for gaps, conflicting sources
  and anything the evidence could not settle.
- Separate facts from opinions ("HN commenters argue ... [E2]"). When sources disagree, say so
  and cite both sides.
- Keep figures, dates and names from the evidence. 350-650 words. Do not add a title heading
  or a sources list; the app renders both.

FOLLOW-UPS
- If the prompt shows earlier questions and answers, answer the new question in that context
  without repeating the earlier answer. Sources from earlier answers are in the evidence list.

REVISING
- When you get a critic review, address every issue. Add one response per issue: action
  "fixed" with what you changed, or "disputed" only if the critic is wrong given the evidence,
  with the reason and the evidence ids that show it.
- If the coordinator's brief rules on a dispute, follow the ruling.
"""


def _strip_title(markdown: str) -> str:
    return re.sub(r"\A\s*#\s+[^\n]*\n+", "", markdown).strip()


def fallback_draft(state: RunState, version: int) -> Draft:
    """A plain findings digest, used when the writer itself cannot produce a draft."""
    lines = [
        "The writing agent was unavailable, so this is a digest of the evidence the research "
        "agents collected rather than a synthesised report.",
        "",
        "## Key findings",
    ]
    for e in state.evidence.all():
        if e.key_points:
            lines.append(f"- **{e.title}**: {e.key_points[0]} [{e.id}]")
    lines += ["", "## Open questions and limitations",
              "This digest was not synthesised or reviewed, so read the sources directly."]
    return Draft(version=version, title=f"Findings: {state.query[:80]}",
                 markdown="\n".join(lines), fallback=True)


class WriterAgent:
    agent_id = "writer"

    def __init__(self, settings: Settings, channel: RunChannel) -> None:
        self.settings = settings
        self.channel = channel

    def _make_agent(self) -> Agent:
        model, fallbacks = build_model_chain(self.agent_id, self.settings, self.channel)
        return Agent(
            name="Writer",
            model=model,
            fallback_config=fallbacks,
            instructions=INSTRUCTIONS,
            output_schema=WriterOutput,
            telemetry=False,
        )

    def _prompt(self, state: RunState, brief: str) -> str:
        parts = []
        if state.conversation:
            parts.append(f"EARLIER IN THIS CONVERSATION:\n{state.render_conversation()}")
        parts += [
            f"USER QUERY: {state.query}",
            f"RESEARCH PLAN:\n{state.render_plan()}",
            f"COORDINATOR'S BRIEF: {brief or 'Write the report.'}",
            f"EVIDENCE (cite as [E#]):\n{state.evidence.render_full()}",
        ]
        draft, review = state.latest_draft, state.latest_review
        if draft and review and review.draft_version == draft.version and review.critique:
            c = review.critique
            issues = "\n".join(
                f"{i.id} [{i.severity} {i.kind}] {i.detail} Suggestion: {i.suggestion}" for i in c.issues
            ) or "(no specific issues)"
            rulings = "\n".join(
                f"Ruling on your dispute of {r.issue_id}: {'accepted' if r.accepted else 'rejected'}. {r.note}"
                for r in c.rulings
            )
            parts += [
                f"YOUR PREVIOUS DRAFT (v{draft.version}):\n{draft.markdown}",
                f"CRITIC'S REVIEW OF v{draft.version}: {c.verdict}, score {c.score}/10. {c.summary}\n"
                f"ISSUES TO ADDRESS:\n{issues}" + (f"\n{rulings}" if rulings else ""),
            ]
        return "\n\n".join(parts)

    async def write(self, state: RunState, brief: str) -> Draft:
        version = len(state.drafts) + 1
        revising = version > 1
        self.channel.status(self.agent_id, "writing",
                            f"revising to v{version}" if revising else "writing first draft")
        try:
            output = await run_structured(
                self._make_agent,
                self._prompt(state, brief),
                WriterOutput,
                channel=self.channel,
                agent_id=self.agent_id,
                timeout=self.settings.agent_timeout_s,
            )
        finally:
            self.channel.status(self.agent_id, "idle")
        return Draft(
            version=version,
            title=output.title.strip().lstrip("# ") or state.query,
            markdown=_strip_title(output.report_markdown),
            responses=output.responses,
        )
