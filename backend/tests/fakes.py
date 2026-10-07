"""Scripted stand-ins for the LLM agents, shared by the orchestrator and API tests."""

from app.agents import AgentFailure
from app.config import Budget
from app.schemas import (
    CoordinatorDecision,
    Critique,
    Draft,
    Issue,
    IssueResponse,
    PlanItem,
    TaskResult,
    TaskSpec,
)

BUDGET = Budget(max_turns=6, max_drafts=2, max_tasks_per_turn=2, max_findings_per_task=3,
                max_urls_per_read=2, time_limit_s=60)


def decision(action, **kwargs):
    return CoordinatorDecision(thought=f"{action} now",
                               plan=[PlanItem(id=1, question="What changed?")],
                               action=action, **kwargs)


def delegate(*agents):
    return decision("delegate", tasks=[TaskSpec(agent=a, instruction=f"{a} task") for a in agents])


class ScriptedCoordinator:
    """Plays back decisions; a callable step receives the rendered state it was shown."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.views: list[str] = []

    async def decide(self, state):
        view = state.render_for_coordinator()
        self.views.append(view)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(view) if callable(step) else step


class FakeWorker:
    def __init__(self, agent_id, evidence, *, fail=False):
        self.agent_id, self.evidence, self.fail = agent_id, evidence, fail
        self.calls: list[TaskSpec] = []

    async def execute(self, task, task_id, query, allowed_urls=None):
        self.calls.append(task)
        if self.fail:
            return TaskResult(task_id=task_id, agent=self.agent_id, instruction=task.instruction,
                              status="failed", summary="search backend down",
                              errors=["web_search: timeout"])
        item, _ = self.evidence.add(url=f"https://{self.agent_id}.example.com/{task_id}",
                                    title=f"{self.agent_id} source", source_type="web",
                                    agent=self.agent_id, key_points=["a fact"])
        return TaskResult(task_id=task_id, agent=self.agent_id, instruction=task.instruction,
                          status="success", summary="found one source", evidence_ids=[item.id])


class FakeWriter:
    def __init__(self, fail=False):
        self.fail = fail
        self.saw_review: list[bool] = []

    async def write(self, state, brief):
        if self.fail:
            raise AgentFailure("writer model call failed: quota")
        self.saw_review.append(state.latest_review is not None)
        version = len(state.drafts) + 1
        responses = [IssueResponse(issue_id="I1", action="disputed", note="E1 says so")] if version > 1 else []
        return Draft(version=version, title=f"Report v{version}",
                     markdown="Summary of what changed [E1].", responses=responses)


class FakeCritic:
    def __init__(self, *critiques):
        self.critiques = list(critiques)

    async def review(self, state, draft, checks):
        return self.critiques.pop(0)


APPROVE = Critique(verdict="approve", score=8, summary="Solid.")
REVISE = Critique(verdict="revise", score=5, summary="Needs work.",
                  issues=[Issue(id="I1", severity="major", kind="unsupported_claim",
                                detail="Claim not in E1")])
