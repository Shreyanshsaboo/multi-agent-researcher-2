import { describe, expect, it } from "vitest";

import type { RunEvent } from "../types";
import { applyEvent, initialRun, rateLimitText, settleAgents, toolCallCount, totalTokens } from "./runState";

let seq = 0;
function ev(body: Record<string, unknown>): RunEvent {
  seq += 1;
  return { seq, ts: 1000 + seq, elapsed: seq / 2, ...body } as RunEvent;
}

function replay(events: RunEvent[]) {
  return events.reduce(applyEvent, initialRun("r1"));
}

const started = () =>
  ev({
    type: "run_started",
    run_id: "r1",
    query: "What changed?",
    options: { depth: "quick", simulate_failures: [] },
    budget: { max_turns: 5, max_drafts: 2, max_tasks_per_turn: 2, max_findings_per_task: 4, max_urls_per_read: 2, time_limit_s: 360 },
    agents: [],
  });

describe("applyEvent", () => {
  it("starts the run and tracks turns, tasks and message pulses", () => {
    const view = replay([
      started(),
      ev({ type: "message", id: "m1", sender: "coordinator", recipients: ["hn_scout", "web_researcher"], kind: "decision", summary: "go", content: { turn: 1 } }),
      ev({ type: "message", id: "m2", sender: "coordinator", recipients: ["hn_scout"], kind: "task", summary: "search", content: {} }),
    ]);
    expect(view.status).toBe("running");
    expect(view.query).toBe("What changed?");
    expect(view.turn).toBe(1);
    expect(view.tasks).toBe(1);
    expect(view.pulses.map((p) => p.id)).toEqual(["m1-hn_scout", "m1-web_researcher", "m2-hn_scout"]);
    expect(view.timeline).toHaveLength(2);
  });

  it("merges a tool call's completion into its started entry", () => {
    const view = replay([
      started(),
      ev({ type: "tool_call", phase: "started", agent: "hn_scout", task_id: "T1", call_id: "T1.1", tool: "search_hackernews", args: { query: "llm" } }),
      ev({ type: "tool_call", phase: "failed", agent: "hn_scout", task_id: "T1", call_id: "T1.1", tool: "search_hackernews", error: "SimulatedFault", simulated: true, duration_ms: 3 }),
    ]);
    expect(view.timeline).toHaveLength(1);
    const entry = view.timeline[0];
    expect(entry.kind === "tool" && entry.call).toMatchObject({ phase: "failed", simulated: true, args: { query: "llm" } });
    expect(toolCallCount(view)).toBe(1);
  });

  it("flags a re-plan only when the questions change", () => {
    const plan = (questions: string[]) =>
      ev({ type: "plan", turn: 1, items: questions.map((question, i) => ({ id: i + 1, question, status: "open" })) });
    const same = replay([started(), plan(["a", "b"]), plan(["a", "b"])]);
    expect(same.replanned).toBe(false);
    const changed = replay([started(), plan(["a", "b"]), plan(["a", "c"])]);
    expect(changed.replanned).toBe(true);
  });

  it("updates evidence in place when a source is enriched", () => {
    const item = { id: "E1", url: "https://a.com", title: "A", source_type: "web", found_by: ["web_researcher"], key_points: ["x"], full_text_read: false, published: null, meta: {} };
    const view = replay([
      started(),
      ev({ type: "evidence", agent: "web_researcher", task_id: "T1", created: true, item }),
      ev({ type: "evidence", agent: "article_reader", task_id: "T2", created: false, item: { ...item, full_text_read: true } }),
    ]);
    expect(view.evidence).toHaveLength(1);
    expect(view.evidence[0].full_text_read).toBe(true);
  });

  it("sums tokens per agent and marks errors", () => {
    const view = replay([
      started(),
      ev({ type: "metrics", agent: "writer", input_tokens: 1000, output_tokens: 200, duration_s: 2, tool_calls: 0 }),
      ev({ type: "metrics", agent: "critic", input_tokens: 500, output_tokens: 100, duration_s: 1, tool_calls: 0 }),
      ev({ type: "agent_error", agent: "critic", error: "quota" }),
    ]);
    expect(totalTokens(view)).toBe(1800);
    expect(view.agents.critic.state).toBe("error");
  });

  it("ignores events it has already applied after a reconnect", () => {
    const first = started();
    const message = ev({ type: "message", id: "m1", sender: "user", recipients: ["coordinator"], kind: "query", summary: "q", content: null });
    const view = replay([first, message, message]);
    expect(view.timeline).toHaveLength(1);
  });

  it("ends as rejected or completed from the final result", () => {
    const result = { status: "rejected", evidence: [] } as unknown;
    const view = replay([started(), ev({ type: "run_completed", result })]);
    expect(view.status).toBe("rejected");
  });

  it("explains whether a rate limit will clear or needs a fallback model", () => {
    const limited = (retry: number | null, detail: string) =>
      ev({ type: "rate_limited", agent: "coordinator", retry_after_s: retry, detail }) as Parameters<typeof rateLimitText>[0];
    expect(rateLimitText(limited(12, "Rate limit reached ... on tokens per minute (TPM): Limit 8000"))).toBe(
      "Rate limited (tokens per minute); retrying in 12s",
    );
    expect(rateLimitText(limited(1025, "Rate limit reached ... on tokens per day (TPD): Limit 200000"))).toBe(
      "Rate limited (tokens per day); switching to a fallback model",
    );
    expect(rateLimitText(limited(null, ""))).toBe("Rate limited by the model provider; retrying");
  });

  it("leaves no agent busy once the run has ended", () => {
    const view = replay([
      started(),
      ev({ type: "agent_status", agent: "coordinator", state: "waiting", detail: "rate limited, retrying in 5s" }),
      ev({ type: "agent_status", agent: "hn_scout", state: "error", detail: "" }),
      ev({ type: "run_failed", error: "boom" }),
    ]);
    expect(view.agents.coordinator).toMatchObject({ state: "idle", detail: "" });
    expect(view.agents.hn_scout.state).toBe("error");
    expect(settleAgents({ writer: { ...view.agents.coordinator, state: "writing" } }).writer.state).toBe("idle");
  });
});
