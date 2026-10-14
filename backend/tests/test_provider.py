import json

import httpx
import pytest

import app.provider as provider
from app.config import Settings
from app.events import ACTIVE_AGENT, RunChannel

QWEN, BIG = "qwen/qwen3.8-27b", "openai/gpt-oss-120b"
# About the size of a worker's second step: its prompt plus a few search results.
REQUEST = {"model": QWEN, "messages": [{"role": "user", "content": "x" * 7000}]}
NEED = len(json.dumps(REQUEST)) / provider.CHARS_PER_TOKEN + provider.REPLY_ALLOWANCE


def scripted(*responses):
    """An upstream that answers with the given responses in order, recording each request."""
    queue = list(responses)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    return httpx.MockTransport(handler), seen


def limited(retry_after: float, scope: str = "input tokens per minute (ITPM)",
            figures: str = "") -> httpx.Response:
    body = {"error": {"message": f"Rate limit reached on {scope}{figures}", "code": "rate_limit_exceeded"}}
    return httpx.Response(429, headers={"retry-after": str(retry_after)}, json=body)


def ok(remaining: int | None = None) -> httpx.Response:
    headers = {}
    if remaining is not None:
        headers = {"x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": str(remaining)}
    return httpx.Response(200, headers=headers, json={"choices": []})


BAD_TOOL_CALL = httpx.Response(400, json={"error": {"message": "Failed to parse tool call arguments as JSON",
                                                  "code": "tool_use_failed"}})


class Clock:
    """Time that only moves when the transport sleeps."""

    def __init__(self):
        self.now = 1000.0
        self.waits: list[float] = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


@pytest.fixture
def channel():
    provider.reset_quota_state()
    channel = RunChannel("r")
    token = ACTIVE_AGENT.set((channel, "web_researcher"))
    log_token = provider.CALL_LOG.set(provider.CallLog())
    yield channel
    provider.CALL_LOG.reset(log_token)
    ACTIVE_AGENT.reset(token)
    provider.reset_quota_state()


def transport(upstream, clock=None, alternates=()):
    clock = clock or Clock()
    return provider.ResilientTransport(upstream, sleep=clock.sleep, clock=clock,
                                       alternates=lambda agent_id: list(alternates))


async def send(transport):
    async with httpx.AsyncClient(transport=transport) as client:
        return await client.post("https://api.example.com/chat", content=json.dumps(REQUEST))


async def test_rejected_request_is_counted_as_spent_before_resending(channel):
    # Groq charges the rejected 3,194 tokens too, so the retry-after it gives is too short:
    # resending then is rejected again, forever. The wait has to cover the rejected request.
    figures = ": Limit 7000, Used 6173, Requested 3194. Please try again in 20.29s."
    upstream, seen = scripted(limited(20.3, figures=figures), ok())
    clock = Clock()

    response = await send(transport(upstream, clock))
    assert response.status_code == 200
    assert len(seen) == 2 and seen[0].content == seen[1].content
    [wait] = clock.waits
    level = 7000 - 6173 - 3194
    assert wait == pytest.approx((NEED - level) / (7000 / 60) + provider.WAIT_MARGIN_S)
    assert wait > 20.3 * 1.5
    [event] = [e for e in channel.events if e["type"] == "rate_limited"]
    assert event["agent"] == "web_researcher" and event["model"] == QWEN
    assert "Used 6173" in event["detail"]


async def test_a_limited_call_moves_to_a_team_model_with_room_instead_of_waiting(channel):
    figures = ": Limit 7000, Used 6900, Requested 3000."
    upstream, seen = scripted(limited(25, figures=figures), ok())
    clock = Clock()

    response = await send(transport(upstream, clock, alternates=[BIG]))
    assert response.status_code == 200
    assert clock.waits == []
    assert json.loads(seen[1].content)["model"] == BIG
    [event] = [e for e in channel.events if e["type"] == "model_fallback"]
    assert (event["primary"], event["fallback"]) == (QWEN, BIG)
    assert provider.CALL_LOG.get().served == {BIG: 1}


async def test_a_model_known_to_be_out_of_tokens_is_not_sent_a_request_it_would_reject(channel):
    # The last response said 100 tokens were left, so the next call goes straight elsewhere.
    upstream, seen = scripted(ok(remaining=100), ok(), ok())
    t = transport(upstream, alternates=[BIG])
    await send(t)
    await send(t)
    await send(t)

    assert [json.loads(r.content)["model"] for r in seen] == [QWEN, BIG, BIG]
    assert len([e for e in channel.events if e["type"] == "model_fallback"]) == 1


async def test_a_short_wait_keeps_the_call_on_its_own_model(channel):
    upstream, seen = scripted(ok(remaining=0), ok())
    clock = Clock()
    t = transport(upstream, clock, alternates=[BIG])
    await send(t)
    clock.now += (NEED - 100) / (8000 / 60)  # 100 tokens short: under a second from fitting
    await send(t)

    assert [json.loads(r.content)["model"] for r in seen] == [QWEN, QWEN]
    assert clock.waits == [pytest.approx(100 / (8000 / 60) + provider.WAIT_MARGIN_S)]


