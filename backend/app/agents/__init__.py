"""The six agents. Each wraps an Agno agent with its own model, prompt and tools."""

from app.agents.coordinator import CoordinatorAgent
from app.agents.critic import CriticAgent
from app.agents.registry import AGENT_SPECS, describe_agents
from app.agents.runtime import AgentFailure
from app.agents.workers import WorkerAgent
from app.agents.writer import WriterAgent, fallback_draft

__all__ = [
    "AGENT_SPECS",
    "AgentFailure",
    "CoordinatorAgent",
    "CriticAgent",
    "WorkerAgent",
    "WriterAgent",
    "describe_agents",
    "fallback_draft",
]
