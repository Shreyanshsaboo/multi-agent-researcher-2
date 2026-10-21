"""Starts runs in the background and wires each one together.

A run gets its own event channel (persisted to the store as it goes), its own
evidence store and HTTP client, and a fresh set of agents. The manager also
caps how many runs execute at once, since they share the model rate limits.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict

import httpx

from app.agents import describe_agents
from app.config import BUDGETS, Settings
from app.events import RunChannel
from app.evidence import EvidenceStore
from app.orchestrator import AgentSuite, Orchestrator
from app.schemas import RunRequest, RunResult
from app.store import RunStore
from app.team import build_suite

log = logging.getLogger(__name__)

SuiteFactory = Callable[..., AgentSuite]
HTTP_HEADERS = {"User-Agent": "multi-agent-researcher/0.2 (+https://github.com/Shreyanshsaboo)"}


class TooManyRuns(RuntimeError):
    pass


class UnknownThread(LookupError):
    pass


# How much of a conversation a follow-up carries forward.
CONTEXT_TURNS = 3
CONTEXT_SOURCES_PER_TURN = 8
SUMMARY_CHARS = 700


def conversation_context(runs: list[dict]) -> list[dict]:
    """Earlier completed turns of a thread: question, answer summary and cited sources."""
    turns = []
    for run in runs:
        result = run.get("result") or {}
        if run["status"] != "completed" or not result.get("report_markdown"):
            continue
        cited = set(result.get("cited_ids") or [])
        sources = [e for e in result.get("evidence", []) if e["id"] in cited]
        turns.append({
            "query": run["query"],
            "title": result.get("title") or "",
            "summary": " ".join(result["report_markdown"].split())[:SUMMARY_CHARS],
            "evidence": sources[:CONTEXT_SOURCES_PER_TURN],
        })
    return turns[-CONTEXT_TURNS:]


class RunManager:
    def __init__(self, settings: Settings, store: RunStore,
                 suite_factory: SuiteFactory = build_suite) -> None:
        self.settings = settings
        self.store = store
        self.suite_factory = suite_factory
        self._channels: dict[str, RunChannel] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    def channel(self, run_id: str) -> RunChannel | None:
        return self._channels.get(run_id)

    def start(self, request: RunRequest) -> tuple[str, str]:
        """Start a run in the background; returns its run id and thread id."""
        if self.active_count >= self.settings.max_active_runs:
            raise TooManyRuns(f"{self.active_count} runs are already in progress; try again shortly")
        # Anyone can start runs on a public deployment; this keeps them from spending the daily quota.
        if self.store.runs_since(time.time() - 86400) >= self.settings.max_runs_per_day:
            raise TooManyRuns(f"the limit of {self.settings.max_runs_per_day} runs a day is reached; "
                              "try again later")
        conversation: list[dict] = []
        if request.thread_id:
            earlier = self.store.thread_runs(request.thread_id)
            if not earlier:
                raise UnknownThread(f"conversation {request.thread_id} not found")
            conversation = conversation_context(earlier)
        run_id = uuid.uuid4().hex[:12]
        thread_id = request.thread_id or run_id
        self.store.create_run(run_id, request.query, request.options.model_dump(), thread_id)
        channel = RunChannel(run_id, sink=self.store.append_event)
        self._channels[run_id] = channel
        self._tasks[run_id] = asyncio.create_task(
            self.execute(run_id, request, channel, thread_id=thread_id, conversation=conversation))
        return run_id, thread_id

    async def execute(
        self,
        run_id: str,
        request: RunRequest,
        channel: RunChannel,
        *,
        thread_id: str | None = None,
        conversation: list[dict] | None = None,
    ) -> RunResult | None:
        budget = BUDGETS[request.options.depth]
        channel.emit("run_started", run_id=run_id, thread_id=thread_id or run_id,
                     query=request.query, options=request.options.model_dump(),
                     budget=asdict(budget), agents=describe_agents(self.settings),
                     follow_up=bool(conversation))
        try:
            async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True) as http:
                evidence = EvidenceStore()
                suite = self.suite_factory(settings=self.settings, channel=channel,
                                           evidence=evidence, http=http, budget=budget,
                                           options=request.options)
                orchestrator = Orchestrator(
                    run_id=run_id, query=request.query, depth=request.options.depth,
                    budget=budget, channel=channel, suite=suite, evidence=evidence,
                    related=self.store.recall(request.query, exclude=run_id,
                                              exclude_thread=thread_id),
                    conversation=conversation,
                )
                result = await orchestrator.run()
            self.store.finish_run(run_id, result.status, result.model_dump())
            channel.emit("run_completed", result=result.model_dump())
            return result
        except asyncio.CancelledError:
            self.store.finish_run(run_id, "failed", None)
            channel.emit("run_failed", error="run was cancelled")
            raise
        except Exception as exc:
            log.exception("run %s failed", run_id)
            self.store.finish_run(run_id, "failed", None)
            channel.emit("run_failed", error=f"{type(exc).__name__}: {exc}")
            return None
        finally:
            channel.close()
            self._tasks.pop(run_id, None)
            self._channels.pop(run_id, None)

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
