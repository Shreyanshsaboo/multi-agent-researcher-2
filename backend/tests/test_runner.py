from app.runner import CONTEXT_TURNS, conversation_context


def run(query, status="completed", report="An answer [E1].", cited=("E1",)):
    evidence = [{"id": "E1", "url": "https://a.com", "title": "A"},
                {"id": "E2", "url": "https://b.com", "title": "B"}]
    result = {"title": f"About {query}", "report_markdown": report, "cited_ids": list(cited),
              "evidence": evidence} if status == "completed" else None
    return {"query": query, "status": status, "result": result}


def test_context_keeps_completed_turns_with_only_cited_sources():
    turns = conversation_context([run("first"), run("broken", status="failed"), run("second")])
    assert [t["query"] for t in turns] == ["first", "second"]
    assert [e["id"] for e in turns[0]["evidence"]] == ["E1"]
    assert turns[0]["title"] == "About first"


def test_context_is_limited_to_the_most_recent_turns():
    turns = conversation_context([run(f"q{i}") for i in range(CONTEXT_TURNS + 2)])
    assert len(turns) == CONTEXT_TURNS
    assert turns[-1]["query"] == f"q{CONTEXT_TURNS + 1}"
