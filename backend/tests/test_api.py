import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.orchestrator import AgentSuite
from app.store import RunStore
from tests.fakes import APPROVE, FakeCritic, FakeWorker, FakeWriter, ScriptedCoordinator, decision, delegate


def fake_suite(*, settings, channel, evidence, http, budget, options):
    coordinator = ScriptedCoordinator([delegate("hn_scout", "web_researcher"), decision("draft"),
                                       decision("finish")])
    workers = {a: FakeWorker(a, evidence, fail=a in options.simulate_failures)
               for a in ("hn_scout", "web_researcher", "article_reader")}
    return AgentSuite(coordinator=coordinator, writer=FakeWriter(), critic=FakeCritic(APPROVE),
                      workers=workers)


@pytest.fixture
def client(tmp_path):
    settings = Settings(groq_api_key="test-key", frontend_dist=tmp_path / "no-dist")
    app = create_app(settings=settings, store=RunStore(":memory:"), suite_factory=fake_suite)
    with TestClient(app) as test_client:
        yield test_client


def read_stream(client, run_id, after=0):
    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events", params={"after": after}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data: ") and line != "data: {}":
                events.append(json.loads(line[6:]))
    return events


def test_health_and_agents(client):
    assert client.get("/api/health").json()["llm_configured"] is True
    body = client.get("/api/agents").json()
    assert [a["id"] for a in body["agents"]] == [
        "coordinator", "hn_scout", "web_researcher", "article_reader", "writer", "critic"]
    assert all(a["model"] for a in body["agents"])
    assert set(body["budgets"]) == {"quick", "standard", "deep"}


@pytest.mark.parametrize("payload", [
    {"query": ""},
    {"query": "?!"},
    {"query": "x" * 501},
    {"query": "valid question", "options": {"depth": "extreme"}},
    {"query": "valid question", "options": {"simulate_failures": ["writer"]}},
])
def test_invalid_requests_are_rejected(client, payload):
    assert client.post("/api/runs", json=payload).status_code == 422


def test_run_streams_events_then_serves_result_trace_and_report(client):
    run_id = client.post("/api/runs", json={"query": "What changed in LLM pricing?"}).json()["run_id"]

    events = read_stream(client, run_id)
    types = [e["type"] for e in events]
    assert types[0] == "run_started"
    assert types[-1] == "run_completed"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert {"message", "plan", "draft", "review"} <= set(types)

    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "completed"
    assert run["result"]["review_status"] == "approved"

    trace = client.get(f"/api/runs/{run_id}/trace")
    assert "attachment" in trace.headers["content-disposition"]
    assert len(trace.json()["events"]) == len(events)

    report = client.get(f"/api/runs/{run_id}/report.md").text
    assert report.startswith("# Report v1")
    assert "## Sources" in report

    # A finished run replays from the store, honouring the resume point.
    assert [e["seq"] for e in read_stream(client, run_id, after=len(events) - 2)] == [
        len(events) - 1, len(events)]
    assert client.get("/api/runs").json()["runs"][0]["id"] == run_id


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/nope/events").status_code == 404


def test_missing_api_key_is_503(tmp_path):
    settings = Settings(groq_api_key=None, frontend_dist=tmp_path)
    app = create_app(settings=settings, store=RunStore(":memory:"), suite_factory=fake_suite)
    with TestClient(app) as test_client:
        assert test_client.post("/api/runs", json={"query": "anything at all"}).status_code == 503


def test_concurrent_run_limit_returns_429(tmp_path):
    settings = Settings(groq_api_key="k", max_active_runs=0, frontend_dist=tmp_path)
    app = create_app(settings=settings, store=RunStore(":memory:"), suite_factory=fake_suite)
    with TestClient(app) as test_client:
        assert test_client.post("/api/runs", json={"query": "anything at all"}).status_code == 429


def test_daily_run_limit_returns_429(tmp_path):
    settings = Settings(groq_api_key="k", max_runs_per_day=1, frontend_dist=tmp_path)
    app = create_app(settings=settings, store=RunStore(":memory:"), suite_factory=fake_suite)
    with TestClient(app) as test_client:
        first = test_client.post("/api/runs", json={"query": "anything at all"})
        assert first.status_code == 202
        read_stream(test_client, first.json()["run_id"])
        second = test_client.post("/api/runs", json={"query": "anything at all"})
        assert second.status_code == 429
        assert "daily question limit" in second.json()["detail"]


def test_follow_up_joins_the_conversation(client):
    first = client.post("/api/runs", json={"query": "What changed in LLM pricing?"}).json()
    assert first["thread_id"] == first["run_id"]
    read_stream(client, first["run_id"])

    second = client.post("/api/runs", json={"query": "Summarise that in three bullets",
                                            "thread_id": first["thread_id"]}).json()
    assert second["thread_id"] == first["thread_id"]
    events = read_stream(client, second["run_id"])
    assert events[0]["follow_up"] is True
    assert any(e["type"] == "context" for e in events)

    thread = client.get(f"/api/threads/{first['thread_id']}").json()
    assert [r["id"] for r in thread["runs"]] == [first["run_id"], second["run_id"]]
    [listed] = client.get("/api/threads").json()["threads"]
    assert listed["turns"] == 2 and listed["title"] == "What changed in LLM pricing?"


def test_follow_up_to_unknown_conversation_is_404(client):
    response = client.post("/api/runs", json={"query": "anything at all", "thread_id": "missing"})
    assert response.status_code == 404
    assert client.get("/api/threads/missing").status_code == 404


@pytest.mark.parametrize("endpoint,collection", [
    ("/api/runs", "runs"),
    ("/api/threads", "threads"),
])
@pytest.mark.parametrize("limit", [-10, 0, 1, 100, 1000])
def test_listing_limits_are_accepted(client, endpoint, collection, limit):
    response = client.get(endpoint, params={"limit": limit})
    assert response.status_code == 200
    assert isinstance(response.json()[collection], list)


@pytest.mark.parametrize("path", [
    "/api/runs/missing/trace",
    "/api/runs/missing/report.md",
])
def test_missing_run_downloads_return_404(client, path):
    assert client.get(path).status_code == 404


def test_sse_reconnect_resumes_from_last_event_id(client):
    run_id = client.post(
        "/api/runs",
        json={"query": "What changed in LLM pricing?"},
    ).json()["run_id"]

    events = read_stream(client, run_id)
    last_seen = len(events) - 2

    resumed = []
    with client.stream(
        "GET",
        f"/api/runs/{run_id}/events",
        headers={"Last-Event-ID": str(last_seen)},
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: ") and line != "data: {}":
                resumed.append(json.loads(line[6:]))

    assert [event["seq"] for event in resumed] == [
        last_seen + 1,
        last_seen + 2,
    ]


def test_frontend_route_serves_only_files_inside_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("app shell")
    (dist / "robots.txt").write_text("allow")
    (tmp_path / ".env").write_text("GROQ_API_KEY=secret")
    settings = Settings(groq_api_key="k", frontend_dist=dist)
    with TestClient(create_app(settings=settings, store=RunStore(":memory:"))) as test_client:
        assert test_client.get("/robots.txt").text == "allow"
        assert test_client.get("/..%2f.env").text == "app shell"
        assert test_client.get("/some/client/route").text == "app shell"
