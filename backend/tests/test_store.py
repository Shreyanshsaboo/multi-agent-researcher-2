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
