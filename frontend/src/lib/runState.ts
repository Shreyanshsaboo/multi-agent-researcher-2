import type {
  AgentId,
  AgentSpec,
  Budget,
  Draft,
  EventOf,
  Evidence,
  Participant,
  PlanItem,
  Review,
  RunEvent,
  RunOptions,
  RunResult,
} from "../types";

export type RunStatus = "idle" | "connecting" | "running" | "completed" | "rejected" | "failed";

export interface AgentView {
  state: string;
  detail: string;
  /** The model that actually served the agent's last call, if it was not the configured one. */
  model?: string;
  tokens: number;
  calls: number;
  toolCalls: number;
}

export interface ToolCallView {
  callId: string;
  agent: AgentId;
  taskId: string;
  tool: string;
  args: Record<string, unknown>;
  phase: "started" | "completed" | "failed";
  preview?: string;
  error?: string;
  simulated?: boolean;
  durationMs?: number;
}

export type NoticeTone = "guard" | "wait" | "error" | "fallback" | "memory" | "evidence";

export type TimelineEntry =
  | { kind: "message"; seq: number; elapsed: number; event: EventOf<"message"> }
  | { kind: "tool"; seq: number; elapsed: number; call: ToolCallView }
  | { kind: "notice"; seq: number; elapsed: number; tone: NoticeTone; agent: Participant; text: string };

/** One message travelling along an edge of the agent graph. */
export interface Pulse {
  id: string;
  from: Participant;
  to: Participant;
  kind: string;
}

export interface RunView {
  runId: string | null;
  query: string;
  status: RunStatus;
  startedTs: number | null;
  lastElapsed: number;
  lastSeq: number;
  options: RunOptions | null;
  budget: Budget | null;
  specs: AgentSpec[];
  agents: Record<string, AgentView>;
  plan: PlanItem[];
  planTurn: number;
  replanned: boolean;
  turn: number;
  tasks: number;
  timeline: TimelineEntry[];
  pulses: Pulse[];
  evidence: Evidence[];
  drafts: Draft[];
  reviews: Review[];
  result: RunResult | null;
  error: string | null;
}

const MAX_PULSES = 8;

export function initialRun(runId: string | null = null): RunView {
  return {
    runId,
    query: "",
    status: runId ? "connecting" : "idle",
    startedTs: null,
    lastElapsed: 0,
    lastSeq: 0,
    options: null,
    budget: null,
    specs: [],
    agents: {},
    plan: [],
    planTurn: 0,
    replanned: false,
    turn: 0,
    tasks: 0,
    timeline: [],
    pulses: [],
    evidence: [],
    drafts: [],
    reviews: [],
    result: null,
    error: null,
  };
}

function agent(view: RunView, id: string): AgentView {
  return view.agents[id] ?? { state: "idle", detail: "", tokens: 0, calls: 0, toolCalls: 0 };
}

function patchAgent(view: RunView, id: string, patch: Partial<AgentView>): Record<string, AgentView> {
  return { ...view.agents, [id]: { ...agent(view, id), ...patch } };
}

function notice(
  event: RunEvent,
  tone: NoticeTone,
  who: Participant,
  text: string,
): TimelineEntry {
  return { kind: "notice", seq: event.seq, elapsed: event.elapsed, tone, agent: who, text };
}

/** Per-minute limits clear after a short wait; a daily limit means switching models. */
export function rateLimitText(event: EventOf<"rate_limited">): string {
  const scope = /on (tokens per day|tokens per minute|requests per day|requests per minute|[a-z ]+ per (?:minute|day))/i
    .exec(event.detail)?.[1]?.toLowerCase();
  const wait = event.retry_after_s ?? 0;
  const what = scope ? `Rate limited (${scope})` : "Rate limited by the model provider";
  if (wait > 60 || scope?.includes("day")) return `${what}; switching to a fallback model`;
  return wait ? `${what}; retrying in ${Math.round(wait)}s` : `${what}; retrying`;
}

function samePlan(a: PlanItem[], b: PlanItem[]): boolean {
  return a.length === b.length && a.every((item, i) => item.question === b[i].question);
}

