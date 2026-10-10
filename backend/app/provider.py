"""Rate-limit handling for model-provider HTTP calls, applied below the SDK.

The Groq SDK's own retries are turned off and this transport takes over. What
live runs on the free tier showed:

- Every model has its own per-minute token bucket (8,000 tokens; qwen also caps
  input at 7,000), refilled continuously. A request the bucket cannot cover is
  rejected, and the rejected request is charged to the bucket anyway. Resending
  when the 429 says to therefore fails again, every time: one worker spent its
  whole timeout in that loop. So the transport keeps its own estimate of every
  model's bucket, from the headers of each response and the figures in each 429,
  and only sends a request it expects to fit.
- qwen also caps output at 1,000 tokens a minute. That limit has its own
  bucket, which the request size says nothing about, so after an output 429 the
  model is simply held back for as long as the 429 says.
- When the agent's own model has no room, the call goes to a team model that
  has, instead of waiting. All the team's models take the same request
  parameters, so only the request's "model" changes. Waiting is left for when
  no model has room.
- A daily quota is not worth waiting for. The model is remembered as exhausted
  and skipped; with nowhere else to go, the 429 is passed through so the agent's
  fallback models take over.
- gpt-oss models occasionally emit a malformed tool call, which Groq rejects
  with 400 tool_use_failed. Sending the same request again usually samples a
  valid one, which is far cheaper than failing the agent's whole run.
"""

import asyncio
import json
import re
import time
from collections import Counter
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field

import httpx

from app.config import get_settings
from app.events import ACTIVE_AGENT

# A retry-after longer than this means a daily quota, not a per-minute one.
LONG_WAIT_S = 60
MAX_RATE_LIMIT_RETRIES = 6
MAX_TOOL_CALL_RETRIES = 2
# The free tier's tokens per minute, assumed until a model's headers say otherwise.
DEFAULT_TOKENS_PER_MIN = 8000
# A wait this short is not worth moving the call to another model for.
SHORT_WAIT_S = 3.0
# Sleep a little past the estimate, so the request fits when it is sent.
WAIT_MARGIN_S = 0.5
# Tokens are estimated from the request size, generously, plus room for the reply:
# Groq counts the reply it expects against the limit before it is written.
CHARS_PER_TOKEN = 3.5
REPLY_ALLOWANCE = 800

_FIGURES_RE = re.compile(r"Limit (\d+), Used (\d+), Requested (\d+)")


@dataclass
class Bucket:
    """One model's per-minute token bucket as last observed; it refills linearly."""

    limit: float = DEFAULT_TOKENS_PER_MIN
    # A tighter limit on input tokens alone, learned from a 429 (qwen has one).
    input_limit: float | None = None
    level: float = DEFAULT_TOKENS_PER_MIN
    at: float = float("-inf")
    # Held back after an output-tokens 429, which the token level does not cover.
    blocked_until: float = float("-inf")

    @property
    def capacity(self) -> float:
        return min(self.limit, self.input_limit or self.limit)

    def available(self, now: float) -> float:
        return min(self.capacity, self.level + (now - self.at) * self.capacity / 60)

    def wait_for(self, need: float, now: float) -> float:
        refill = max(0.0, min(need, self.capacity) - self.available(now)) * 60 / self.capacity
        return max(refill, self.blocked_until - now)

    def set_level(self, level: float, now: float) -> None:
        self.level, self.at = level, now

    def reserve(self, need: float, now: float) -> None:
        """Count a request as spent when it is sent, so concurrent calls see less room."""
        self.set_level(self.available(now) - need, now)


@dataclass
class CallLog:
    """The models that served one agent call, so its metrics name the right one."""

    served: Counter = field(default_factory=Counter)
    rerouted: set[str] = field(default_factory=set)


CALL_LOG: ContextVar[CallLog | None] = ContextVar("call_log", default=None)

_buckets: dict[str, Bucket] = {}
_exhausted_until: dict[str, float] = {}


def bucket(model_id: str) -> Bucket:
    return _buckets.setdefault(model_id, Bucket())


def mark_exhausted(model_id: str, seconds: float) -> None:
    _exhausted_until[model_id] = time.monotonic() + seconds


def is_exhausted(model_id: str) -> bool:
    return _exhausted_until.get(model_id, 0) > time.monotonic()


def reset_quota_state() -> None:
    _exhausted_until.clear()
    _buckets.clear()


def observe_headers(model_id: str, headers: httpx.Headers, now: float) -> None:
    try:
        limit = float(headers["x-ratelimit-limit-tokens"])
        remaining = float(headers["x-ratelimit-remaining-tokens"])
    except (KeyError, ValueError):
        return
    b = bucket(model_id)
    b.limit = limit
    b.set_level(b.capacity - (limit - remaining), now)


