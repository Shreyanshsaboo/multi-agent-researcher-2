"""Assembles the six LLM-backed agents for one run."""

import httpx

from app.agents import CoordinatorAgent, CriticAgent, WorkerAgent, WriterAgent
from app.config import Budget, Settings
from app.events import RunChannel
from app.evidence import EvidenceStore
from app.orchestrator import AgentSuite
from app.schemas import WORKER_IDS, RunOptions


def build_suite(
    *,
    settings: Settings,
    channel: RunChannel,
    evidence: EvidenceStore,
    http: httpx.AsyncClient,
    budget: Budget,
    options: RunOptions,
) -> AgentSuite:
    workers = {
        worker_id: WorkerAgent(
            worker_id,
            settings=settings,
            channel=channel,
            evidence=evidence,
            http=http,
            budget=budget,
            simulate_failure=worker_id in options.simulate_failures,
        )
        for worker_id in WORKER_IDS
    }
    return AgentSuite(
        coordinator=CoordinatorAgent(settings, channel),
        writer=WriterAgent(settings, channel),
        critic=CriticAgent(settings, channel),
        workers=workers,
    )
