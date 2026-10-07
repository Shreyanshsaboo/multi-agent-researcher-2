import asyncio

from app.events import RunChannel


def test_emit_numbers_events_and_forwards_to_sink():
    stored = []
    channel = RunChannel("r1", sink=lambda run_id, event: stored.append((run_id, event["seq"])))
    channel.emit("run_started", query="q")
    channel.message("coordinator", "hn_scout", "task", "Find stories")
    assert [e["seq"] for e in channel.events] == [1, 2]
    assert stored == [("r1", 1), ("r1", 2)]
    message = channel.events[1]
    assert message["id"] == "m1"
    assert message["recipients"] == ["hn_scout"]


def test_failing_sink_does_not_break_emit():
    def broken_sink(run_id, event):
        raise OSError("disk full")

    channel = RunChannel("r1", sink=broken_sink)
    channel.emit("run_started")
    assert len(channel.events) == 1


async def test_subscriber_gets_backlog_then_live_events_until_close():
    channel = RunChannel("r1")
    channel.emit("run_started")

    received = []

    async def consume():
        async for event in channel.subscribe():
            received.append(event["type"])

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    channel.emit("agent_status", agent="coordinator", state="thinking")
    channel.emit("run_completed")
    channel.close()
    await asyncio.wait_for(consumer, timeout=1)
    assert received == ["run_started", "agent_status", "run_completed"]


async def test_subscribe_after_seq_skips_seen_events_on_closed_channel():
    channel = RunChannel("r1")
    for kind in ("a", "b", "c"):
        channel.emit(kind)
    channel.close()
    received = [e["type"] async for e in channel.subscribe(after=1)]
    assert received == ["b", "c"]
