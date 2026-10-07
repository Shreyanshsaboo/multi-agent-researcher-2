"""Model factory: one place that maps an agent to its provider and model."""

from agno.models.base import Model
from agno.models.groq import Groq
from agno.models.ollama import Ollama

from app.config import REASONING_EFFORT, Settings


def build_model(agent_id: str, settings: Settings) -> Model:
    model_id = settings.model_for(agent_id)

    if settings.llm_provider == "ollama":
        return Ollama(id=model_id, host=settings.ollama_host)

    request_params = None
    if model_id.startswith("openai/gpt-oss"):
        request_params = {"reasoning_effort": REASONING_EFFORT.get(agent_id, "low")}

    return Groq(
        id=model_id,
        api_key=settings.groq_api_key,
        # The Groq client retries 429s itself and honours retry-after, which is
        # what keeps a run alive on the free tier's per-minute token limit.
        max_retries=settings.llm_max_retries,
        timeout=settings.llm_timeout_s,
        temperature=0.2,
        request_params=request_params,
    )
