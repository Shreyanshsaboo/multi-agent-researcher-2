from app.store import RunStore


def finished_run(store, run_id, query, title, urls):
    store.create_run(run_id, query, {"depth": "quick"})
    evidence = [{"id": f"E{i}", "url": u} for i, u in enumerate(urls, 1)]
    store.finish_run(run_id, "completed", {
        "title": title,
        "final_score": 8,
        "review_status": "approved",
        "evidence": evidence,
        "cited_ids": [e["id"] for e in evidence],
    })


def test_events_round_trip_in_order_and_after_seq():
    store = RunStore(":memory:")
    store.create_run("r1", "q", {})
    for seq in (1, 2, 3):
        store.append_event("r1", {"seq": seq, "type": "x"})
    assert [e["seq"] for e in store.events("r1")] == [1, 2, 3]
    assert [e["seq"] for e in store.events("r1", after=2)] == [3]


def test_finish_and_list_runs_expose_score_and_status():
    store = RunStore(":memory:")
    finished_run(store, "r1", "LLM inference costs", "Cutting costs", ["https://a.com"])
    store.create_run("r2", "still going", {})
    runs = {r["id"]: r for r in store.list_runs()}
    assert runs["r1"]["status"] == "completed"
    assert runs["r1"]["score"] == 8
    assert runs["r2"]["status"] == "running"
    assert store.get_run("r1")["result"]["title"] == "Cutting costs"


def test_mark_interrupted_fails_runs_left_running():
    store = RunStore(":memory:")
    store.create_run("r1", "q", {})
    assert store.mark_interrupted() == 1
    assert store.get_run("r1")["status"] == "failed"


def test_recall_finds_similar_past_research_with_cited_urls():
    store = RunStore(":memory:")
    finished_run(store, "r1", "How are teams cutting LLM inference costs?", "Inference cost tactics",
                 ["https://a.com/caching", "https://b.com/routing"])
    finished_run(store, "r2", "Best sourdough starter hydration", "Sourdough", ["https://c.com"])

    related = store.recall("cheapest ways to cut LLM inference costs")
    assert [r["run_id"] for r in related] == ["r1"]
    assert related[0]["urls"] == ["https://a.com/caching", "https://b.com/routing"]
    assert store.recall("cut LLM inference costs", exclude="r1") == []


def test_threads_group_follow_ups_under_their_first_question():
    store = RunStore(":memory:")
    store.create_run("a", "First question", {})
    store.create_run("b", "Follow-up", {}, thread_id="a")
    store.create_run("c", "Unrelated", {})
    threads = {t["thread_id"]: t for t in store.list_threads()}
    assert threads["a"]["turns"] == 2
    assert threads["a"]["title"] == "First question"
    assert threads["c"]["turns"] == 1
    assert [r["id"] for r in store.thread_runs("a")] == ["a", "b"]
    assert store.get_run("b")["thread_id"] == "a"


def test_recall_skips_the_current_conversation():
    store = RunStore(":memory:")
    finished_run(store, "r1", "How are teams cutting LLM inference costs?", "Inference cost tactics",
                 ["https://a.com/caching"])
    assert store.recall("cutting LLM inference costs", exclude_thread="r1") == []


def test_databases_from_before_threads_are_migrated(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, query TEXT NOT NULL, options TEXT NOT NULL, "
                 "status TEXT NOT NULL, created_at REAL NOT NULL, finished_at REAL, title TEXT, result TEXT)")
    conn.execute("INSERT INTO runs VALUES ('old', 'q', '{}', 'completed', 1, 2, 't', NULL)")
    conn.commit()
    conn.close()

    store = RunStore(path)
    assert store.get_run("old")["thread_id"] == "old"
    assert store.list_threads()[0]["thread_id"] == "old"

def test_get_missing_run_returns_none():
    store = RunStore(":memory:")

    assert store.get_run("nonexistent") is None
    assert store.events("nonexistent") == []
    assert store.thread_runs("nonexistent") == []


def test_events_are_isolated_between_runs():
    store = RunStore(":memory:")
    store.create_run("r1", "First research", {})
    store.create_run("r2", "Second research", {})

    store.append_event("r1", {"seq": 1, "type": "started"})
    store.append_event("r2", {"seq": 1, "type": "completed"})
    store.append_event("r1", {"seq": 2, "type": "progress"})

    assert [e["type"] for e in store.events("r1")] == [
        "started",
        "progress",
    ]
    assert [e["type"] for e in store.events("r2")] == ["completed"]


def test_mark_interrupted_only_fails_running_runs():
    store = RunStore(":memory:")
    store.create_run("completed", "Finished research", {})
    store.finish_run("completed", "completed", {"title": "Done"})

    store.create_run("running", "Active research", {})

    assert store.mark_interrupted() == 1
    assert store.get_run("completed")["status"] == "completed"
    assert store.get_run("running")["status"] == "failed"

    assert store.mark_interrupted() == 0


def test_event_with_duplicate_sequence_replaces_previous_payload():
    store = RunStore(":memory:")
    store.create_run("r1", "Research", {})

    store.append_event("r1", {"seq": 1, "type": "started"})
    store.append_event("r1", {"seq": 1, "type": "updated"})

    events = store.events("r1")

    assert len(events) == 1
    assert events[0]["type"] == "updated"