async def test_daily_limit_is_passed_through_and_model_marked_exhausted(channel):
    upstream, seen = scripted(limited(900, "tokens per day (TPD)"))
    clock = Clock()

    response = await send(transport(upstream, clock))
    assert response.status_code == 429
    assert len(seen) == 1 and clock.waits == []
    assert provider.is_exhausted(QWEN)


async def test_daily_limit_moves_the_call_to_a_model_with_quota_left(channel):
    upstream, seen = scripted(limited(900, "tokens per day (TPD)"), ok())
    response = await send(transport(upstream, alternates=[BIG]))
    assert response.status_code == 200
    assert json.loads(seen[1].content)["model"] == BIG


async def test_malformed_tool_call_is_resampled(channel):
    upstream, seen = scripted(BAD_TOOL_CALL, ok())
    response = await send(transport(upstream))
    assert response.status_code == 200
    assert len(seen) == 2
    assert any(e.get("rule") == "malformed_tool_call" for e in channel.events)


async def test_other_client_errors_are_not_retried(channel):
    upstream, seen = scripted(httpx.Response(400, json={"error": {"message": "bad request"}}))
    response = await send(transport(upstream))
    assert response.status_code == 400
    assert len(seen) == 1


async def test_gives_up_after_the_retry_limit(channel):
    upstream, seen = scripted(*[limited(1) for _ in range(provider.MAX_RATE_LIMIT_RETRIES + 1)])
    response = await send(transport(upstream))
    assert response.status_code == 429
    assert len(seen) == provider.MAX_RATE_LIMIT_RETRIES + 1


def test_provider_messages_lose_the_organization_id_and_the_upgrade_pitch():
    message = ("Rate limit reached for model `qwen/qwen3.8-27b` in organization `org_01abc` service tier "
               "`on_demand` on tokens per minute (TPM): Limit 8000, Used 7302, Requested 1853. Please "
               "try again in 8.66s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com")
    assert provider.clean_provider_message(message) == (
        "Rate limit reached for model `qwen/qwen3.8-27b` service tier `on_demand` on tokens per minute "
        "(TPM): Limit 8000, Used 7302, Requested 1853. Please try again in 8.66s.")


def test_the_critic_never_borrows_the_writers_model_family():
    settings = Settings(groq_api_key="k", models={
        "coordinator": BIG, "hn_scout": "openai/gpt-oss-20b", "web_researcher": QWEN,
        "article_reader": "openai/gpt-oss-20b", "writer": BIG, "critic": QWEN,
    })
    assert settings.alternate_models("critic") == []
    assert settings.alternate_models("web_researcher") == [BIG, "openai/gpt-oss-20b"]


def test_a_model_with_an_output_cap_lends_to_no_one():
    # qwen's 1,000 output tokens a minute are kept for the critic, which can run nowhere else.
    settings = Settings(groq_api_key="k")
    for agent_id in ("coordinator", "hn_scout", "web_researcher", "article_reader", "writer"):
        assert QWEN not in settings.alternate_models(agent_id)
    assert settings.alternate_models("coordinator") == ["openai/gpt-oss-20b"]


async def test_an_output_limit_holds_the_model_back_without_shrinking_its_token_budget(channel):
    figures = ": Limit 1000, Used 999, Requested 146. Please try again in 8.7s."
    upstream, seen = scripted(limited(8.7, "output tokens per minute (OTPM)", figures), ok())
    clock = Clock()

    response = await send(transport(upstream, clock))
    assert response.status_code == 200
    assert len(seen) == 2
    assert clock.waits == [pytest.approx(8.7 + provider.WAIT_MARGIN_S)]
    assert provider.bucket(QWEN).capacity == provider.DEFAULT_TOKENS_PER_MIN


@pytest.mark.parametrize("message,expected", [
    (
        "Error in organization `org_private123` while processing request",
        "Error while processing request",
    ),
    (
        "Rate limit exceeded. Need more tokens? Upgrade your plan.",
        "Rate limit exceeded.",
    ),
    (
        "Temporary provider failure",
        "Temporary provider failure",
    ),
])
def test_provider_error_sanitization_edge_cases(message, expected):
    assert provider.clean_provider_message(message) == expected


def test_provider_error_message_handles_plain_text_response():
    response = httpx.Response(
        503,
        text="Provider temporarily unavailable",
    )
    assert provider._error_message(response) == "Provider temporarily unavailable"


def test_provider_error_message_handles_missing_error_field():
    response = httpx.Response(
        400,
        json={"message": "Unexpected response format"},
    )
    assert provider._error_message(response)


def test_provider_error_message_removes_organization_identifier():
    response = httpx.Response(
        429,
        json={
            "error": {
                "message": "Rate limited in organization `org_secret123`"
            }
        },
    )

    message = provider._error_message(response)
    assert "org_secret123" not in message
    assert "Rate limited" in message
