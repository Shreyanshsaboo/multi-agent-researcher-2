"""Model factory: one place that maps an agent to its provider and model."""

import asyncio
import weakref

import httpx
from agno.models.base import Model
from agno.models.fallback import FallbackConfig
from agno.models.groq import Groq
from agno.models.ollama import Ollama

from app.config import REASONING_EFFORT, Settings
from app.events import ACTIVE_AGENT

_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = (
    weakref.WeakKeyDictionary()
)


async def _report_rate_limit(response: httpx.Response) -> None:
    """Surface 429s in the trace; the Groq client then waits and retries on its own."""
    if response.status_code != 429:
        return
    active = ACTIVE_AGENT.get()
    if active is None:
        return
    channel, agent_id = active
    retry_after = response.headers.get("retry-after")
    await response.aread()
    try:
        detail = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        detail = ""
    channel.emit(
        "rate_limited",
        agent=agent_id,
        retry_after_s=float(retry_after) if retry_after else None,
        detail=detail[:300],
    )
    channel.status(agent_id, "waiting", "rate limited by the model provider, retrying")


def _shared_http_client() -> httpx.AsyncClient | None:
    """One pooled client per event loop, shared by every agent's model."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            event_hooks={"response": [_report_rate_limit]},
        )
        _clients[loop] = client
    return client


def _groq(model_id: str, settings: Settings) -> Groq:
    request_params = None
    if model_id.startswith("openai/gpt-oss"):
        request_params = {"reasoning_effort": REASONING_EFFORT}
    return Groq(
        id=model_id,
        api_key=settings.groq_api_key,
        # The Groq client retries 429s itself and honours retry-after, which rides
        # out per-minute limits; a daily limit falls through to the fallback models.
        max_retries=settings.llm_max_retries,
        timeout=settings.llm_timeout_s,
        temperature=0.2,
        request_params=request_params,
        http_client=_shared_http_client(),
    )


def build_model(agent_id: str, settings: Settings) -> Model:
    model_id = settings.model_for(agent_id)
    if settings.llm_provider == "ollama":
        return Ollama(id=model_id, host=settings.ollama_host)
    return _groq(model_id, settings)


def _report_fallback(primary: str, fallback: str, error: Exception) -> None:
    active = ACTIVE_AGENT.get()
    if active is None:
        return
    channel, agent_id = active
    channel.emit("model_fallback", agent=agent_id, primary=primary, fallback=fallback,
                 detail=str(error)[:300])


def build_fallbacks(agent_id: str, settings: Settings) -> FallbackConfig | None:
    """When an agent's model is rate limited past its retries, try the team's other models.

    Limits are per model, so a model that is out of tokens for the day does not
    take every agent that uses it down with it.
    """
    if settings.llm_provider == "ollama":
        return None
    primary = settings.model_for(agent_id)
    others = [m for m in dict.fromkeys(settings.models.values()) if m != primary]
    if not others:
        return None
    return FallbackConfig(on_rate_limit=[_groq(m, settings) for m in others],
                          callback=_report_fallback)
