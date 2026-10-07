// Mirrors backend/app/schemas.py and the events in backend/app/events.py.

export type AgentId =
  | "coordinator"
  | "hn_scout"
  | "web_researcher"
  | "article_reader"
  | "writer"
  | "critic";
export type WorkerId = "hn_scout" | "web_researcher" | "article_reader";
export type Participant = AgentId | "user" | "orchestrator";
export type Depth = "quick" | "standard" | "deep";

export interface AgentSpec {
  id: AgentId;
  name: string;
  kind: string;
  role: string;
  tools: string[];
  model: string;
}

export interface Budget {
  max_turns: number;
  max_drafts: number;
  max_tasks_per_turn: number;
  max_findings_per_task: number;
  max_urls_per_read: number;
  time_limit_s: number;
}

export interface RunOptions {
  depth: Depth;
  simulate_failures: WorkerId[];
}

export interface PlanItem {
  id: number;
  question: string;
  status: "open" | "in_progress" | "answered" | "dropped";
}

export interface Evidence {
  id: string;
  url: string;
  title: string;
  source_type: "hackernews" | "web" | "news" | "article";
  found_by: string[];
  key_points: string[];
  full_text_read: boolean;
  published: string | null;
  meta: Record<string, unknown>;
}

export interface IssueResponse {
  issue_id: string;
  action: "fixed" | "disputed";
  note: string;
}

export interface Draft {
  version: number;
  title: string;
  markdown: string;
  responses: IssueResponse[];
  fallback: boolean;
}

export interface Issue {
  id: string;
  severity: "minor" | "major";
  kind: string;
  detail: string;
  suggestion: string;
}

export interface Critique {
  verdict: "approve" | "revise";
  score: number;
  summary: string;
  issues: Issue[];
  research_requests: { agent: WorkerId; instruction: string }[];
  rulings: { issue_id: string; accepted: boolean; note: string }[];
}

export interface CitationCheck {
  cited_ids: string[];
  unknown_ids: string[];
  uncited_paragraphs: string[];
  evidence_total: number;
}

export interface Review {
  draft_version: number;
  critique: Critique | null;
  checks: CitationCheck;
  error: string | null;
}

export interface RunResult {
  run_id: string;
  query: string;
  status: "completed" | "rejected" | "failed";
  title: string;
  report_markdown: string;
  message: string;
  evidence: Evidence[];
  cited_ids: string[];
  final_score: number | null;
  review_status: "approved" | "accepted_with_issues" | "unreviewed" | "none";
  unresolved_issues: Issue[];
  plan: PlanItem[];
  stats: {
    turns: number;
    tasks: number;
    failed_tasks: number;
    tool_calls: number;
    drafts: number;
    duration_s: number;
    tokens: Record<string, number>;
  };
}

export interface RunSummary {
  id: string;
  query: string;
  status: string;
  created_at: number;
  finished_at: number | null;
  title: string | null;
  score: number | null;
  review_status: string | null;
}

interface BaseEvent {
  seq: number;
  ts: number;
  elapsed: number;
}

export type RunEvent = BaseEvent &
  (
    | {
        type: "run_started";
        run_id: string;
        query: string;
        options: RunOptions;
        budget: Budget;
        agents: AgentSpec[];
      }
    | {
        type: "message";
        id: string;
        sender: Participant;
        recipients: Participant[];
        kind: string;
        summary: string;
        content: unknown;
      }
    | { type: "agent_status"; agent: AgentId; state: string; detail: string }
    | {
        type: "tool_call";
        phase: "started" | "completed" | "failed";
        agent: AgentId;
        task_id: string;
        call_id: string;
        tool: string;
        args?: Record<string, unknown>;
        preview?: string;
        error?: string;
        simulated?: boolean;
        duration_ms?: number;
      }
    | { type: "evidence"; agent: AgentId; task_id: string; created: boolean; item: Evidence }
    | { type: "plan"; turn: number; items: PlanItem[] }
    | { type: "draft"; draft: Draft }
    | { type: "review"; review: Review }
    | { type: "guardrail"; agent: Participant; rule: string; detail: string; task_id?: string }
    | { type: "rate_limited"; agent: AgentId; retry_after_s: number | null; detail: string }
    | { type: "model_fallback"; agent: AgentId; primary: string; fallback: string; detail: string }
    | { type: "agent_error"; agent: AgentId; error: string }
    | {
        type: "metrics";
        agent: AgentId;
        model?: string | null;
        input_tokens: number;
        output_tokens: number;
        duration_s: number;
        tool_calls: number;
      }
    | { type: "memory"; items: { run_id: string; query: string; title: string; date: string }[] }
    | { type: "run_completed"; result: RunResult }
    | { type: "run_failed"; error: string }
  );

export type EventOf<T extends RunEvent["type"]> = Extract<RunEvent, { type: T }>;
