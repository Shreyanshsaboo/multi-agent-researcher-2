"""Full-text reading for the article reader.

Articles are extracted with newspaper4k, then cut down to the paragraphs that
match what the reader is looking for (its ``focus``). A whole article would
otherwise be resent on every step of the agent's tool loop, and that alone can
exceed a free-tier tokens-per-minute budget.
"""

import asyncio
import re
from typing import Any

import newspaper

from app.evidence import normalize_url
from app.tools.base import SourceMeta, ToolContext, record_findings_tool
from app.tools.hackernews import format_thread, hn_item_id, story_thread

MAX_CHARS = 3200
MIN_ARTICLE_CHARS = 300
FETCH_TIMEOUT_S = 12
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_STOPWORDS = frozenset(
    "the and for are but not you all any can had her was one our out has have this that with "
    "from they will what when who how why which their there about into more than then them "
    "these those some such only also just like over most other very been were does did".split()
)


class ExtractionError(RuntimeError):
    pass


def _terms(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def select_passages(text: str, focus: str, max_chars: int = MAX_CHARS) -> tuple[str, bool]:
    """Keep the lead paragraph plus the paragraphs that best match ``focus``.

    Paragraphs are returned in their original order so the excerpt still reads
    like the article. Returns the excerpt and whether anything was cut.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if len(p.strip()) > 40]
    if sum(len(p) for p in paragraphs) <= max_chars:
        return "\n\n".join(paragraphs), False

    focus_terms = _terms(focus)
    scored = []
    for index, paragraph in enumerate(paragraphs):
        overlap = len(focus_terms & _terms(paragraph))
        has_figure = bool(re.search(r"\d", paragraph))
        scored.append((overlap + (0.5 if has_figure else 0), index))

    keep = {0}
    used = len(paragraphs[0])
    for _, index in sorted(scored, key=lambda s: (-s[0], s[1])):
        if index in keep:
            continue
        if used + len(paragraphs[index]) > max_chars:
            continue
        keep.add(index)
        used += len(paragraphs[index])
    return "\n\n".join(paragraphs[i] for i in sorted(keep)), True


def _extract(url: str) -> dict[str, Any]:
    config = newspaper.Config()
    config.request_timeout = FETCH_TIMEOUT_S
    config.browser_user_agent = USER_AGENT
    config.fetch_images = False
    config.memoize_articles = False
    article = newspaper.Article(url, config=config)
    article.download()
    article.parse()
    text = (article.text or "").strip()
    if len(text) < MIN_ARTICLE_CHARS:
        raise ExtractionError(
            "no readable article text (likely a paywall, login wall or JavaScript-only page)"
        )
    published = article.publish_date.date().isoformat() if article.publish_date else None
    return {"title": article.title or url, "text": text, "published": published,
            "authors": list(article.authors or [])[:3]}


def make_article_tools(ctx: ToolContext) -> list:
    async def read_article(url: str, focus: str) -> str:
        """Read the full text of one web page and return the passages relevant to your focus.

        Args:
            url: The URL to read. Must be one from your task or the team's evidence.
            focus: What you are looking for in this page, e.g. "pricing figures and dates".
        """
        async def body() -> str:
            if ctx.allowed_urls is not None and normalize_url(url) not in ctx.allowed_urls:
                raise PermissionError(
                    "this URL is not in your task or the evidence store; read only those URLs"
                )
            existing = ctx.evidence.find_by_url(url)

            story_id = hn_item_id(url)
            if story_id:
                thread = await story_thread(ctx.http, story_id, limit=8)
                text = format_thread(thread)
                ctx.remember(url, SourceMeta(
                    title=f"HN discussion: {thread['title']}", source_type="hackernews",
                    text=text, published=thread["date"], full_text=True))
                return text

            data = await asyncio.wait_for(asyncio.to_thread(_extract, url), FETCH_TIMEOUT_S + 8)
            excerpt, trimmed = select_passages(data["text"], focus)
            ctx.remember(url, SourceMeta(
                title=data["title"],
                source_type=existing.source_type if existing else "article",
                text=data["text"],
                published=data["published"],
                full_text=True,
                meta={"chars": len(data["text"])},
            ))
            header = [f"TITLE: {data['title']}", f"URL: {url}"]
            if data["published"]:
                header.append(f"PUBLISHED: {data['published']}")
            if data["authors"]:
                header.append(f"AUTHORS: {', '.join(data['authors'])}")
            note = (f"\n[excerpt: passages most relevant to '{focus}' from "
                    f"{len(data['text'])} characters]" if trimmed else "")
            return "\n".join(header) + "\n---\n" + excerpt + note

        return await ctx.call("read_article", {"url": url, "focus": focus}, body)

    return [read_article, record_findings_tool(ctx)]
