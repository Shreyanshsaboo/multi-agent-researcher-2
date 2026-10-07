import { describe, expect, it } from "vitest";

import type { RunEvent } from "../types";
import { applyEvent, initialRun } from "./runState";
import { currentActivity, deriveSteps } from "./steps";

let seq = 0;
function message(sender: string, recipients: string[], kind: string, summary: string, content: unknown = null): RunEvent {
  seq += 1;
  return { seq, ts: seq, elapsed: seq, type: "message", id: `m${seq}`, sender, recipients, kind, summary, content } as RunEvent;
}

function view(events: RunEvent[]) {
  const start = { seq: 0, ts: 0, elapsed: 0, type: "run_started", run_id: "r", query: "q",
    options: { depth: "quick", simulate_failures: [] }, agents: [],
    budget: { max_turns: 5, max_drafts: 2, max_tasks_per_turn: 2, max_findings_per_task: 4, max_urls_per_read: 2, time_limit_s: 360 } };
  return [start as RunEvent, ...events]
    .map((e, i) => ({ ...e, seq: i + 1 }))
    .reduce(applyEvent, initialRun("r"));
}

describe("deriveSteps", () => {
  it("follows a run from plan to approval", () => {
    const v = view([
      message("coordinator", ["hn_scout", "web_researcher"], "decision", "Split it up", {
        action: "delegate", plan: [{ id: 1 }, { id: 2 }], turn: 1 }),
      message("coordinator", ["hn_scout"], "task", "Search HN for Rust", { task_id: "T1" }),
      message("coordinator", ["web_researcher"], "task", "Search the web", { task_id: "T2" }),
      message("hn_scout", ["coordinator"], "result", "[success] ok", { task_id: "T1", status: "success", evidence_ids: ["E1", "E2"] }),
      message("web_researcher", ["coordinator"], "result", "[failed] down", { task_id: "T2", status: "failed", summary: "search backend down", evidence_ids: [] }),
      message("coordinator", ["writer"], "decision", "Enough evidence", { action: "draft", turn: 2 }),
      message("coordinator", ["writer"], "brief", "Write it", { version: 1 }),
      message("writer", ["critic"], "draft", "Draft v1: Title", { version: 1 }),
      message("critic", ["coordinator"], "verdict", "REVISE", { verdict: "revise", score: 6, summary: "Needs work", issues: [{}, {}] }),
      message("coordinator", ["writer"], "brief", "Fix it", { version: 2 }),
      message("writer", ["critic"], "draft", "Draft v2: Title; fixed 2, disputed 0", { version: 2 }),
      message("critic", ["coordinator"], "verdict", "APPROVE", { verdict: "approve", score: 9, summary: "Good" }),
    ]);
    const steps = deriveSteps(v);
    expect(steps.map((s) => [s.label, s.state])).toEqual([
      ["Planned 2 research questions", "done"],
      ["Search HN for Rust", "done"],
      ["Search the web", "failed"],
      ["Asked the writer for a draft", "done"],
      ["Wrote the first draft", "done"],
      ["Asked for changes (6/10, 2 issues)", "warn"],
      ["Revised to draft 2", "done"],
      ["Approved the answer (9/10)", "done"],
    ]);
    expect(steps[1].detail).toBe("Found 2 sources");
    expect(steps[2].detail).toBe("search backend down");
    expect(steps[6].detail).toBe("Fixed 2, disputed 0");
  });

  it("describes work in progress", () => {
    const v = view([
      message("coordinator", ["hn_scout"], "decision", "Go", { action: "delegate", plan: [{ id: 1 }], turn: 1 }),
      message("coordinator", ["hn_scout"], "task", "Search HN", { task_id: "T1" }),
    ]);
    expect(deriveSteps(v).at(-1)?.state).toBe("running");
    expect(currentActivity(v)).toBe("HN Scout is working…");
  });
});
