"""Running one Agno agent call inside a research run.

Agno reports a failed model call as a completed run whose status is ERROR and
whose content is the error text. These helpers turn that, timeouts and crashes
into a single AgentFailure, so the orchestrator can decide how to recover.
"""

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from agno.agent import Agent
from agno.run.base import RunStatus
from pydantic import BaseModel, ValidationError

from app.events import ACTIVE_AGENT, RunChannel

T = TypeVar("T", bound=BaseModel)


class AgentFailure(RuntimeError):
    pass


@dataclass
class AgentReply:
    content: Any
    tools: list[Any] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_s: float = 0.0


def _error_text(content: Any) -> str:
    text = str(content or "unknown error")
    try:
        return json.loads(text)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return text[:300]


async def run_agent(
    agent: Agent, prompt: str, *, channel: RunChannel, agent_id: str, timeout: float
) -> AgentReply:
    token = ACTIVE_AGENT.set((channel, agent_id))
    try:
        output = await asyncio.wait_for(agent.arun(prompt), timeout)
    except TimeoutError:
        raise AgentFailure(f"{agent_id} timed out after {int(timeout)}s") from None
    except Exception as exc:
        raise AgentFailure(f"{agent_id} crashed: {type(exc).__name__}: {exc}") from exc
    finally:
        ACTIVE_AGENT.reset(token)

    if output.status == RunStatus.error:
        raise AgentFailure(f"{agent_id} model call failed: {_error_text(output.content)}")

    metrics = output.metrics
    reply = AgentReply(
        content=output.content,
        tools=list(output.tools or []),
        input_tokens=getattr(metrics, "input_tokens", 0) or 0,
        output_tokens=getattr(metrics, "output_tokens", 0) or 0,
        duration_s=round(getattr(metrics, "duration", 0) or 0, 2),
    )
    channel.emit(
        "metrics",
        agent=agent_id,
        model=output.model,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        duration_s=reply.duration_s,
        tool_calls=len(reply.tools),
    )
    return reply


def coerce(content: Any, schema: type[T]) -> T:
    """Accept the parsed model, a dict, or JSON text (possibly wrapped in prose or fences)."""
    if isinstance(content, schema):
        return content
    if isinstance(content, BaseModel):
        content = content.model_dump()
    if isinstance(content, dict):
        return schema.model_validate(content)
    text = str(content or "")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in the reply")
    return schema.model_validate_json(match.group(0))


async def run_structured(
    make_agent: Callable[[], Agent],
    prompt: str,
    schema: type[T],
    *,
    channel: RunChannel,
    agent_id: str,
    timeout: float,
    retries: int = 1,
) -> T:
    """Run an agent that answers in ``schema``; on a malformed reply, retry with the error."""
    attempt_prompt = prompt
    last_error = ""
    for _ in range(retries + 1):
        reply = await run_agent(make_agent(), attempt_prompt, channel=channel,
                                agent_id=agent_id, timeout=timeout)
        try:
            return coerce(reply.content, schema)
        except (ValueError, ValidationError) as exc:
            last_error = str(exc)[:500]
            channel.emit("guardrail", agent=agent_id, rule="malformed_output",
                         detail=f"Reply did not match {schema.__name__}; asking again. {last_error}")
            attempt_prompt = (
                f"{prompt}\n\nYOUR PREVIOUS REPLY WAS INVALID: {last_error}\n"
                "Reply again with only a JSON object that matches the schema."
            )
    raise AgentFailure(f"{agent_id} returned malformed output: {last_error}")
