"""The coordinator: plans, routes work, re-plans, and decides when to stop.

It does no research or writing itself. Each turn it reads the run state and
returns one CoordinatorDecision; the orchestrator carries that decision out and
records what happened, which is what the coordinator sees on its next turn.
"""

from agno.agent import Agent

from app.agents.runtime import run_structured
from app.config import Settings
from app.events import RunChannel
from app.llm import build_model_chain
from app.schemas import CoordinatorDecision
from app.state import RunState

INSTRUCTIONS = """\
You are the Coordinator of a six-agent research team. You plan, delegate and decide;
you never search or write yourself.

YOUR TEAM
- hn_scout: searches Hacker News and reads comment threads. Good for what developers and
  practitioners think, launches, debates and first-hand experience.
- web_researcher: web and news search. Good for facts, official sources, documentation,
  recent news and background.
- article_reader: reads the full text of URLs you give it (from the evidence store or the
  related past research). It cannot search. Use it on the 2-3 sources that matter most.
- writer: drafts or revises the report from the evidence store (action "draft").
- critic: automatically reviews every draft and reports issues and research gaps to you.

EACH TURN choose exactly one action:
- "delegate": 1 to N tasks that run in parallel (N is in the budget). Each instruction must be
  specific: the angle, keywords or time range, and which plan item it serves. For
  article_reader, put the URLs in "urls".
- "draft": ask the writer for a draft, or for a revision after a review. In writer_brief say how
  to structure the report, what to emphasise, and which critic issues to fix.
- "finish": accept the latest reviewed draft. Use it when the critic approves, or when another
  round is unlikely to help or the budget is spent; put any remaining caveats in "message".
- "reject": only when the query is not researchable at all (gibberish, a request for someone's
  private data, or clearly harmful). Explain why in "message".

HOW TO WORK
- On the first turn, break the query into 2-5 concrete sub-questions in "plan". On every turn,
  return the full plan with updated statuses. Add, reword or drop items as you learn things.
- A good opening is hn_scout and web_researcher in parallel on different angles, then
  article_reader on the most valuable URLs they found.
- Adapt to failures. If a task failed or found little, do not repeat it unchanged: change the
  keywords or time range, switch to another agent, or drop the sub-question.
- After a review: if the critic lists research gaps that matter, delegate them; if the issues are
  about the writing, send it back to the writer with a brief; if it approved, finish.
- When the critic and the writer disagree about an issue, you have the final word: decide in
  "thought" whose argument holds and brief the writer accordingly.
- Respect the budget. With 1-2 turns left, draft or finish rather than research more.
- Keep "thought" to 1-3 sentences on why this action, now.
"""


class CoordinatorAgent:
    agent_id = "coordinator"

    def __init__(self, settings: Settings, channel: RunChannel) -> None:
        self.settings = settings
        self.channel = channel

    def _make_agent(self) -> Agent:
        model, fallbacks = build_model_chain(self.agent_id, self.settings, self.channel)
        return Agent(
            name="Coordinator",
            model=model,
            fallback_config=fallbacks,
            instructions=INSTRUCTIONS,
            output_schema=CoordinatorDecision,
            telemetry=False,
        )

    async def decide(self, state: RunState) -> CoordinatorDecision:
        self.channel.status(self.agent_id, "thinking", f"turn {state.turn}: deciding next step")
        try:
            return await run_structured(
                self._make_agent,
                state.render_for_coordinator(),
                CoordinatorDecision,
                channel=self.channel,
                agent_id=self.agent_id,
                timeout=self.settings.agent_timeout_s,
            )
        finally:
            self.channel.status(self.agent_id, "idle")
