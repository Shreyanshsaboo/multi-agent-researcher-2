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

async def test_closed_channel_replays_events_without_registering_subscriber():
    channel = RunChannel("closed-run")
    channel.emit("run_started")
    channel.emit("run_completed")
    channel.close()

    received = [event async for event in channel.subscribe()]

    assert [event["seq"] for event in received] == [1, 2]
    assert channel._subscribers == set()

async def test_multiple_subscribers_receive_same_live_event():
    channel = RunChannel("multi-run")
    received = []

    async def consume(name):
        async for event in channel.subscribe():
            received.append((name, event["type"]))

    first = asyncio.create_task(consume("first"))
    second = asyncio.create_task(consume("second"))
    await asyncio.sleep(0)

    channel.emit("agent_status", agent="writer", state="working")
    channel.close()

    await asyncio.wait_for(asyncio.gather(first, second), timeout=1)

    assert ("first", "agent_status") in received
    assert ("second", "agent_status") in received
    assert channel._subscribers == set()


async def test_subscriber_cleanup_when_consumer_is_cancelled():
    channel = RunChannel("cancel-run")

    async def consume():
        async for _ in channel.subscribe():
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)

    assert len(channel._subscribers) == 1

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert channel._subscribers == set()


async def test_closed_channel_with_no_new_events_returns_empty_replay():
    channel = RunChannel("empty-run")
    channel.emit("run_started")
    channel.close()

    received = [event async for event in channel.subscribe(after=1)]

    assert received == []
