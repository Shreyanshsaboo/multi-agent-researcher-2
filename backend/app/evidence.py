"""The shared evidence store (the team's blackboard of sources) and citation checks.

Workers write to it through their record_finding tool, the writer cites its ids,
and the critic checks those citations against it. Sources are keyed by a
normalised URL, so when the article reader reads a story the HN scout already
found, the two findings merge into one evidence item instead of two.
"""

import re
from collections.abc import Iterable
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.schemas import CitationCheck, Evidence

CITATION_RE = re.compile(r"\[(E\d+)\]")
_TRACKING_PREFIXES = ("utm_", "ref", "fbclid", "gclid")
MAX_KEY_POINTS = 6


def normalize_url(url: str) -> str:
    """Canonical form used to decide whether two URLs are the same source."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(_TRACKING_PREFIXES)]
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))


def domain_of(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def closest_url(url: str, known: Iterable[str], cutoff: float = 0.95) -> str | None:
    """The known (normalised) URL that ``url`` refers to, if any.

    Models sometimes drop or change a word when copying a long URL, which turns a
    read of a known source into a refused one. A near-identical URL on the same
    site is taken to mean that source; an ambiguous or distant one never is.
    """
    key = normalize_url(url)
    if key in known:
        return key
    site = domain_of(key)
    scored = sorted(((SequenceMatcher(None, key, k).ratio(), k) for k in known
                     if domain_of(k) == site), reverse=True)
    if not scored or scored[0][0] < cutoff:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.02:
        return None
    return scored[0][1]


class EvidenceStore:
    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}
        self._by_url: dict[str, str] = {}

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, evidence_id: str) -> bool:
        return evidence_id in self._items

    def all(self) -> list[Evidence]:
        return list(self._items.values())

    def get(self, evidence_id: str) -> Evidence | None:
        return self._items.get(evidence_id)

    def find_by_url(self, url: str) -> Evidence | None:
        evidence_id = self._by_url.get(normalize_url(url))
        return self._items.get(evidence_id) if evidence_id else None

    def known_urls(self) -> set[str]:
        return set(self._by_url)

    def add(
        self,
        *,
        url: str,
        title: str,
        source_type: str,
        agent: str,
        key_points: list[str],
        full_text_read: bool = False,
        published: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> tuple[Evidence, bool]:
        """Add a source, or merge into the existing item for the same URL.

        Returns the item and whether it was newly created.
        """
        key = normalize_url(url)
        points = [p.strip() for p in key_points if p and p.strip()]

        existing_id = self._by_url.get(key)
        if existing_id:
            item = self._items[existing_id]
            for point in points:
                if point not in item.key_points and len(item.key_points) < MAX_KEY_POINTS:
                    item.key_points.append(point)
            if agent not in item.found_by:
                item.found_by.append(agent)
            item.full_text_read = item.full_text_read or full_text_read
            item.published = item.published or published
            item.meta.update(meta or {})
            return item, False

        item = Evidence(
            id=f"E{len(self._items) + 1}",
            url=url,
            title=title.strip() or domain_of(url),
            source_type=source_type,
            found_by=[agent],
            key_points=points[:MAX_KEY_POINTS],
            full_text_read=full_text_read,
            published=published,
            meta=meta or {},
        )
        self._items[item.id] = item
        self._by_url[key] = item.id
        return item, True

    # -------------------------------------------------------------- rendering

    def render_index(self, title_chars: int = 80) -> str:
        """One line per source, for the coordinator, which routes but never writes."""
        if not self._items:
            return "(empty)"
        lines = []
        for e in self._items.values():
            flags = [e.source_type, domain_of(e.url), "by " + "+".join(e.found_by)]
            if e.full_text_read:
                flags.append("full text read")
            title = e.title if len(e.title) <= title_chars else e.title[: title_chars - 1] + "…"
            lines.append(f"[{e.id}] {title} ({', '.join(flags)}) {e.url}")
        return "\n".join(lines)

    def render_full(self, max_points: int = 4) -> str:
        """Every source with its key points, for the writer and the critic."""
        if not self._items:
            return "(empty)"
        blocks = []
        for e in self._items.values():
            header = f"[{e.id}] {e.title}"
            details = [e.source_type, domain_of(e.url)]
            if e.published:
                details.append(e.published)
            if e.full_text_read:
                details.append("full text read")
            points = "\n".join(f"  - {p}" for p in e.key_points[:max_points])
            blocks.append(f"{header} ({', '.join(details)})\n{points}")
        return "\n".join(blocks)


def check_citations(markdown: str, store: EvidenceStore) -> CitationCheck:
    """Deterministic checks the critic gets alongside its own reading of a draft."""
    cited = list(dict.fromkeys(CITATION_RE.findall(markdown)))
    unknown = [c for c in cited if c not in store]

    uncited = []
    for block in re.split(r"\n\s*\n", markdown):
        text = block.strip()
        # Headings, short lines and the limitations section are allowed to go uncited.
        if not text or text.startswith("#") or len(text) < 120:
            continue
        if "open question" in text.lower() or "limitation" in text.lower():
            continue
        if not CITATION_RE.search(text):
            uncited.append(text[:140])

    return CitationCheck(
        cited_ids=cited,
        unknown_ids=unknown,
        uncited_paragraphs=uncited,
        evidence_total=len(store),
    )
