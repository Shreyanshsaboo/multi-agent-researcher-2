"""Orchestrator behaviour with scripted agents: routing, re-planning, revision and recovery."""

import pytest

from app.agents import AgentFailure
from app.config import Budget
from app.events import RunChannel
from app.evidence import EvidenceStore
from app.orchestrator import AgentSuite, Orchestrator
from app.schemas import Critique, Ruling, TaskSpec
from tests.fakes import (
    APPROVE,
    BUDGET,
    REVISE,
    FakeCritic,
    FakeWorker,
    FakeWriter,
    ScriptedCoordinator,
    decision,
    delegate,
)


def build(coordinator, *, critic=None, writer=None, failing=(), budget=BUDGET, conversation=None):
    channel, evidence = RunChannel("r"), EvidenceStore()
    workers = {a: FakeWorker(a, evidence, fail=a in failing)
               for a in ("hn_scout", "web_researcher", "article_reader")}
    suite = AgentSuite(coordinator=coordinator, writer=writer or FakeWriter(),
                       critic=critic or FakeCritic(APPROVE), workers=workers)
    orchestrator = Orchestrator(run_id="r", query="What changed?", depth="quick", budget=budget,
                                channel=channel, suite=suite, evidence=evidence,
                                conversation=conversation)
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


async def test_article_reader_urls_can_be_evidence_ids_or_slightly_mangled_copies():
    url = "https://www.manilatimes.net/2026/10/08/m-mark-esports-event-returns-for-second-year/2442043"
    read = decision("delegate", tasks=[TaskSpec(agent="article_reader", instruction="read", urls=[
        "E1", url.replace("esports-event-returns", "esports-returns")])])
    orchestrator, channel, workers = build(ScriptedCoordinator([read, decision("draft"),
                                                                decision("finish")]))
    orchestrator.state.evidence.add(url=url, title="BLAST returns", source_type="news",
                                    agent="web_researcher", key_points=["a fact"])
    await orchestrator.run()

    # Both point at E1 (the second is its URL copied with a word dropped): one read is enough.
    [task] = workers["article_reader"].calls
    assert task.urls == [url]
    assert not [e for e in channel.events if e.get("rule") == "decision_corrected"]


async def test_a_task_that_repeats_an_earlier_one_is_dropped_and_the_writer_drafts():
    same = "Search news for the most widely reported sports stories this week"
    coordinator = ScriptedCoordinator([
        decision("delegate", tasks=[TaskSpec(agent="web_researcher", instruction=same)]),
        decision("delegate", tasks=[TaskSpec(agent="web_researcher", instruction=same + " today")]),
        decision("finish"),
    ])
    orchestrator, channel, workers = build(coordinator)
    result = await orchestrator.run()

    assert len(workers["web_researcher"].calls) == 1
    notes = [e["detail"] for e in channel.events if e.get("rule") == "decision_corrected"]
    assert any("repeats T1" in n for n in notes)
    assert result.review_status == "approved"


def hn_task(instruction):
    return decision("delegate", tasks=[TaskSpec(agent="hn_scout", instruction=instruction)])


async def test_turn_limit_stops_research_and_still_writes_a_report():
    # Nothing is found until the last turn, so that turn researches and no review fits after it.
    coordinator = ScriptedCoordinator([delegate("web_researcher"),
                                       hn_task("complaints about latency in production")])
    budget = Budget(max_turns=2, max_drafts=2, max_tasks_per_turn=2, max_findings_per_task=3,
                    max_urls_per_read=2, time_limit_s=60)
    orchestrator, channel, _ = build(coordinator, budget=budget, failing=("web_researcher",))
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


EARLIER = [{
    "query": "How are teams cutting inference costs?",
    "title": "Inference cost tactics",
    "summary": "Caching and routing cut costs [E1].",
    "evidence": [{"id": "E4", "url": "https://a.com/caching", "title": "Caching", "source_type": "web",
                  "found_by": ["web_researcher"], "key_points": ["Caching cut costs 36%"],
                  "full_text_read": True, "published": None, "meta": {}}],
}]


async def test_follow_up_sees_the_conversation_and_reuses_earlier_sources():
    def summarise(view):
        assert "CONVERSATION SO FAR" in view
        assert "Q1: How are teams cutting inference costs?" in view
        assert "[E1] Caching" in view
        return decision("draft", writer_brief="Summarise the earlier answer")

    coordinator = ScriptedCoordinator([summarise, decision("finish")])
    orchestrator, channel, workers = build(coordinator, conversation=EARLIER)
    result = await orchestrator.run()

    # Answered from the carried-over source, without any new research.
    assert not any(w.calls for w in workers.values())
    assert result.cited_ids == ["E1"]
    assert result.evidence[0].meta["earlier_turn"] is True
    [context] = [e for e in channel.events if e["type"] == "context"]
    assert context["carried"] == ["E1"]


async def test_research_on_the_last_turn_becomes_a_reviewed_draft():
    coordinator = ScriptedCoordinator([hn_task("launch threads about pricing"),
                                       hn_task("complaints about latency in production")])
    budget = Budget(max_turns=2, max_drafts=2, max_tasks_per_turn=2, max_findings_per_task=3,
                    max_urls_per_read=2, time_limit_s=60)
    orchestrator, channel, workers = build(coordinator, budget=budget)
    result = await orchestrator.run()

    assert len(workers["hn_scout"].calls) == 1
    assert result.review_status == "approved"
    notes = [e["detail"] for e in channel.events if e.get("rule") == "decision_corrected"]
    assert any(n.startswith("Last turn") for n in notes)
