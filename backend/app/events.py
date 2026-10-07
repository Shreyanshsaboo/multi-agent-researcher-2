"""The event channel for one run, which doubles as its execution trace.

Every inter-agent message, tool call, status change and metric is appended here
in order. Events go to an optional sink (the SQLite store) as they happen and are
fanned out to live subscribers (the SSE stream the frontend reads).
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextvars import ContextVar
from typing import Any

log = logging.getLogger(__name__)

TERMINAL_EVENTS = frozenset({"run_completed", "run_failed"})

Sink = Callable[[str, dict[str, Any]], None]

# The agent whose LLM call is in flight, so code far from the run loop (the HTTP
# client's rate-limit hook) can attribute what it sees to the right agent.
ACTIVE_AGENT: ContextVar[tuple["RunChannel", str] | None] = ContextVar("active_agent", default=None)


class RunChannel:
    def __init__(self, run_id: str, sink: Sink | None = None) -> None:
        self.run_id = run_id
        self.events: list[dict[str, Any]] = []
        self.closed = False
        self._sink = sink
        self._subscribers: set[asyncio.Queue] = set()
        self._started = time.monotonic()
        self._message_count = 0

    # ------------------------------------------------------------------ emitting

    def emit(self, type: str, **payload: Any) -> dict[str, Any]:
        event = {
            "seq": len(self.events) + 1,
            "ts": time.time(),
            "elapsed": round(time.monotonic() - self._started, 2),
            "type": type,
            **payload,
        }
        self.events.append(event)
        if self._sink:
            try:
                self._sink(self.run_id, event)
            except Exception:  # a storage hiccup must not take the run down with it
                log.exception("failed to persist event %s for run %s", event["seq"], self.run_id)
        for queue in self._subscribers:
            queue.put_nowait(event)
        return event

    def message(
        self,
        sender: str,
        recipient: str | list[str],
        kind: str,
        summary: str,
        content: Any = None,
    ) -> dict[str, Any]:
        """Record one message passed between agents (or between the user and an agent)."""
        self._message_count += 1
        recipients = recipient if isinstance(recipient, list) else [recipient]
        return self.emit(
            "message",
            id=f"m{self._message_count}",
            sender=sender,
            recipients=recipients,
            kind=kind,
            summary=summary,
            content=content,
        )

    def status(self, agent: str, state: str, detail: str = "") -> None:
        self.emit("agent_status", agent=agent, state=state, detail=detail)

    def close(self) -> None:
        self.closed = True
        for queue in self._subscribers:
            queue.put_nowait(None)

    # --------------------------------------------------------------- subscribing

    async def subscribe(self, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        """Replay events after ``after``, then follow live ones until the run ends.

        The backlog snapshot and the queue registration happen with no await in
        between, so on a single event loop no event can fall in the gap.
        """
        backlog = self.events[after:]
        if self.closed:
            for event in backlog:
                yield event
            return

        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            for event in backlog:
                yield event
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
        finally:
            self._subscribers.discard(queue)
