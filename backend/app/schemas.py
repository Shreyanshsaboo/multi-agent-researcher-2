"""Data contracts: the API input, what agents say to each other, and the final output.

The LLM-facing models (CoordinatorDecision, WriterOutput, Critique) are parsed
from model output, so their enum-like fields are normalised before validation
instead of rejecting "Delegate" when the schema says "delegate".
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

WorkerId = Literal["hn_scout", "web_researcher", "article_reader"]
SourceType = Literal["hackernews", "web", "news", "article"]

WORKER_IDS: tuple[str, ...] = ("hn_scout", "web_researcher", "article_reader")


def _lower(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


# --------------------------------------------------------------------------- input


class RunOptions(BaseModel):
    depth: Literal["quick", "standard", "deep"] = "standard"
    # Fault injection for demos: every tool call made by these workers fails,
    # so the coordinator has to re-plan around them.
    simulate_failures: list[WorkerId] = Field(default_factory=list)


class RunRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    options: RunOptions = Field(default_factory=RunOptions)
    # Continue an existing conversation: the run sees its earlier questions,
    # answers and sources. Omitted for a new conversation.
    thread_id: str | None = Field(default=None, max_length=64)

    @field_validator("query")
    @classmethod
    def _query_has_words(cls, value: str) -> str:
        value = " ".join(value.split())
        if sum(ch.isalnum() for ch in value) < 3:
            raise ValueError("query must contain at least a few letters or digits")
        return value


# ------------------------------------------------------------------------ evidence


class Evidence(BaseModel):
    id: str
    url: str
    title: str
    source_type: SourceType
    found_by: list[str]
    key_points: list[str]
    full_text_read: bool = False
    published: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------- coordinator


class PlanItem(BaseModel):
    id: int
    question: str
    status: Literal["open", "in_progress", "answered", "dropped"] = "open"

    _norm_status = field_validator("status", mode="before")(_lower)


class TaskSpec(BaseModel):
    agent: WorkerId
    instruction: str = Field(description="Specific task: what to look for and why.")
    urls: list[str] = Field(default_factory=list, description="article_reader only: URLs to read.")
    rationale: str = ""

    _norm_agent = field_validator("agent", mode="before")(_lower)


class CoordinatorDecision(BaseModel):
    thought: str = Field(description="1-3 sentences: why this action now.")
    plan: list[PlanItem] = Field(description="The full, updated research plan.")
    action: Literal["delegate", "draft", "finish", "reject"]
    tasks: list[TaskSpec] = Field(default_factory=list, description="For delegate: 1-3 parallel tasks.")
    writer_brief: str = Field(default="", description="For draft: structure, emphasis, issues to fix.")
    message: str = Field(default="", description="For finish/reject: note for the user.")

    _norm_action = field_validator("action", mode="before")(_lower)


# ------------------------------------------------------------------------- workers


class TaskResult(BaseModel):
    task_id: str
    agent: WorkerId
    instruction: str
    status: Literal["success", "partial", "failed"]
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    tool_calls: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_s: float = 0.0


# ----------------------------------------------------------------- writer / critic


class IssueResponse(BaseModel):
    issue_id: str
    action: Literal["fixed", "disputed"]
    note: str = ""

    _norm_action = field_validator("action", mode="before")(_lower)


class WriterOutput(BaseModel):
    title: str
    report_markdown: str = Field(description="The report in Markdown, citing evidence as [E1].")
    responses: list[IssueResponse] = Field(
        default_factory=list, description="When revising: one entry per critic issue."
    )


class Issue(BaseModel):
    id: str
    severity: Literal["minor", "major"] = "minor"
    kind: Literal[
        "unsupported_claim", "citation_error", "missing_coverage", "contradiction", "clarity"
    ] = "clarity"
    detail: str
    suggestion: str = ""

    _norm = field_validator("severity", "kind", mode="before")(_lower)


class ResearchRequest(BaseModel):
    agent: WorkerId
    instruction: str

    _norm_agent = field_validator("agent", mode="before")(_lower)


class Ruling(BaseModel):
    issue_id: str
    accepted: bool = Field(description="True if the writer's dispute is accepted.")
    note: str = ""


class Critique(BaseModel):
    verdict: Literal["approve", "revise"]
    score: int = Field(ge=1, le=10)
    summary: str
    issues: list[Issue] = Field(default_factory=list)
    research_requests: list[ResearchRequest] = Field(default_factory=list)
    rulings: list[Ruling] = Field(default_factory=list)

    _norm_verdict = field_validator("verdict", mode="before")(_lower)


class Draft(BaseModel):
    version: int
    title: str
    markdown: str
    responses: list[IssueResponse] = Field(default_factory=list)
    fallback: bool = False


class CitationCheck(BaseModel):
    cited_ids: list[str]
    unknown_ids: list[str]
    uncited_paragraphs: list[str]
    evidence_total: int


class Review(BaseModel):
    draft_version: int
    critique: Critique | None
    checks: CitationCheck
    error: str | None = None


# -------------------------------------------------------------------------- output


class RunStats(BaseModel):
    turns: int = 0
    tasks: int = 0
    failed_tasks: int = 0
    tool_calls: int = 0
    drafts: int = 0
    duration_s: float = 0.0
    tokens: dict[str, int] = Field(default_factory=dict)


class RunResult(BaseModel):
    run_id: str
    query: str
    status: Literal["completed", "rejected", "failed"]
    title: str = ""
    report_markdown: str = ""
    message: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    cited_ids: list[str] = Field(default_factory=list)
    final_score: int | None = None
    review_status: Literal["approved", "accepted_with_issues", "unreviewed", "none"] = "none"
    unresolved_issues: list[Issue] = Field(default_factory=list)
    plan: list[PlanItem] = Field(default_factory=list)
    stats: RunStats = Field(default_factory=RunStats)
