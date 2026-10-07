import json

import httpx
import pytest

import app.provider as provider
from app.events import ACTIVE_AGENT, RunChannel

REQUEST = {"model": "qwen/qwen3.8-27b", "messages": []}


def scripted(*responses):
    """An upstream that answers with the given responses in order, recording each request."""
    queue = list(responses)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    return httpx.MockTransport(handler), seen


def limited(retry_after: float, scope: str = "input tokens per minute (ITPM)") -> httpx.Response:
    body = {"error": {"message": f"Rate limit reached on {scope}", "code": "rate_limit_exceeded"}}
    return httpx.Response(429, headers={"retry-after": str(retry_after)}, json=body)


OK = httpx.Response(200, json={"choices": []})
BAD_TOOL_CALL = httpx.Response(400, json={"error": {"message": "Failed to parse tool call arguments as JSON",
                                                  "code": "tool_use_failed"}})


@pytest.fixture
def channel():
    provider.reset_quota_state()
    channel = RunChannel("r")
    token = ACTIVE_AGENT.set((channel, "web_researcher"))
    yield channel
    ACTIVE_AGENT.reset(token)
    provider.reset_quota_state()


async def send(transport):
    async with httpx.AsyncClient(transport=transport) as client:
        return await client.post("https://api.example.com/chat", content=json.dumps(REQUEST))


async def test_per_minute_limit_waits_past_retry_after_then_resends(channel):
    upstream, seen = scripted(limited(10), OK)
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    response = await send(provider.ResilientTransport(upstream, sleep=fake_sleep))
    assert response.status_code == 200
    assert len(seen) == 2 and seen[0].content == seen[1].content
    assert waits[0] > 10 * 1.15
    [event] = [e for e in channel.events if e["type"] == "rate_limited"]
    assert event["agent"] == "web_researcher" and event["model"] == "qwen/qwen3.8-27b"


async def test_daily_limit_is_passed_through_and_model_marked_exhausted(channel):
    upstream, seen = scripted(limited(900, "tokens per day (TPD)"))

    async def no_sleep(seconds):
        raise AssertionError("must not wait for a daily limit")

    response = await send(provider.ResilientTransport(upstream, sleep=no_sleep))
    assert response.status_code == 429
    assert len(seen) == 1
    assert provider.is_exhausted("qwen/qwen3.8-27b")


async def test_malformed_tool_call_is_resampled(channel):
    upstream, seen = scripted(BAD_TOOL_CALL, OK)
    response = await send(provider.ResilientTransport(upstream))
    assert response.status_code == 200
    assert len(seen) == 2
    assert any(e.get("rule") == "malformed_tool_call" for e in channel.events)


async def test_other_client_errors_are_not_retried(channel):
    upstream, seen = scripted(httpx.Response(400, json={"error": {"message": "bad request"}}))
    response = await send(provider.ResilientTransport(upstream))
    assert response.status_code == 400
    assert len(seen) == 1


async def test_gives_up_after_the_retry_limit(channel):
    upstream, seen = scripted(*[limited(1) for _ in range(provider.MAX_RATE_LIMIT_RETRIES + 1)])

    async def fake_sleep(seconds):
        pass

    response = await send(provider.ResilientTransport(upstream, sleep=fake_sleep))
    assert response.status_code == 429
    assert len(seen) == provider.MAX_RATE_LIMIT_RETRIES + 1
