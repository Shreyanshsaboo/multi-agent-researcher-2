"""Model factory: one place that maps an agent to its provider, model and fallbacks."""

import asyncio
import weakref

import httpx
from agno.models.base import Model
from agno.models.fallback import FallbackConfig
from agno.models.groq import Groq
from agno.models.ollama import Ollama

from app.config import REASONING_EFFORT, Settings
from app.events import ACTIVE_AGENT, RunChannel
from app.provider import ResilientTransport, clean_provider_message, is_exhausted

_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = (
    weakref.WeakKeyDictionary()
)


def _shared_http_client() -> httpx.AsyncClient | None:
    """One pooled client per event loop, shared by every agent's model."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0),
                                   transport=ResilientTransport())
        _clients[loop] = client
    return client


def _groq(model_id: str, settings: Settings) -> Groq:
    request_params = None
    if model_id.startswith("openai/gpt-oss"):
        request_params = {"reasoning_effort": REASONING_EFFORT}
    return Groq(
        id=model_id,
        api_key=settings.groq_api_key,
        # Retries happen in ResilientTransport instead (see app/provider.py).
        max_retries=0,
        timeout=settings.llm_timeout_s,
        temperature=0.2,
        request_params=request_params,
        http_client=_shared_http_client(),
    )


def _report_fallback(primary: str, fallback: str, error: Exception) -> None:
    active = ACTIVE_AGENT.get()
    if active is None:
        return
    channel, agent_id = active
    channel.emit("model_fallback", agent=agent_id, primary=primary, fallback=fallback,
                 detail=clean_provider_message(str(error))[:300])


def build_model_chain(
    agent_id: str, settings: Settings, channel: RunChannel | None = None
) -> tuple[Model, FallbackConfig | None]:
    """The agent's model plus the team's other models as rate-limit fallbacks.

    Limits are per model, so a model that is out of tokens for the day does not
    take every agent that uses it down with it. A model known to be exhausted is
    skipped up front rather than retried on every call.
    """
    primary = settings.model_for(agent_id)
    if settings.llm_provider == "ollama":
        return Ollama(id=primary, host=settings.ollama_host), None

    order = [primary] + [m for m in dict.fromkeys(settings.models.values()) if m != primary]
    chosen = next((m for m in order if not is_exhausted(m)), primary)
    if chosen != primary and channel is not None:
        channel.emit("model_fallback", agent=agent_id, primary=primary, fallback=chosen,
                     detail=f"{primary} is out of its daily token quota")
    rest = [m for m in order if m != chosen]
    fallbacks = FallbackConfig(on_rate_limit=[_groq(m, settings) for m in rest],
                               callback=_report_fallback) if rest else None
    return _groq(chosen, settings), fallbacks
