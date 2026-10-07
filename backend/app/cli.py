"""Run one research query from the terminal and print the agents' messages live.

    python -m app.cli "How are teams cutting LLM inference costs?" --depth quick
    python -m app.cli "..." --fail article_reader --trace trace.json

The full event trace is saved as JSON, the same format the API serves.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from app.config import get_settings
from app.events import RunChannel
from app.runner import RunManager
from app.schemas import WORKER_IDS, RunOptions, RunRequest
from app.store import RunStore

KIND_WIDTH = 9


def _print_event(event: dict) -> None:
    t = f"{event['elapsed']:6.1f}s"
    kind = event["type"]
    if kind == "message":
        to = ",".join(event["recipients"])
        print(f"{t}  {event['sender']:>14} -> {to:<16} {event['kind']:<{KIND_WIDTH}} {event['summary'][:150]}")
    elif kind == "tool_call" and event["phase"] != "started":
        mark = "ok" if event["phase"] == "completed" else f"FAILED {event.get('error', '')[:80]}"
        print(f"{t}  {event['agent']:>14}    tool {event['tool']}({json.dumps(event.get('args', {}))[:80]}) {mark}")
    elif kind in ("guardrail", "agent_error", "rate_limited"):
        detail = event.get("detail") or event.get("error") or f"retry in {event.get('retry_after_s')}s"
        print(f"{t}  {event.get('agent', ''):>14}    [{kind}] {detail[:150]}")
    elif kind == "model_fallback":
        print(f"{t}  {event['agent']:>14}    [fallback] {event['primary']} -> {event['fallback']}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("query")
    parser.add_argument("--depth", choices=["quick", "standard", "deep"], default="quick")
    parser.add_argument("--fail", action="append", choices=WORKER_IDS, default=[],
                        help="simulate an outage of this worker's tools (repeatable)")
    parser.add_argument("--trace", type=Path, help="write the event trace to this JSON file")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.llm_configured:
        print("GROQ_API_KEY is not set (see .env.example).", file=sys.stderr)
        return 2

    store = RunStore(settings.db_path)
    manager = RunManager(settings, store)
    request = RunRequest(query=args.query,
                         options=RunOptions(depth=args.depth, simulate_failures=args.fail))

    def sink(run_id: str, event: dict) -> None:
        store.append_event(run_id, event)
        _print_event(event)

    run_id = "cli-" + uuid.uuid4().hex[:8]
    store.create_run(run_id, request.query, request.options.model_dump())
    channel = RunChannel(run_id, sink=sink)
    result = await manager.execute(run_id, request, channel)

    if args.trace:
        args.trace.write_text(json.dumps(channel.events, indent=2, default=str))
        print(f"\ntrace: {args.trace} ({len(channel.events)} events)")
    if result is None:
        return 1
    print(f"\n=== {result.title} ===  [{result.status}, {result.review_status}, "
          f"score {result.final_score}]\n")
    print(result.report_markdown)
    if result.message:
        print(f"\nNote: {result.message}")
    print(f"\nstats: {result.stats.model_dump()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
