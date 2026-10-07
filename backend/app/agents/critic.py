"""The critic: an independent reviewer that checks each draft against the evidence.

It runs on a different model family from the writer so the two do not share
blind spots, and it gets a deterministic citation check alongside the draft.
Its verdict goes to the coordinator; its issues go to the writer.
"""

from agno.agent import Agent

from app.agents.runtime import run_structured
from app.config import Settings
from app.events import RunChannel
from app.llm import build_fallbacks, build_model
from app.schemas import CitationCheck, Critique, Draft
from app.state import RunState

INSTRUCTIONS = """\
You are the Critic on a six-agent research team: an independent reviewer running on a
different model from the Writer. Judge the draft against the evidence list, not against your
own knowledge.

CHECK
1. Support: is every claim backed by the evidence it cites? Flag claims the cited source does
   not support (unsupported_claim) and wrong or unknown ids (citation_error).
2. Coverage: does the draft answer the user's query and the plan's sub-questions?
   (missing_coverage)
3. Conflicts: are disagreements between sources acknowledged? (contradiction)
4. Clarity: flag writing only where it would mislead or confuse a reader. (clarity)
Real problems found by the automated citation check should become issues.

OUTPUT
- Give each issue an id (I1, I2, ...), a severity ("major" if it would mislead a reader), a
  specific detail and a concrete suggestion. Report 0-5 issues, most important first.
- research_requests: only for gaps the current evidence cannot fill, at most 2, each naming
  the best worker (hn_scout, web_researcher or article_reader) and a specific instruction.
- If the writer disputed any of your earlier issues, add a ruling for each one: accepted true
  if the writer's argument holds given the evidence.
- verdict "approve" when no major issues remain and the score is 7 or more, otherwise
  "revise". score 1-10: how trustworthy and useful the report is.
"""


def render_checks(checks: CitationCheck) -> str:
    unused = checks.evidence_total - len(set(checks.cited_ids) - set(checks.unknown_ids))
    lines = [
        f"- cited ids: {', '.join(checks.cited_ids) or 'none'}",
        f"- unknown ids (cited but not in the evidence store): {', '.join(checks.unknown_ids) or 'none'}",
        f"- sources never cited: {max(0, unused)} of {checks.evidence_total}",
    ]
    if checks.uncited_paragraphs:
        lines.append("- substantive paragraphs with no citation:")
        lines += [f"  * \"{p}…\"" for p in checks.uncited_paragraphs[:4]]
    return "\n".join(lines)


class CriticAgent:
    agent_id = "critic"

    def __init__(self, settings: Settings, channel: RunChannel) -> None:
        self.settings = settings
        self.channel = channel

    def _make_agent(self) -> Agent:
        return Agent(
            name="Critic",
            model=build_model(self.agent_id, self.settings),
            fallback_config=build_fallbacks(self.agent_id, self.settings),
            instructions=INSTRUCTIONS,
            output_schema=Critique,
            telemetry=False,
        )

    def _prompt(self, state: RunState, draft: Draft, checks: CitationCheck) -> str:
        parts = [
            f"USER QUERY: {state.query}",
            f"RESEARCH PLAN:\n{state.render_plan()}",
            f"EVIDENCE:\n{state.evidence.render_full()}",
            f"DRAFT v{draft.version}: \"{draft.title}\"\n{draft.markdown}",
            f"AUTOMATED CITATION CHECK:\n{render_checks(checks)}",
        ]
        previous = state.latest_review
        if draft.responses and previous and previous.critique:
            earlier = "\n".join(f"{i.id}: {i.detail}" for i in previous.critique.issues)
            answers = "\n".join(f"{r.issue_id} {r.action}: {r.note}" for r in draft.responses)
            parts.append(f"YOUR ISSUES ON v{previous.draft_version}:\n{earlier}\n\n"
                         f"WRITER'S RESPONSES:\n{answers}")
        return "\n\n".join(parts)

    async def review(self, state: RunState, draft: Draft, checks: CitationCheck) -> Critique:
        self.channel.status(self.agent_id, "reviewing", f"checking draft v{draft.version}")
        try:
            return await run_structured(
                self._make_agent,
                self._prompt(state, draft, checks),
                Critique,
                channel=self.channel,
                agent_id=self.agent_id,
                timeout=self.settings.agent_timeout_s,
            )
        finally:
            self.channel.status(self.agent_id, "idle")
