"""Hacker News tools for the HN scout, backed by the public Algolia HN API.

Algolia gives keyword search over stories (the official Firebase API has none),
date filtering, and whole comment threads in a single request.
"""

import html
import re
import time
from typing import Any

import httpx

from app.tools.base import SourceMeta, ToolContext, record_findings_tool

ALGOLIA = "https://hn.algolia.com/api/v1"
HN_ITEM = "https://news.ycombinator.com/item?id={}"
_HN_ITEM_RE = re.compile(r"news\.ycombinator\.com/item\?id=(\d+)")
_TAG_RE = re.compile(r"<[^>]+>")
COMMENT_CHARS = 450


def hn_item_id(url: str) -> str | None:
    match = _HN_ITEM_RE.search(url)
    return match.group(1) if match else None


def strip_html(text: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", text or "")).split())


def _story(hit: dict[str, Any]) -> dict[str, Any]:
    story_id = str(hit.get("objectID") or hit.get("id"))
    discussion = HN_ITEM.format(story_id)
    return {
        "id": story_id,
        "title": hit.get("title") or "(untitled)",
        "url": hit.get("url") or discussion,
        "discussion": discussion,
        "points": hit.get("points") or 0,
        "comments": hit.get("num_comments") or 0,
        "date": (hit.get("created_at") or "")[:10],
        "author": hit.get("author"),
    }


async def search_stories(
    http: httpx.AsyncClient,
    query: str,
    *,
    sort: str = "relevance",
    days: int | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    endpoint = "search_by_date" if sort == "recent" else "search"
    params: dict[str, Any] = {"query": query, "tags": "story", "hitsPerPage": limit}
    if days:
        params["numericFilters"] = f"created_at_i>{int(time.time()) - days * 86400}"
    response = await http.get(f"{ALGOLIA}/{endpoint}", params=params, timeout=10)
    response.raise_for_status()
    return [_story(hit) for hit in response.json().get("hits", [])]


async def front_page(http: httpx.AsyncClient, *, limit: int = 10) -> list[dict[str, Any]]:
    params = {"tags": "front_page", "hitsPerPage": limit}
    response = await http.get(f"{ALGOLIA}/search", params=params, timeout=10)
    response.raise_for_status()
    return [_story(hit) for hit in response.json().get("hits", [])]


async def story_thread(
    http: httpx.AsyncClient, story_id: str, *, limit: int = 8
) -> dict[str, Any]:
    response = await http.get(f"{ALGOLIA}/items/{story_id}", timeout=10)
    response.raise_for_status()
    data = response.json()

    comments = []
    for child in data.get("children") or []:
        text = strip_html(child.get("text") or "")
        if not text:
            continue
        comments.append({
            "author": child.get("author") or "anon",
            "text": text[:COMMENT_CHARS] + ("…" if len(text) > COMMENT_CHARS else ""),
            "replies": len(child.get("children") or []),
        })
    # Algolia does not return HN's ranking, so reply count stands in for which
    # top-level comments drew the most discussion.
    comments.sort(key=lambda c: c["replies"], reverse=True)

    story = _story({**data, "num_comments": None})
    story["text"] = strip_html(data.get("text") or "")
    story["comments"] = comments[:limit]
    return story


def format_stories(stories: list[dict[str, Any]]) -> str:
    lines = []
    for i, s in enumerate(stories, 1):
        lines.append(
            f"{i}. {s['title']}\n"
            f"   url: {s['url']}\n"
            f"   hn: {s['discussion']} (story_id {s['id']}) · {s['points']} points · "
            f"{s['comments']} comments · {s['date']}"
        )
    return "\n".join(lines)


def format_thread(thread: dict[str, Any]) -> str:
    parts = [f"STORY: {thread['title']}", f"url: {thread['url']}", f"hn: {thread['discussion']}"]
    if thread.get("text"):
        parts.append(f"POST TEXT: {thread['text'][:1200]}")
    if thread["comments"]:
        parts.append("TOP COMMENTS (by replies):")
        parts += [f"- {c['author']} ({c['replies']} replies): {c['text']}" for c in thread["comments"]]
    else:
        parts.append("No comments yet.")
    return "\n".join(parts)


def _remember_stories(ctx: ToolContext, stories: list[dict[str, Any]]) -> None:
    for s in stories:
        listing = f"{s['title']} {s['points']} points {s['comments']} comments {s['date']}"
        meta = {"hn_id": s["id"], "points": s["points"], "comments": s["comments"],
                "discussion": s["discussion"]}
        ctx.remember(s["url"], SourceMeta(title=s["title"], source_type="hackernews",
                                          text=listing, published=s["date"], meta=meta))
        if s["discussion"] != s["url"]:
            ctx.remember(s["discussion"], SourceMeta(
                title=f"HN discussion: {s['title']}", source_type="hackernews",
                text=listing, published=s["date"], meta=meta))


def make_hn_tools(ctx: ToolContext) -> list:
    async def search_hackernews(
        query: str, sort: str = "relevance", days: int = 0, max_results: int = 8
    ) -> str:
        """Search Hacker News stories by keyword.

        Args:
            query: 2-5 keywords. Short keyword queries match far better than sentences.
            sort: "relevance" for the best matches overall, or "recent" for newest first.
            days: Only stories from the last N days; 0 for no limit.
            max_results: Number of stories to return, 1-10.
        """
        async def body() -> str:
            stories = await search_stories(ctx.http, query, sort=sort, days=days or None,
                                           limit=max(1, min(max_results, 10)))
            if not stories:
                return f"No Hacker News stories matched '{query}'. Try fewer or broader keywords."
            _remember_stories(ctx, stories)
            return format_stories(stories)

        return await ctx.call("search_hackernews",
                              {"query": query, "sort": sort, "days": days}, body)

    async def get_front_page(max_results: int = 10) -> str:
        """Get the stories currently on the Hacker News front page.

        Args:
            max_results: Number of stories to return, 1-15.
        """
        async def body() -> str:
            stories = await front_page(ctx.http, limit=max(1, min(max_results, 15)))
            _remember_stories(ctx, stories)
            return format_stories(stories) or "The front page is empty."

        return await ctx.call("get_front_page", {"max_results": max_results}, body)

    async def get_story_comments(story_id: str, max_comments: int = 8) -> str:
        """Read the most discussed top-level comments of a Hacker News story.

        Args:
            story_id: The numeric story_id shown in search results.
            max_comments: Number of comments to return, 1-10.
        """
        async def body() -> str:
            thread = await story_thread(ctx.http, story_id.strip(),
                                        limit=max(1, min(max_comments, 10)))
            text = format_thread(thread)
            ctx.remember(thread["discussion"], SourceMeta(
                title=f"HN discussion: {thread['title']}", source_type="hackernews",
                text=text, published=thread["date"], full_text=True,
                meta={"hn_id": thread["id"], "comments_read": len(thread["comments"])}))
            return text

        return await ctx.call("get_story_comments", {"story_id": story_id}, body)

    return [search_hackernews, get_front_page, get_story_comments, record_findings_tool(ctx)]
