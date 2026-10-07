"""Web and news search for the web researcher, through the keyless ddgs library.

backend="auto" rotates across engines (Bing, DuckDuckGo, Yahoo, ...) and falls
back when one returns nothing, instead of pinning to a single engine that
rate-limits rapid queries.
"""

import asyncio
from typing import Any

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from app.evidence import domain_of
from app.tools.base import SourceMeta, ToolContext

SNIPPET_CHARS = 220
# Sponsored results come back as redirect links rather than the advertiser's page.
_AD_MARKERS = ("bing.com/aclick", "duckduckgo.com/y.js")
TIMELIMITS = {"d", "w", "m", "y"}


def _is_ad(url: str) -> bool:
    return any(marker in url for marker in _AD_MARKERS)


def _search(method: str, query: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Call ddgs, treating "no results" as an empty list rather than an error."""
    try:
        return getattr(DDGS(), method)(query, backend="auto", **kwargs) or []
    except DDGSException as exc:
        if "no results" in str(exc).lower():
            return []
        raise


def _web_results(query: str, max_results: int) -> list[dict[str, Any]]:
    raw = _search("text", query, max_results=max_results + 3)
    results = []
    for r in raw:
        url = r.get("href") or ""
        if url and not _is_ad(url):
            results.append({"title": r.get("title") or domain_of(url), "url": url,
                            "snippet": r.get("body") or "", "date": None})
    return results[:max_results]


def _news_results(query: str, max_results: int, timelimit: str) -> list[dict[str, Any]]:
    raw = _search("news", query, max_results=max_results, timelimit=timelimit)
    results = []
    for r in raw:
        url = r.get("url") or ""
        if url and not _is_ad(url):
            results.append({"title": r.get("title") or domain_of(url), "url": url,
                            "snippet": r.get("body") or "", "date": (r.get("date") or "")[:10],
                            "publisher": r.get("source")})
    return results


def format_results(results: list[dict[str, Any]]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        source = r.get("publisher") or domain_of(r["url"])
        dated = f", {r['date']}" if r.get("date") else ""
        snippet = r["snippet"][:SNIPPET_CHARS] + ("…" if len(r["snippet"]) > SNIPPET_CHARS else "")
        lines.append(f"{i}. {r['title']} ({source}{dated})\n   url: {r['url']}\n   {snippet}")
    return "\n".join(lines)


def _remember(ctx: ToolContext, results: list[dict[str, Any]], source_type: str) -> None:
    for r in results:
        ctx.remember(r["url"], SourceMeta(
            title=r["title"], source_type=source_type, text=f"{r['title']} {r['snippet']}",
            published=r.get("date") or None,
            meta={"publisher": r.get("publisher") or domain_of(r["url"])}))


def make_web_tools(ctx: ToolContext) -> list:
    async def web_search(query: str, max_results: int = 5) -> str:
        """Search the web. Best for facts, official sources, documentation and background.

        Args:
            query: A focused search query.
            max_results: Number of results, 1-8.
        """
        async def body() -> str:
            results = await asyncio.to_thread(_web_results, query, max(1, min(max_results, 8)))
            if not results:
                return f"No web results for '{query}'. Rephrase or broaden the query."
            _remember(ctx, results, "web")
            return format_results(results)

        return await ctx.call("web_search", {"query": query}, body)

    async def news_search(query: str, timelimit: str = "m", max_results: int = 5) -> str:
        """Search recent news articles. Best for current events and anything time-sensitive.

        Args:
            query: A focused search query.
            timelimit: How far back to look: "d" day, "w" week, "m" month, "y" year.
            max_results: Number of results, 1-8.
        """
        async def body() -> str:
            limit = timelimit if timelimit in TIMELIMITS else "m"
            results = await asyncio.to_thread(_news_results, query, max(1, min(max_results, 8)), limit)
            if not results:
                return f"No news in that period for '{query}'. Try a longer timelimit or other terms."
            _remember(ctx, results, "news")
            return format_results(results)

        return await ctx.call("news_search", {"query": query, "timelimit": timelimit}, body)

    return [web_search, news_search]
