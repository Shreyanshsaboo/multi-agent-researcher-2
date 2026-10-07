"""Retry policy for model-provider HTTP calls, applied below the SDK.

The Groq SDK's own retries are turned off and this transport takes over, for
three reasons found in live runs on the free tier:

- Rejected requests still count toward Groq's per-minute token limits, so a
  retry sent exactly when the 429 says to can be rejected again, indefinitely.
  Waiting a margin past retry-after breaks that loop.
- A daily quota is not worth waiting for. Those 429s are passed straight
  through so the agent's fallback models take over, and the model is
  remembered as exhausted so later agents skip it.
- gpt-oss models occasionally emit a malformed tool call, which Groq rejects
  with 400 tool_use_failed. Sending the same request again usually samples a
  valid one, which is far cheaper than failing the agent's whole run.

Retrying here resends the identical request, invisibly to the agent framework.
"""

import asyncio
import json
import random
import time

import httpx

from app.events import ACTIVE_AGENT

# A retry-after longer than this means a daily quota, not a per-minute one.
LONG_WAIT_S = 60
MAX_RATE_LIMIT_RETRIES = 6
MAX_TOOL_CALL_RETRIES = 2

_exhausted_until: dict[str, float] = {}


def mark_exhausted(model_id: str, seconds: float) -> None:
    _exhausted_until[model_id] = time.monotonic() + seconds


def is_exhausted(model_id: str) -> bool:
    return _exhausted_until.get(model_id, 0) > time.monotonic()


def reset_quota_state() -> None:
    _exhausted_until.clear()


def _model_of(request: httpx.Request) -> str | None:
    try:
        return json.loads(request.content)["model"]
    except (ValueError, KeyError, TypeError):
        return None


def _error_message(response: httpx.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return response.text[:300]


def _emit(type_: str, **payload) -> None:
    active = ACTIVE_AGENT.get()
    if active is not None:
        channel, agent_id = active
        channel.emit(type_, agent=agent_id, **payload)


def backoff_after(retry_after: float, attempt: int) -> float:
    """Wait past the provider's hint, by more on each attempt, with jitter."""
    return retry_after * (1.15 + 0.1 * attempt) + 1.0 + random.uniform(0, 1.5)


class ResilientTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport | None = None,
                 sleep=asyncio.sleep) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()
        self._sleep = sleep

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        rate_limit_attempts = tool_call_attempts = 0
        while True:
            response = await self._inner.handle_async_request(request)
            if response.status_code not in (400, 429):
                return response

            await response.aread()
            message = _error_message(response)

            if response.status_code == 400:
                if "tool_use_failed" not in response.text or tool_call_attempts >= MAX_TOOL_CALL_RETRIES:
                    return response
                tool_call_attempts += 1
                _emit("guardrail", rule="malformed_tool_call",
                      detail="The model produced a malformed tool call; asking it again.")
                continue

            retry_after = float(response.headers.get("retry-after") or 5)
            model_id = _model_of(request)
            if retry_after > LONG_WAIT_S:
                if model_id:
                    mark_exhausted(model_id, retry_after)
                _emit("rate_limited", retry_after_s=retry_after, detail=message[:300], model=model_id)
                return response
            if rate_limit_attempts >= MAX_RATE_LIMIT_RETRIES:
                return response

            wait = backoff_after(retry_after, rate_limit_attempts)
            rate_limit_attempts += 1
            _emit("rate_limited", retry_after_s=round(wait, 1), detail=message[:300], model=model_id)
            active = ACTIVE_AGENT.get()
            if active is not None:
                active[0].status(active[1], "waiting", f"rate limited, retrying in {round(wait)}s")
            await response.aclose()
            await self._sleep(wait)

    async def aclose(self) -> None:
        await self._inner.aclose()
