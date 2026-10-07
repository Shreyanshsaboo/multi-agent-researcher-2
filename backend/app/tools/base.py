"""The per-task environment every worker's tools run in.

All tool calls go through ``ToolContext.call``, which times the call, records it
in the run trace, applies fault injection, and turns exceptions into an error
string the agent reads and reacts to (rather than crashing the run).

The context also remembers every URL a tool returned, along with the text it
returned for it. The findings a worker reports are checked against that: a
worker can only save a source it actually retrieved, and any figure in a key
point has to appear in the retrieved text.
"""

import itertools
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.events import RunChannel
from app.evidence import EvidenceStore, normalize_url

MAX_POINTS_PER_FINDING = 4
MAX_POINT_CHARS = 300
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


class SimulatedFault(RuntimeError):
    """Raised by fault injection, so the trace can tell a staged outage from a real one."""


@dataclass
class SourceMeta:
    title: str
    source_type: str
    text: str = ""
    url: str = ""
    published: str | None = None
    full_text: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


class Finding(BaseModel):
    url: str = Field(description="Source URL exactly as one of your tools returned it.")
    title: str = Field(description="Short title of the source.")
    key_points: list[str] = Field(
        description="1-4 specific facts, figures or attributed opinions taken from the source."
    )


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER_RE.findall(text)}


class ToolContext:
    def __init__(
        self,
        *,
        channel: RunChannel,
        agent_id: str,
        task_id: str,
        evidence: EvidenceStore,
        http: httpx.AsyncClient,
        max_findings: int = 5,
        simulate_failure: bool = False,
        allowed_urls: set[str] | None = None,
    ) -> None:
        self.channel = channel
        self.agent_id = agent_id
        self.task_id = task_id
        self.evidence = evidence
        self.http = http
        self.max_findings = max_findings
        self.simulate_failure = simulate_failure
        # Normalised URLs this worker may read; None means unrestricted.
        self.allowed_urls = allowed_urls
        self.seen: dict[str, SourceMeta] = {}
        self.evidence_ids: list[str] = []
        self.tool_calls = 0
        self.rejected = 0
        self.errors: list[str] = []
        self._call_ids = itertools.count(1)

    def remember(self, url: str, meta: SourceMeta) -> None:
        meta.url = url
        key = normalize_url(url)
        previous = self.seen.get(key)
        if previous:
            meta.text = f"{previous.text}\n{meta.text}".strip()
            meta.full_text = meta.full_text or previous.full_text
        self.seen[key] = meta

    async def call(
        self,
        tool: str,
        args: dict[str, Any],
        body: Callable[[], Awaitable[str]],
        *,
        faultable: bool = True,
    ) -> str:
        self.tool_calls += 1
        call_id = f"{self.task_id}.{next(self._call_ids)}"
        common = {"agent": self.agent_id, "task_id": self.task_id, "call_id": call_id, "tool": tool}
        self.channel.emit("tool_call", phase="started", args=args, **common)
        started = time.monotonic()
        try:
            if faultable and self.simulate_failure:
                raise SimulatedFault(f"{tool} is unavailable (simulated outage)")
            result = await body()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
            self.errors.append(f"{tool}: {error}")
            self.channel.emit(
                "tool_call",
                phase="failed",
                error=error,
                simulated=isinstance(exc, SimulatedFault),
                duration_ms=int((time.monotonic() - started) * 1000),
                **common,
            )
            return (
                f"ERROR: {tool} failed ({error}). Try a different query or approach, "
                "or report the failure in your final answer."
            )
        self.channel.emit(
            "tool_call",
            phase="completed",
            preview=result[:400],
            duration_ms=int((time.monotonic() - started) * 1000),
            **common,
        )
        return result

    # ------------------------------------------------------------- findings

    def _guardrail(self, rule: str, detail: str) -> None:
        self.channel.emit(
            "guardrail", agent=self.agent_id, task_id=self.task_id, rule=rule, detail=detail
        )

    def _save(self, finding: Finding) -> str:
        meta = self.seen.get(normalize_url(finding.url))
        if meta is None:
            self._guardrail("unseen_source", f"Rejected {finding.url}: no tool returned it.")
            return f"REJECTED {finding.url}: not returned by any of your tools; use exact URLs."

        if len(self.evidence_ids) >= self.max_findings:
            return f"SKIPPED {finding.url}: finding limit ({self.max_findings}) reached."

        source_numbers = _numbers(meta.text) if meta.text else None
        points, dropped = [], []
        for raw in finding.key_points[:MAX_POINTS_PER_FINDING]:
            point = " ".join(raw.split())[:MAX_POINT_CHARS]
            if not point:
                continue
            # Figures are where hallucinations do the most damage, so every number
            # in a point has to appear somewhere in the text the tool returned.
            if source_numbers is not None and not _numbers(point) <= source_numbers:
                dropped.append(point)
                continue
            points.append(point)

        if dropped:
            self._guardrail(
                "ungrounded_figure",
                f"Dropped {len(dropped)} point(s) for {finding.url} with figures not in the source: "
                + " | ".join(dropped),
            )
        if not points:
            return f"REJECTED {finding.url}: no key point was supported by the retrieved text."

        item, created = self.evidence.add(
            url=finding.url,
            title=meta.title or finding.title,
            source_type=meta.source_type,
            agent=self.agent_id,
            key_points=points,
            full_text_read=meta.full_text,
            published=meta.published,
            meta=meta.meta,
        )
        if item.id not in self.evidence_ids:
            self.evidence_ids.append(item.id)
        self.channel.emit(
            "evidence", agent=self.agent_id, task_id=self.task_id, created=created,
            item=item.model_dump(),
        )
        note = f" ({len(dropped)} ungrounded point(s) dropped)" if dropped else ""
        merged = " (merged into an existing source)" if not created else ""
        return f"SAVED {finding.url} as {item.id}{merged}{note}"

    def save_findings(self, findings: list[Finding]) -> list[str]:
        """Validate and store the findings a worker reported; returns one outcome line each."""
        outcomes = [self._save(f) for f in findings]
        self.rejected += sum(o.startswith("REJECTED") for o in outcomes)
        return outcomes

    def salvage(self, limit: int = 3) -> list[str]:
        """Save raw sources from tool output when the agent failed before reporting.

        The key point is the tool's own text for the source, so it is grounded by
        construction, but it has not been read or summarised by the agent.
        """
        ranked = sorted(self.seen.items(), key=lambda kv: not kv[1].full_text)
        saved = []
        for _, meta in ranked:
            if len(self.evidence_ids) >= min(limit, self.max_findings):
                break
            if not meta.text:
                continue
            point = " ".join(meta.text.split())[:MAX_POINT_CHARS]
            saved.append(self._save(Finding(url=meta.url, title=meta.title, key_points=[point])))
        return saved
