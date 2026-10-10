"""Runtime settings, read once from the environment (and .env in development)."""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env")

AGENT_IDS = (
    "coordinator",
    "hn_scout",
    "web_researcher",
    "article_reader",
    "writer",
    "critic",
)

# Groq rate limits are per model, so the agents are spread over three models to
# keep one run inside the free tier's tokens-per-minute. The critic runs on a
# different model family from the writer so it does not share its blind spots.
DEFAULT_MODELS = {
    "coordinator": "openai/gpt-oss-120b",
    "hn_scout": "openai/gpt-oss-20b",
    "web_researcher": "qwen/qwen3.8-27b",
    "article_reader": "openai/gpt-oss-20b",
    "writer": "openai/gpt-oss-120b",
    "critic": "qwen/qwen3.8-27b",
}

# On the free tier qwen also caps output at 1,000 tokens a minute, and Groq refuses
# a call whose expected output exceeds that, judged by recent replies. So qwen never
# takes the writer's long drafts: one would stall the critic, which only runs on qwen.
OUTPUT_CAPPED_MODELS = frozenset({"qwen/qwen3.8-27b"})
LONG_REPLY_AGENTS = frozenset({"writer"})

# Only the gpt-oss models take reasoning_effort. Reasoning tokens count against
# the per-minute rate limit, and "low" was enough for routing and writing in testing.
REASONING_EFFORT = "low"


@dataclass(frozen=True)
class Budget:
    """Hard limits for one run. The coordinator sees these and plans within them."""

    max_turns: int
    max_drafts: int
    max_tasks_per_turn: int
    max_findings_per_task: int
    max_urls_per_read: int
    time_limit_s: int


BUDGETS = {
    "quick": Budget(max_turns=5, max_drafts=2, max_tasks_per_turn=2,
                    max_findings_per_task=4, max_urls_per_read=2, time_limit_s=360),
    "standard": Budget(max_turns=8, max_drafts=3, max_tasks_per_turn=3,
                       max_findings_per_task=5, max_urls_per_read=3, time_limit_s=600),
    "deep": Budget(max_turns=12, max_drafts=4, max_tasks_per_turn=3,
                   max_findings_per_task=6, max_urls_per_read=3, time_limit_s=900),
}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "groq"
    groq_api_key: str | None = None
    ollama_host: str | None = None
    ollama_model: str = "llama3.2"
    models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    llm_timeout_s: int = 60
    # Generous, because on a free tier most of an agent's time is rate-limit waits.
    agent_timeout_s: int = 240
    max_active_runs: int = 2
    db_path: Path = BACKEND_DIR / "data" / "runs.db"
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

    @property
    def llm_configured(self) -> bool:
        return self.llm_provider == "ollama" or bool(self.groq_api_key)

    def model_for(self, agent_id: str) -> str:
        if self.llm_provider == "ollama":
            return self.ollama_model
        return self.models[agent_id]

    def alternate_models(self, agent_id: str) -> list[str]:
        """Team models that may take an agent's calls while its own is out of tokens.

        The critic only borrows from model families the writer does not use, so a
        draft is never reviewed by the family that wrote it.
        """
        if self.llm_provider == "ollama" or agent_id not in self.models:
            return []
        primary = self.models[agent_id]
        others = [m for m in dict.fromkeys(self.models.values()) if m != primary]
        if agent_id in LONG_REPLY_AGENTS:
            others = [m for m in others if m not in OUTPUT_CAPPED_MODELS]
        if agent_id == "critic":
            writer_family = self.models["writer"].split("/")[0]
            others = [m for m in others if m.split("/")[0] != writer_family]
        return others


@lru_cache
def get_settings() -> Settings:
    # MODEL_<AGENT_ID> overrides a single agent, e.g. MODEL_WRITER=openai/gpt-oss-20b.
    models = {
        agent_id: os.getenv(f"MODEL_{agent_id.upper()}", default)
        for agent_id, default in DEFAULT_MODELS.items()
    }
    db_path = os.getenv("DB_PATH")
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "groq").lower(),
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        ollama_host=os.getenv("OLLAMA_HOST") or None,
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        models=models,
        llm_timeout_s=_env_int("LLM_TIMEOUT_S", 60),
        agent_timeout_s=_env_int("AGENT_TIMEOUT_S", 240),
        max_active_runs=_env_int("MAX_ACTIVE_RUNS", 2),
        db_path=Path(db_path) if db_path else BACKEND_DIR / "data" / "runs.db",
    )
