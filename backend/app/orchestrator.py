"""The run loop: the coordinator decides, the orchestrator carries the decision out.

This loop holds no research strategy. Each turn it asks the coordinator what to
do, checks the decision against the budget and the evidence, executes it (worker
tasks in parallel, or a write-and-review round), and records the outcome in the
run state for the coordinator's next turn. The order of steps is whatever the
coordinator decides; the only fixed rule is that every draft goes to the critic.

The orchestrator also keeps a run from going wrong: it enforces the budget,
corrects decisions that cannot be executed (and tells the coordinator why), and
falls back to a simple policy if the coordinator itself fails. Every run ends with
a result, even when agents fail.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

from app.agents import AgentFailure, fallback_draft
from app.config import Budget
from app.events import RunChannel
from app.evidence import EvidenceStore, check_citations, normalize_url
from app.schemas import (
    CitationCheck,
    CoordinatorDecision,
    Critique,
    Draft,
    PlanItem,
    Review,
    RunResult,
    RunStats,
    TaskResult,
    TaskSpec,
)
from app.state import RunState

# ----------------------------------------------------------------- agent interfaces


class Coordinator(Protocol):
    async def decide(self, state: RunState) -> CoordinatorDecision: ...


class Worker(Protocol):
    async def execute(self, task: TaskSpec, task_id: str, query: str,
                      allowed_urls: set[str] | None = None) -> TaskResult: ...


class Writer(Protocol):
    async def write(self, state: RunState, brief: str) -> Draft: ...


class Critic(Protocol):
    async def review(self, state: RunState, draft: Draft, checks: CitationCheck) -> Critique: ...


@dataclass
class AgentSuite:
    coordinator: Coordinator
    writer: Writer
    critic: Critic
    workers: dict[str, Worker]


@dataclass
class Outcome:
    status: str
    message: str = ""


def _targets(decision: CoordinatorDecision) -> list[str]:
    if decision.action == "delegate":
        return list(dict.fromkeys(t.agent for t in decision.tasks)) or ["orchestrator"]
    if decision.action == "draft":
        return ["writer"]
    return ["user"]


class Orchestrator:
    def __init__(
        self,
        *,
        run_id: str,
        query: str,
        depth: str,
        budget: Budget,
        channel: RunChannel,
        suite: AgentSuite,
        evidence: EvidenceStore,
        related: list[dict[str, Any]] | None = None,
        conversation: list[dict[str, Any]] | None = None,
    ) -> None:
        self.channel = channel
        self.suite = suite
        self.state = RunState(run_id=run_id, query=query, depth=depth, budget=budget,
                              evidence=evidence, related=related or [],
                              conversation=conversation or [])
        self._task_seq = 0

    # ------------------------------------------------------------------- the loop

    async def run(self) -> RunResult:
        state, channel = self.state, self.channel
        channel.message("user", "coordinator", "query", state.query)
        if state.conversation:
            self._carry_forward_sources()
        if state.related:
            channel.emit("memory", items=state.related)

        outcome: Outcome | None = None
        while outcome is None:
            stop_reason = self._budget_exhausted()
            if stop_reason:
                outcome = await self._wrap_up(stop_reason)
                break
            state.turn += 1
            decision = await self._decide()
            outcome = await self._execute(decision)

        result = self._result(outcome)
        channel.message("coordinator", "user", "final",
                        result.message or f"Report ready: {result.title}",
                        content={"status": result.status, "review_status": result.review_status})
        return result

    def _carry_forward_sources(self) -> None:
        """Seed a follow-up's evidence store with the sources earlier answers cited.

        A follow-up like "summarise that" can then be answered without new
        research, and "tell me more about X" only has to research what is new.
        """
        carried = []
        for turn in self.state.conversation:
            for e in turn["evidence"]:
                item, created = self.state.evidence.add(
                    url=e["url"], title=e["title"], source_type=e["source_type"],
                    agent=(e.get("found_by") or ["coordinator"])[0], key_points=e["key_points"],
                    full_text_read=e.get("full_text_read", False), published=e.get("published"),
                    meta={**e.get("meta", {}), "earlier_turn": True})
                if created:
                    carried.append(item)
                    self.channel.emit("evidence", agent="coordinator", task_id="context",
                                      created=True, item=item.model_dump())
        self.channel.emit("context", turns=len(self.state.conversation),
                          carried=[item.id for item in carried])

    def _budget_exhausted(self) -> str | None:
        if self.state.turn >= self.state.budget.max_turns:
            return f"turn limit of {self.state.budget.max_turns} reached"
        if self.state.time_left_s <= 0:
            return f"time limit of {self.state.budget.time_limit_s}s reached"
        return None

    # ---------------------------------------------------------------- deciding

    async def _decide(self) -> CoordinatorDecision:
        fallback = False
        try:
            decision = await self.suite.coordinator.decide(self.state)
        except AgentFailure as exc:
            self.channel.emit("agent_error", agent="coordinator", error=str(exc))
            decision = self._fallback_decision(str(exc))
            fallback = True

        decision = self._validate(decision)
        self.state.decisions.append(decision)
        if decision.plan:
            self.state.plan = decision.plan
            self.channel.emit("plan", turn=self.state.turn,
                              items=[p.model_dump() for p in decision.plan])

        summary = decision.thought
        if fallback:
            summary = f"(fallback policy) {summary}"
        self.channel.message("coordinator", _targets(decision), "decision", summary,
                             content={**decision.model_dump(), "turn": self.state.turn,
                                      "fallback": fallback})
        return decision

    def _correct(self, note: str) -> None:
        """Record a correction to the coordinator's decision; it sees the note next turn."""
        self.state.notes.append(note)
        self.channel.emit("guardrail", agent="orchestrator", rule="decision_corrected", detail=note)

    def _opening_tasks(self) -> list[TaskSpec]:
        q = self.state.query
        return [
            TaskSpec(agent="web_researcher", instruction=f"Find authoritative, recent sources on: {q}"),
            TaskSpec(agent="hn_scout", instruction=f"Find Hacker News discussions about: {q}"),
        ][: self.state.budget.max_tasks_per_turn]

    def _fallback_decision(self, reason: str) -> CoordinatorDecision:
        s = self.state
        plan = s.plan or [PlanItem(id=1, question=s.query, status="open")]
        thought = f"Coordinator unavailable ({reason[:120]}); using the default policy."
        if not len(s.evidence) and not s.tasks:
            return CoordinatorDecision(thought=thought, plan=plan, action="delegate",
                                       tasks=self._opening_tasks())
        if len(s.evidence) and not s.drafts:
            return CoordinatorDecision(thought=thought, plan=plan, action="draft",
                                       writer_brief="Write the report from the evidence.")
        return CoordinatorDecision(thought=thought, plan=plan, action="finish",
                                   message="Finished by the fallback policy.")

    def _readable_urls(self) -> set[str]:
        urls = self.state.evidence.known_urls()
        for past in self.state.related:
            urls |= {normalize_url(u) for u in past.get("urls", [])}
        return urls

    def _validate(self, decision: CoordinatorDecision) -> CoordinatorDecision:
        s, budget = self.state, self.state.budget
        action = decision.action

        if action == "delegate":
            tasks = []
            readable = self._readable_urls()
            for task in decision.tasks:
                if task.agent == "article_reader":
                    urls = [u for u in task.urls if normalize_url(u) in readable]
                    if len(urls) < len(task.urls):
                        self._correct("Dropped article_reader URLs that are not in the evidence store.")
                    if not urls:
                        self._correct("article_reader needs URLs from the evidence store; task skipped.")
                        continue
                    task = task.model_copy(update={"urls": urls[: budget.max_urls_per_read]})
                tasks.append(task)
            if len(tasks) > budget.max_tasks_per_turn:
                self._correct(f"Only {budget.max_tasks_per_turn} tasks run per turn; extra tasks dropped.")
                tasks = tasks[: budget.max_tasks_per_turn]
            if tasks:
                return decision.model_copy(update={"tasks": tasks})
            if len(s.evidence) and len(s.drafts) < budget.max_drafts:
                self._correct("No runnable tasks, so the writer drafts from the current evidence.")
                return decision.model_copy(update={"action": "draft", "tasks": []})
            self._correct("No runnable tasks; starting with default research tasks.")
            return decision.model_copy(update={"tasks": self._opening_tasks()})

        if action == "draft":
            if not len(s.evidence):
                self._correct("Cannot draft with an empty evidence store; researching first.")
                return decision.model_copy(update={"action": "delegate",
                                                   "tasks": self._opening_tasks()})
            if len(s.drafts) >= budget.max_drafts:
                self._correct(f"All {budget.max_drafts} drafts are used; finishing with the latest.")
                return decision.model_copy(update={"action": "finish"})

        if action == "finish" and not s.drafts:
            if len(s.evidence):
                self._correct("Cannot finish without a report; asking the writer for a draft.")
                return decision.model_copy(update={"action": "draft"})
            if not s.tasks:
                self._correct("Cannot finish before any research; starting research.")
                return decision.model_copy(update={"action": "delegate",
                                                   "tasks": self._opening_tasks()})

        return decision

    # ---------------------------------------------------------------- executing

    async def _execute(self, decision: CoordinatorDecision) -> Outcome | None:
        if decision.action == "delegate":
            await self._delegate(decision.tasks)
            return None
        if decision.action == "draft":
            await self._write_and_review(decision.writer_brief)
            return None
        if decision.action == "reject":
            return Outcome("rejected", decision.message or "The coordinator declined this query.")
        if not self.state.drafts:
            return Outcome("completed", decision.message
                           or "The team could not find usable sources for this query.")
        return Outcome("completed", decision.message)

    async def _delegate(self, tasks: list[TaskSpec]) -> None:
        readable = self._readable_urls()
        jobs, ids = [], []
        for spec in tasks:
            self._task_seq += 1
            task_id = f"T{self._task_seq}"
            ids.append(task_id)
            self.channel.message("coordinator", spec.agent, "task", spec.instruction,
                                 content={**spec.model_dump(), "task_id": task_id})
            worker = self.suite.workers[spec.agent]
            allowed = readable if spec.agent == "article_reader" else None
            jobs.append(worker.execute(spec, task_id, self.state.query, allowed_urls=allowed))

        results = await asyncio.gather(*jobs, return_exceptions=True)
        for spec, task_id, result in zip(tasks, ids, results):
            if isinstance(result, BaseException):
                result = TaskResult(task_id=task_id, agent=spec.agent, instruction=spec.instruction,
                                    status="failed", summary=f"Worker crashed: {result}",
                                    errors=[str(result)[:300]])
            self.state.tasks.append(result)
            self.channel.message(result.agent, "coordinator", "result",
                                 f"[{result.status}] {result.summary[:200]}",
                                 content=result.model_dump())

    async def _write_and_review(self, brief: str) -> None:
        s, channel = self.state, self.channel
        version = len(s.drafts) + 1
        channel.message("coordinator", "writer", "brief", brief or "Write the report.",
                        content={"version": version})
        try:
            draft = await self.suite.writer.write(s, brief)
        except AgentFailure as exc:
            channel.emit("agent_error", agent="writer", error=str(exc))
            draft = fallback_draft(s, version)
        s.drafts.append(draft)
        channel.emit("draft", draft=draft.model_dump())

        fixed = sum(r.action == "fixed" for r in draft.responses)
        disputed = sum(r.action == "disputed" for r in draft.responses)
        note = f"; fixed {fixed}, disputed {disputed}" if draft.responses else ""
        channel.message("writer", "critic", "draft", f"Draft v{draft.version}: {draft.title}{note}",
                        content={"version": draft.version, "title": draft.title,
                                 "responses": [r.model_dump() for r in draft.responses]})

        checks = check_citations(draft.markdown, s.evidence)
        critique, error = None, None
        if draft.fallback:
            error = "fallback digest, not sent for review"
        else:
            try:
                critique = await self.suite.critic.review(s, draft, checks)
            except AgentFailure as exc:
                error = str(exc)
                channel.emit("agent_error", agent="critic", error=error)

        review = Review(draft_version=draft.version, critique=critique, checks=checks, error=error)
        s.reviews.append(review)
        channel.emit("review", review=review.model_dump())

        if critique is None:
            channel.message("critic", "coordinator", "verdict", f"No review: {error}")
            return
        channel.message("critic", "coordinator", "verdict",
                        f"{critique.verdict.upper()} {critique.score}/10: {critique.summary}",
                        content=critique.model_dump())
        if critique.verdict == "revise" and critique.issues:
            channel.message("critic", "writer", "critique",
                            f"{len(critique.issues)} issue(s) to address in v{draft.version}",
                            content=[i.model_dump() for i in critique.issues])

    async def _wrap_up(self, reason: str) -> Outcome:
        s = self.state
        self.channel.emit("guardrail", agent="orchestrator", rule="budget", detail=f"Stopping: {reason}.")
        if not s.drafts and len(s.evidence):
            try:
                s.drafts.append(await self.suite.writer.write(
                    s, "The research budget is spent: write the best report you can from the evidence."))
            except AgentFailure as exc:
                self.channel.emit("agent_error", agent="writer", error=str(exc))
                s.drafts.append(fallback_draft(s, len(s.drafts) + 1))
            self.channel.emit("draft", draft=s.drafts[-1].model_dump())
        if not s.drafts:
            return Outcome("completed", f"Stopped early ({reason}) before any usable sources were found.")
        return Outcome("completed", f"Stopped early ({reason}); this is the latest draft.")

    # ------------------------------------------------------------------ result

    def _result(self, outcome: Outcome) -> RunResult:
        s = self.state
        draft = s.latest_draft
        review = s.latest_review if s.latest_review and draft and \
            s.latest_review.draft_version == draft.version else None

        review_status, score, unresolved = "none", None, []
        if draft:
            if review is None or review.critique is None:
                review_status = "unreviewed"
            else:
                c = review.critique
                score = c.score
                accepted = {r.issue_id for r in c.rulings if r.accepted}
                if c.verdict == "approve":
                    review_status = "approved"
                else:
                    review_status = "accepted_with_issues"
                    unresolved = [i for i in c.issues if i.id not in accepted]

        tokens: dict[str, int] = defaultdict(int)
        for event in self.channel.events:
            if event["type"] == "metrics":
                tokens[event["agent"]] += event["input_tokens"] + event["output_tokens"]

        cited = [c for c in check_citations(draft.markdown, s.evidence).cited_ids
                 if c in s.evidence] if draft else []
        return RunResult(
            run_id=s.run_id,
            query=s.query,
            status=outcome.status,
            title=draft.title if draft else "",
            report_markdown=draft.markdown if draft else "",
            message=outcome.message,
            evidence=s.evidence.all(),
            cited_ids=cited,
            final_score=score,
            review_status=review_status,
            unresolved_issues=unresolved,
            plan=s.plan,
            stats=RunStats(
                turns=s.turn,
                tasks=len(s.tasks),
                failed_tasks=sum(t.status == "failed" for t in s.tasks),
                tool_calls=sum(t.tool_calls for t in s.tasks),
                drafts=len(s.drafts),
                duration_s=round(s.elapsed_s, 1),
                tokens=dict(tokens),
            ),
        )
