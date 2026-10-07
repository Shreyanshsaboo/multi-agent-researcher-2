"""Orchestrator behaviour with scripted agents: routing, re-planning, revision and recovery."""

import pytest

from app.agents import AgentFailure
from app.config import Budget
from app.events import RunChannel
from app.evidence import EvidenceStore
from app.orchestrator import AgentSuite, Orchestrator
from app.schemas import (
    CoordinatorDecision,
    Critique,
    Draft,
    Issue,
    IssueResponse,
    PlanItem,
    Ruling,
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


def build(coordinator, *, critic=None, writer=None, failing=(), budget=BUDGET):
    channel, evidence = RunChannel("r"), EvidenceStore()
    workers = {a: FakeWorker(a, evidence, fail=a in failing)
               for a in ("hn_scout", "web_researcher", "article_reader")}
    suite = AgentSuite(coordinator=coordinator, writer=writer or FakeWriter(),
                       critic=critic or FakeCritic(APPROVE), workers=workers)
    orchestrator = Orchestrator(run_id="r", query="What changed?", depth="quick", budget=budget,
                                channel=channel, suite=suite, evidence=evidence)
    return orchestrator, channel, workers


def messages(channel):
    return [(e["sender"], e["recipients"], e["kind"]) for e in channel.events if e["type"] == "message"]


async def test_happy_path_routes_messages_between_agents():
    coordinator = ScriptedCoordinator([delegate("hn_scout", "web_researcher"), decision("draft"),
                                       decision("finish")])
    orchestrator, channel, _ = build(coordinator)
    result = await orchestrator.run()

    assert result.status == "completed"
    assert result.review_status == "approved"
    assert result.final_score == 8
    assert result.cited_ids == ["E1"]
    assert messages(channel) == [
        ("user", ["coordinator"], "query"),
        ("coordinator", ["hn_scout", "web_researcher"], "decision"),
        ("coordinator", ["hn_scout"], "task"),
        ("coordinator", ["web_researcher"], "task"),
        ("hn_scout", ["coordinator"], "result"),
        ("web_researcher", ["coordinator"], "result"),
        ("coordinator", ["writer"], "decision"),
        ("coordinator", ["writer"], "brief"),
        ("writer", ["critic"], "draft"),
        ("critic", ["coordinator"], "verdict"),
        ("coordinator", ["user"], "decision"),
        ("coordinator", ["user"], "final"),
    ]


async def test_failed_task_is_visible_to_coordinator_which_replans():
    def replan(view):
        assert "web_researcher [failed]" in view
        assert "web_search: timeout" in view
        return delegate("hn_scout")

    coordinator = ScriptedCoordinator([delegate("web_researcher"), replan, decision("draft"),
                                       decision("finish")])
    orchestrator, _, workers = build(coordinator, failing={"web_researcher"})
    result = await orchestrator.run()

    assert len(workers["hn_scout"].calls) == 1
    assert result.stats.failed_tasks == 1
    assert result.review_status == "approved"


async def test_revision_round_sends_critique_to_writer_and_disputes_back_to_critic():
    approve_with_ruling = Critique(verdict="approve", score=8, summary="Fixed.",
                                   rulings=[Ruling(issue_id="I1", accepted=True, note="fair")])
    coordinator = ScriptedCoordinator([delegate("web_researcher"), decision("draft"),
                                       decision("draft", writer_brief="Fix I1"), decision("finish")])
    writer = FakeWriter()
    orchestrator, channel, _ = build(coordinator, writer=writer,
                                     critic=FakeCritic(REVISE, approve_with_ruling))
    result = await orchestrator.run()

    assert writer.saw_review == [False, True]
    kinds = messages(channel)
    assert ("critic", ["writer"], "critique") in kinds
    draft_messages = [e for e in channel.events if e.get("kind") == "draft"]
    assert "disputed 1" in draft_messages[-1]["summary"]
    assert result.stats.drafts == 2
    assert result.review_status == "approved"


async def test_draft_request_past_the_draft_budget_becomes_finish_with_open_issues():
    coordinator = ScriptedCoordinator([delegate("web_researcher"), decision("draft"),
                                       decision("draft"), decision("draft")])
    budget = Budget(max_turns=6, max_drafts=2, max_tasks_per_turn=2, max_findings_per_task=3,
                    max_urls_per_read=2, time_limit_s=60)
    orchestrator, channel, _ = build(coordinator, critic=FakeCritic(REVISE, REVISE), budget=budget)
    result = await orchestrator.run()

    assert result.stats.drafts == 2
    assert result.review_status == "accepted_with_issues"
    assert [i.id for i in result.unresolved_issues] == ["I1"]
    corrections = [e for e in channel.events if e.get("rule") == "decision_corrected"]
    assert any("drafts are used" in e["detail"] for e in corrections)


async def test_coordinator_outage_falls_back_to_default_policy():
    outage = AgentFailure("coordinator model call failed: rate limited")
    coordinator = ScriptedCoordinator([outage, outage, outage])
    orchestrator, channel, workers = build(coordinator)
    result = await orchestrator.run()

    assert workers["web_researcher"].calls and workers["hn_scout"].calls
    assert result.status == "completed"
    assert result.report_markdown
    decisions = [e for e in channel.events if e.get("kind") == "decision"]
    assert all(d["content"]["fallback"] for d in decisions)
    assert [d["content"]["action"] for d in decisions] == ["delegate", "draft", "finish"]


async def test_article_reader_cannot_read_urls_outside_the_evidence_store():
    bad = decision("delegate", tasks=[TaskSpec(agent="article_reader", instruction="read",
                                               urls=["https://invented.example.com"])])
    coordinator = ScriptedCoordinator([bad, decision("draft"), decision("finish")])
    orchestrator, channel, workers = build(coordinator)
    await orchestrator.run()

    assert workers["article_reader"].calls == []
    # With nothing runnable and no evidence, the orchestrator starts default research instead.
    assert workers["web_researcher"].calls
    notes = [e["detail"] for e in channel.events if e.get("rule") == "decision_corrected"]
    assert any("article_reader needs URLs" in n for n in notes)


async def test_turn_limit_stops_research_and_still_writes_a_report():
    coordinator = ScriptedCoordinator([delegate("hn_scout")] * 2)
    budget = Budget(max_turns=2, max_drafts=2, max_tasks_per_turn=2, max_findings_per_task=3,
                    max_urls_per_read=2, time_limit_s=60)
    orchestrator, channel, _ = build(coordinator, budget=budget)
    result = await orchestrator.run()

    assert result.report_markdown
    assert result.review_status == "unreviewed"
    assert "turn limit" in result.message
    assert any(e.get("rule") == "budget" for e in channel.events)


async def test_writer_outage_yields_an_unreviewed_evidence_digest():
    coordinator = ScriptedCoordinator([delegate("web_researcher"), decision("draft"),
                                       decision("finish")])
    orchestrator, channel, _ = build(coordinator, writer=FakeWriter(fail=True))
    result = await orchestrator.run()

    assert "[E1]" in result.report_markdown
    assert result.review_status == "unreviewed"
    assert any(e["type"] == "agent_error" and e["agent"] == "writer" for e in channel.events)


async def test_reject_ends_the_run_without_research():
    coordinator = ScriptedCoordinator([decision("reject", message="Not a research question.")])
    orchestrator, _, workers = build(coordinator)
    result = await orchestrator.run()

    assert result.status == "rejected"
    assert result.message == "Not a research question."
    assert not any(w.calls for w in workers.values())


@pytest.mark.parametrize("action", ["finish", "draft"])
async def test_cannot_finish_or_draft_before_any_research(action):
    coordinator = ScriptedCoordinator([decision(action), decision("draft"), decision("finish")])
    orchestrator, _, workers = build(coordinator)
    result = await orchestrator.run()

    assert workers["web_researcher"].calls
    assert result.report_markdown
