"""HTTP API, live event stream, and the built frontend.

    uvicorn app.main:app --reload        (from backend/)
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.agents import describe_agents
from app.config import BUDGETS, Settings, get_settings
from app.runner import RunManager, SuiteFactory, TooManyRuns, UnknownThread
from app.schemas import RunRequest
from app.store import RunStore
from app.team import build_suite

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

HEARTBEAT_S = 15


def _sse(event: dict) -> str:
    return f"id: {event['seq']}\ndata: {json.dumps(event, default=str)}\n\n"


def _report_markdown(run: dict) -> str:
    result = run["result"] or {}
    lines = [f"# {result.get('title') or run['query']}", "", f"_Query: {run['query']}_", "",
             result.get("report_markdown") or "_No report was produced._"]
    cited = set(result.get("cited_ids") or [])
    sources = [e for e in result.get("evidence", []) if e["id"] in cited]
    if sources:
        lines += ["", "## Sources", ""]
        lines += [f"- [{e['id']}] [{e['title']}]({e['url']})" for e in sources]
    return "\n".join(lines) + "\n"


def create_app(
    settings: Settings | None = None,
    store: RunStore | None = None,
    suite_factory: SuiteFactory = build_suite,
) -> FastAPI:
    settings = settings or get_settings()
    store = store or RunStore(settings.db_path)
    manager = RunManager(settings, store, suite_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store.mark_interrupted()
        yield
        await manager.shutdown()

    app = FastAPI(title="Multi-Agent Researcher", version="0.2.0", lifespan=lifespan)

    def get_run_or_404(run_id: str) -> dict:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, f"run {run_id} not found")
        return run

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "provider": settings.llm_provider,
                "llm_configured": settings.llm_configured, "active_runs": manager.active_count}

    @app.get("/api/agents")
    def agents() -> dict:
        return {"agents": describe_agents(settings),
                "budgets": {depth: asdict(b) for depth, b in BUDGETS.items()}}

    @app.post("/api/runs", status_code=202)
    async def start_run(request: RunRequest) -> dict:
        if not settings.llm_configured:
            raise HTTPException(503, "No LLM is configured: set GROQ_API_KEY on the server.")
        try:
            run_id, thread_id = manager.start(request)
        except TooManyRuns as exc:
            raise HTTPException(429, str(exc)) from exc
        except UnknownThread as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"run_id": run_id, "thread_id": thread_id}

    @app.get("/api/runs")
    def list_runs(limit: int = 20) -> dict:
        return {"runs": store.list_runs(min(max(limit, 1), 100))}

    @app.get("/api/threads")
    def list_threads(limit: int = 30) -> dict:
        return {"threads": store.list_threads(min(max(limit, 1), 100))}

    @app.get("/api/threads/{thread_id}")
    def get_thread(thread_id: str) -> dict:
        runs = store.thread_runs(thread_id)
        if not runs:
            raise HTTPException(404, f"conversation {thread_id} not found")
        return {"thread_id": thread_id,
                "runs": [{k: run[k] for k in ("id", "query", "status", "created_at", "title")}
                         for run in runs]}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        return get_run_or_404(run_id)

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(
        run_id: str,
        request: Request,
        after: int = 0,
        last_event_id: str | None = Header(default=None),
    ) -> StreamingResponse:
        get_run_or_404(run_id)
        # EventSource sends Last-Event-ID when it reconnects; resume from there.
        if last_event_id and last_event_id.isdigit():
            after = int(last_event_id)

        async def stream() -> AsyncIterator[str]:
            channel = manager.channel(run_id)
            if channel is None:
                for event in store.events(run_id, after):
                    yield _sse(event)
            else:
                async for event in channel.subscribe(after, heartbeat=HEARTBEAT_S):
                    if await request.is_disconnected():
                        return
                    yield ": keep-alive\n\n" if event is None else _sse(event)
            yield "event: end\ndata: {}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/runs/{run_id}/trace")
    def download_trace(run_id: str) -> JSONResponse:
        run = get_run_or_404(run_id)
        channel = manager.channel(run_id)
        events = list(channel.events) if channel else store.events(run_id)
        return JSONResponse(
            {"run": {k: v for k, v in run.items() if k != "result"}, "events": events},
            headers={"Content-Disposition": f'attachment; filename="trace-{run_id}.json"'},
        )

    @app.get("/api/runs/{run_id}/report.md")
    def download_report(run_id: str) -> PlainTextResponse:
        run = get_run_or_404(run_id)
        return PlainTextResponse(
            _report_markdown(run), media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="report-{run_id}.md"'},
        )

    dist = settings.frontend_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
