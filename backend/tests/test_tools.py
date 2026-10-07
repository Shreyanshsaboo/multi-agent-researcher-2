import app.tools.articles as articles
import app.tools.web as web
from app.tools import Finding, make_article_tools, make_hn_tools, make_web_tools
from app.tools.articles import select_passages


async def test_hn_search_formats_stories_and_falls_back_to_discussion_url(make_ctx):
    search, *_ = make_hn_tools(make_ctx())
    out = await search("llm prices")
    assert "Inference prices fell 80% this year" in out
    assert "412 points" in out
    # A text post has no external URL, so the discussion page stands in for it.
    assert "url: https://news.ycombinator.com/item?id=102" in out


async def test_hn_search_reports_empty_results_as_guidance(make_ctx):
    search, *_ = make_hn_tools(make_ctx())
    out = await search("nothing matches")
    assert out.startswith("No Hacker News stories matched")


async def test_story_comments_skips_deleted_and_ranks_by_replies(make_ctx):
    _, _, comments = make_hn_tools(make_ctx())
    out = await comments("101")
    lines = [line for line in out.splitlines() if line.startswith("- ")]
    assert len(lines) == 2
    assert lines[0].startswith("- b (3 replies)")
    assert "<i>" not in out


async def test_findings_are_accepted_only_for_retrieved_urls(make_ctx, evidence, channel):
    ctx = make_ctx()
    search, *_ = make_hn_tools(ctx)
    await search("llm prices")
    out = "\n".join(ctx.save_findings([
        Finding(url="https://blog.example.com/prices", title="Prices",
                key_points=["Inference prices fell 80% this year"]),
        Finding(url="https://invented.example.org/x", title="Made up", key_points=["claim"]),
    ]))
    assert "SAVED https://blog.example.com/prices as E1" in out
    assert "REJECTED https://invented.example.org/x" in out
    assert len(evidence) == 1
    assert ctx.rejected == 1
    rules = [e["rule"] for e in channel.events if e["type"] == "guardrail"]
    assert rules == ["unseen_source"]


async def test_points_with_figures_not_in_source_are_dropped(make_ctx, evidence, channel):
    ctx = make_ctx()
    search, *_ = make_hn_tools(ctx)
    await search("llm prices")
    [out] = ctx.save_findings([
        Finding(url="https://blog.example.com/prices", title="Prices",
                key_points=["Story drew 230 comments", "Prices fell 95% in a week"]),
    ])
    assert "1 ungrounded point(s) dropped" in out
    assert evidence.get("E1").key_points == ["Story drew 230 comments"]
    assert any(e.get("rule") == "ungrounded_figure" for e in channel.events)


async def test_findings_respect_per_task_limit(make_ctx, evidence):
    ctx = make_ctx(max_findings=1)
    search, *_ = make_hn_tools(ctx)
    await search("llm prices")
    out = ctx.save_findings([
        Finding(url="https://blog.example.com/prices", title="A", key_points=["point"]),
        Finding(url="https://news.ycombinator.com/item?id=102", title="B", key_points=["point"]),
    ])
    assert out[1].startswith("SKIPPED")
    assert len(evidence) == 1


async def test_salvage_saves_retrieved_sources_with_tool_text(make_ctx, evidence, channel):
    ctx = make_ctx()
    search, *_ = make_hn_tools(ctx)
    await search("llm prices")
    saved = ctx.salvage(limit=2)
    assert len(saved) == 2 and all(s.startswith("SAVED") for s in saved)
    assert len(evidence) == 2
    assert "412 points" in evidence.get("E1").key_points[0]


async def test_simulated_fault_returns_error_text_and_traces_it(make_ctx, channel):
    ctx = make_ctx(simulate_failure=True)
    search, *_ = make_hn_tools(ctx)
    out = await search("llm prices")
    assert out.startswith("ERROR: search_hackernews failed (SimulatedFault")
    failed = [e for e in channel.events if e.get("phase") == "failed"]
    assert failed and failed[0]["simulated"] is True
    assert ctx.errors


async def test_web_search_filters_sponsored_links(make_ctx, monkeypatch):
    class FakeDDGS:
        def text(self, query, **kwargs):
            return [
                {"title": "Ad", "href": "https://www.bing.com/aclick?ld=x", "body": "buy"},
                {"title": "Real", "href": "https://docs.example.com/pricing", "body": "$0.10/M"},
            ]

    monkeypatch.setattr(web, "DDGS", FakeDDGS)
    ctx = make_ctx(agent_id="web_researcher")
    web_search, _ = make_web_tools(ctx)
    out = await web_search("pricing")
    assert "docs.example.com/pricing" in out
    assert "aclick" not in out
    assert "https://docs.example.com/pricing" in {m for m in ctx.seen}


async def test_read_article_refuses_urls_outside_allowed_set(make_ctx):
    ctx = make_ctx(agent_id="article_reader", allowed_urls={"https://ok.example.com/a"})
    [read_article] = make_article_tools(ctx)
    out = await read_article("https://elsewhere.example.com/b", "anything")
    assert "PermissionError" in out


async def test_read_article_returns_focused_excerpt(make_ctx, monkeypatch):
    body = "\n\n".join(
        ["Lead paragraph introducing the topic of the article at some length."]
        + [f"Filler paragraph number {i} about unrelated gardening matters entirely." for i in range(80)]
        + ["GPU rental pricing dropped to 2 dollars per hour according to the survey."]
    )

    def fake_extract(url):
        return {"title": "Survey", "text": body, "published": "2026-09-01", "authors": []}

    monkeypatch.setattr(articles, "_extract", fake_extract)
    ctx = make_ctx(agent_id="article_reader")
    [read_article] = make_article_tools(ctx)
    out = await read_article("https://survey.example.com", "GPU rental pricing")
    assert "GPU rental pricing dropped" in out
    assert out.count("Filler paragraph") < 80
    assert "[excerpt:" in out
    assert ctx.seen["https://survey.example.com/"].full_text


def test_select_passages_keeps_short_text_whole():
    text = "First paragraph that is long enough to keep.\n\nSecond paragraph that is long enough too."
    excerpt, trimmed = select_passages(text, "anything")
    assert not trimmed
    assert "Second paragraph" in excerpt