def observe_rejection(model_id: str, message: str, retry_after: float, now: float) -> None:
    """Record a per-minute 429, counting the rejected request as spent, as Groq does."""
    b = bucket(model_id)
    if "output tokens per minute" in message:
        b.blocked_until = max(b.blocked_until, now + retry_after)
        return
    figures = _FIGURES_RE.search(message)
    if figures and "tokens per minute" in message:
        limit, used, requested = map(float, figures.groups())
        if "input tokens per minute" in message:
            b.input_limit = limit
        else:
            b.limit = limit
        b.set_level(b.capacity - used - requested, now)
    else:
        # No figures to go on: wait out retry-after, plus the time to refill what was charged.
        b.set_level(-retry_after * b.capacity / 60, now)


def team_alternates(agent_id: str | None) -> list[str]:
    return get_settings().alternate_models(agent_id) if agent_id else []


def _body(request: httpx.Request) -> dict | None:
    try:
        body = json.loads(request.content)
    except (ValueError, TypeError, httpx.RequestNotRead):
        return None
    return body if isinstance(body, dict) and "model" in body else None


def _with_model(request: httpx.Request, body: dict, model_id: str) -> httpx.Request:
    headers = [(k, v) for k, v in request.headers.raw if k.lower() != b"content-length"]
    return httpx.Request(request.method, request.url, headers=headers,
                         content=json.dumps({**body, "model": model_id}).encode(),
                         extensions=request.extensions)


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


def _status(state: str, detail: str) -> None:
    active = ACTIVE_AGENT.get()
    if active is not None:
        active[0].status(active[1], state, detail)


def route(candidates: list[str], need: float, now: float) -> tuple[str, float]:
    """Pick the model for a call and how long to wait before sending it.

    The first candidate is the agent's own model. It keeps the call when it has
    room, or will within a few seconds; otherwise the model with the most room
    takes it. When none has room, the call waits for whichever frees up first.
    """
    primary = candidates[0]
    usable = [m for m in candidates if not is_exhausted(m)] or [primary]
    waits = {m: bucket(m).wait_for(need, now) for m in usable}
    if primary in waits and waits[primary] <= SHORT_WAIT_S:
        return primary, waits[primary]
    chosen = min(usable, key=lambda m: (waits[m], -bucket(m).available(now)))
    return chosen, waits[chosen]


class ResilientTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        inner: httpx.AsyncBaseTransport | None = None,
        sleep=asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        alternates: Callable[[str | None], list[str]] = team_alternates,
    ) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()
        self._sleep = sleep
        self._clock = clock
        self._alternates = alternates

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = _body(request)
        if body is None:
            return await self._inner.handle_async_request(request)
        model = body["model"]
        active = ACTIVE_AGENT.get()
        candidates = list(dict.fromkeys([model, *self._alternates(active[1] if active else None)]))
        need = len(request.content) / CHARS_PER_TOKEN + REPLY_ALLOWANCE
        rejections = tool_call_attempts = 0
        last_error = ""

        while True:
            chosen, wait = route(candidates, need, self._clock())
            if wait > 0:
                wait += WAIT_MARGIN_S
                _emit("rate_limited", retry_after_s=round(wait, 1), model=chosen,
                      detail=last_error[:300] or f"{chosen} has no tokens left this minute")
                _status("waiting", f"rate limited, retrying in {round(wait)}s")
                await self._sleep(wait)
                last_error = ""
                continue

            bucket(chosen).reserve(need, self._clock())
            outgoing = request if chosen == model else self._reroute(request, body, model, chosen)
            response = await self._inner.handle_async_request(outgoing)
            now = self._clock()
            observe_headers(chosen, response.headers, now)
            if response.status_code not in (400, 429):
                if (log := CALL_LOG.get()) is not None and response.is_success:
                    log.served[chosen] += 1
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
            if retry_after > LONG_WAIT_S:
                mark_exhausted(chosen, retry_after)
                _emit("rate_limited", retry_after_s=retry_after, detail=message[:300], model=chosen)
                if all(is_exhausted(m) for m in candidates):
                    return response
                await response.aclose()
                continue
            if rejections >= MAX_RATE_LIMIT_RETRIES:
                return response
            rejections += 1
            observe_rejection(chosen, message, retry_after, now)
            last_error = message
            await response.aclose()

    def _reroute(self, request: httpx.Request, body: dict, model: str, chosen: str) -> httpx.Request:
        log = CALL_LOG.get()
        if log is None or chosen not in log.rerouted:
            if log is not None:
                log.rerouted.add(chosen)
            _emit("model_fallback", primary=model, fallback=chosen,
                  detail=f"{model} has no tokens left this minute; calls go to {chosen} meanwhile")
        return _with_model(request, body, chosen)

    async def aclose(self) -> None:
        await self._inner.aclose()