/** Fold one server event into the view. Pure, so replaying a trace rebuilds the same view. */
export function applyEvent(view: RunView, event: RunEvent): RunView {
  if (event.seq <= view.lastSeq) return view; // already applied (stream reconnect)
  const base = { ...view, lastSeq: event.seq, lastElapsed: Math.max(view.lastElapsed, event.elapsed) };

  switch (event.type) {
    case "run_started":
      return {
        ...base,
        runId: event.run_id,
        query: event.query,
        status: "running",
        startedTs: event.ts,
        options: event.options,
        budget: event.budget,
        specs: event.agents,
      };

    case "message": {
      const pulses = event.recipients
        .filter((to) => to !== event.sender)
        .map((to) => ({ id: `${event.id}-${to}`, from: event.sender, to, kind: event.kind }));
      const content = event.content as { turn?: number } | null;
      return {
        ...base,
        turn: event.kind === "decision" && content?.turn ? content.turn : base.turn,
        tasks: event.kind === "task" ? base.tasks + 1 : base.tasks,
        pulses: [...base.pulses, ...pulses].slice(-MAX_PULSES),
        timeline: [...base.timeline, { kind: "message", seq: event.seq, elapsed: event.elapsed, event }],
      };
    }

    case "agent_status":
      return { ...base, agents: patchAgent(base, event.agent, { state: event.state, detail: event.detail }) };

    case "tool_call": {
      const call: ToolCallView = {
        callId: event.call_id,
        agent: event.agent,
        taskId: event.task_id,
        tool: event.tool,
        args: event.args ?? {},
        phase: event.phase,
        preview: event.preview,
        error: event.error,
        simulated: event.simulated,
        durationMs: event.duration_ms,
      };
      if (event.phase === "started") {
        return {
          ...base,
          timeline: [...base.timeline, { kind: "tool", seq: event.seq, elapsed: event.elapsed, call }],
        };
      }
      // Completion replaces the started entry in place, keeping its position in the timeline.
      const index = base.timeline.findIndex((e) => e.kind === "tool" && e.call.callId === event.call_id);
      const timeline = [...base.timeline];
      if (index >= 0) {
        const started = timeline[index] as Extract<TimelineEntry, { kind: "tool" }>;
        timeline[index] = { ...started, call: { ...call, args: started.call.args } };
      } else {
        timeline.push({ kind: "tool", seq: event.seq, elapsed: event.elapsed, call });
      }
      const current = agent(base, event.agent);
      return {
        ...base,
        timeline,
        agents: patchAgent(base, event.agent, { toolCalls: current.toolCalls + 1 }),
      };
    }

    case "evidence": {
      const existing = base.evidence.findIndex((e) => e.id === event.item.id);
      const evidence = [...base.evidence];
      if (existing >= 0) evidence[existing] = event.item;
      else evidence.push(event.item);
      const verb = event.created ? "added" : "enriched";
      return {
        ...base,
        evidence,
        timeline: [...base.timeline, notice(event, "evidence", event.agent,
          `${event.item.id} ${verb}: ${event.item.title}`)],
      };
    }

    case "plan":
      return {
        ...base,
        plan: event.items,
        planTurn: event.turn,
        replanned: base.plan.length > 0 && !samePlan(base.plan, event.items),
      };

    case "draft":
      return { ...base, drafts: [...base.drafts.filter((d) => d.version !== event.draft.version), event.draft] };

    case "review":
      return { ...base, reviews: [...base.reviews, event.review] };

    case "guardrail":
      return { ...base, timeline: [...base.timeline, notice(event, "guard", event.agent, event.detail)] };

    case "rate_limited":
      return { ...base, timeline: [...base.timeline, notice(event, "wait", event.agent, rateLimitText(event))] };

    case "model_fallback":
      return {
        ...base,
        agents: patchAgent(base, event.agent, { model: event.fallback }),
        timeline: [...base.timeline, notice(event, "fallback", event.agent,
          `Switched model: ${event.primary} → ${event.fallback}`)],
      };

    case "agent_error":
      return {
        ...base,
        agents: patchAgent(base, event.agent, { state: "error", detail: event.error }),
        timeline: [...base.timeline, notice(event, "error", event.agent, event.error)],
      };

    case "metrics": {
      const current = agent(base, event.agent);
      return {
        ...base,
        agents: patchAgent(base, event.agent, {
          tokens: current.tokens + event.input_tokens + event.output_tokens,
          calls: current.calls + 1,
          model: event.model ?? current.model,
        }),
      };
    }

    case "memory":
      return {
        ...base,
        timeline: [...base.timeline, notice(event, "memory", "coordinator",
          `Recalled ${event.items.length} related past run(s): ${event.items.map((i) => `"${i.query}"`).join(", ")}`)],
      };

    case "run_completed":
      return {
        ...base,
        status: event.result.status === "rejected" ? "rejected" : "completed",
        result: event.result,
        evidence: event.result.evidence.length ? event.result.evidence : base.evidence,
      };

    case "run_failed":
      return { ...base, status: "failed", error: event.error };

    default:
      return base;
  }
}

export function totalTokens(view: RunView): number {
  return Object.values(view.agents).reduce((sum, a) => sum + a.tokens, 0);
}

export function toolCallCount(view: RunView): number {
  return Object.values(view.agents).reduce((sum, a) => sum + a.toolCalls, 0);
}
