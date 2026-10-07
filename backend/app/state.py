"""Working memory for one run, and how each agent gets to see it.

The coordinator never sees raw tool output. Each turn it gets a compact
rendering of this state: the plan, an index of the evidence, what every task
returned, and the latest draft and review. Everything it decides is recorded
back here, so the next turn sees the outcome of the last one.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.config import Budget
from app.evidence import EvidenceStore
from app.schemas import CoordinatorDecision, Draft, PlanItem, Review, TaskResult


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class RunState:
    run_id: str
    query: str
    depth: str
    budget: Budget
    evidence: EvidenceStore = field(default_factory=EvidenceStore)
    plan: list[PlanItem] = field(default_factory=list)
    turn: int = 0
    decisions: list[CoordinatorDecision] = field(default_factory=list)
    tasks: list[TaskResult] = field(default_factory=list)
    drafts: list[Draft] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    # Corrections from the orchestrator (e.g. an invalid task it dropped), shown once.
    notes: list[str] = field(default_factory=list)
    # Long-term memory: similar questions this system has researched before.
    related: list[dict[str, Any]] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    started: float = field(default_factory=time.monotonic)

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self.started

    @property
    def time_left_s(self) -> float:
        return self.budget.time_limit_s - self.elapsed_s

    @property
    def latest_draft(self) -> Draft | None:
        return self.drafts[-1] if self.drafts else None

    @property
    def latest_review(self) -> Review | None:
        return self.reviews[-1] if self.reviews else None

    def next_task_id(self) -> str:
        return f"T{len(self.tasks) + 1}"

    # ---------------------------------------------------------------- rendering

    def render_plan(self) -> str:
        if not self.plan:
            return "(no plan yet: make one this turn)"
        return "\n".join(f"{p.id}. [{p.status}] {p.question}" for p in self.plan)

    def render_tasks(self) -> str:
        if not self.tasks:
            return "(none yet)"
        lines = []
        for t in self.tasks:
            line = f"{t.task_id} {t.agent} [{t.status}] \"{_clip(t.instruction, 110)}\" -> {_clip(t.summary, 220)}"
            if t.evidence_ids:
                line += f" | evidence: {', '.join(t.evidence_ids)}"
            if t.errors:
                line += f" | errors: {_clip('; '.join(t.errors), 160)}"
            lines.append(line)
        return "\n".join(lines)

    def render_review(self) -> str:
        draft, review = self.latest_draft, self.latest_review
        if not draft:
            return "(no draft yet)"
        lines = [f"Draft v{draft.version}: \"{draft.title}\""
                 + (" (fallback draft written without the writer)" if draft.fallback else "")]
        if not review or review.draft_version != draft.version:
            lines.append("Not reviewed yet.")
            return "\n".join(lines)
        if review.critique is None:
            lines.append(f"Critic could not review it: {review.error}")
            return "\n".join(lines)
        c = review.critique
        lines.append(f"Critic verdict: {c.verdict.upper()} (score {c.score}/10). {_clip(c.summary, 240)}")
        for issue in c.issues:
            lines.append(f"  issue {issue.id} [{issue.severity} {issue.kind}] {_clip(issue.detail, 160)}")
        for req in c.research_requests:
            lines.append(f"  research gap -> {req.agent}: {_clip(req.instruction, 160)}")
        for ruling in c.rulings:
            outcome = "accepted" if ruling.accepted else "rejected"
            lines.append(f"  writer dispute on {ruling.issue_id}: {outcome}. {_clip(ruling.note, 120)}")
        return "\n".join(lines)

    def render_for_coordinator(self) -> str:
        b = self.budget
        drafts_left = b.max_drafts - len(self.drafts)
        sections = [
            f"USER QUERY: {self.query}",
            f"TODAY: {date.today().isoformat()}",
            (f"BUDGET: turn {self.turn} of {b.max_turns}; {drafts_left} of {b.max_drafts} drafts "
             f"left; up to {b.max_tasks_per_turn} parallel tasks per turn; article_reader takes "
             f"at most {b.max_urls_per_read} URLs per task; {max(0, int(self.time_left_s))}s left"),
            f"PLAN:\n{self.render_plan()}",
            f"EVIDENCE STORE ({len(self.evidence)} sources):\n{self.evidence.render_index()}",
            f"TASK HISTORY:\n{self.render_tasks()}",
            f"DRAFT AND REVIEW:\n{self.render_review()}",
        ]
        if self.related:
            past = "\n".join(
                f"- \"{r['query']}\" ({r['date']}): {r['title']}"
                + (f"; sources included {', '.join(r['urls'][:3])}" if r.get("urls") else "")
                for r in self.related
            )
            sections.append("RELATED PAST RESEARCH (from long-term memory; may be outdated):\n" + past)
        if self.notes:
            sections.append("NOTES FROM THE ORCHESTRATOR:\n" + "\n".join(f"- {n}" for n in self.notes))
            self.notes = []
        return "\n\n".join(sections)
