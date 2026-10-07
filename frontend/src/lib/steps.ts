import type { Participant } from "../types";
import { participant } from "./agents";
import type { RunView, TimelineEntry } from "./runState";

export type StepState = "running" | "done" | "warn" | "failed";

/** One line in the "what the team is doing" list shown with an answer. */
export interface Step {
  id: string;
  agent: Participant;
  label: string;
  detail?: string;
  state: StepState;
  note?: string;
}

const ACTION_LABEL: Record<string, string> = {
  delegate: "Sent the researchers out",
  draft: "Asked the writer for a draft",
  finish: "Accepted the answer",
  reject: "Declined the question",
};

function clip(text: string, max = 110): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

type MessageEntry = Extract<TimelineEntry, { kind: "message" }>;

/** Collapse a run's messages into a short list of steps, in the order they happened. */
export function deriveSteps(view: RunView): Step[] {
  const steps: Step[] = [];
  const byId = new Map<string, Step>();
  const add = (step: Step) => {
    steps.push(step);
    byId.set(step.id, step);
  };
  let reviewing: Step | null = null;

  if (view.carried > 0) {
    add({ id: "context", agent: "coordinator", state: "done",
          label: `Reused ${view.carried} source${view.carried > 1 ? "s" : ""} from earlier in this conversation` });
  }

  const messages = view.timeline.filter((e): e is MessageEntry => e.kind === "message");
  let decisions = 0;
  for (const { event } of messages) {
    const content = (event.content ?? {}) as Record<string, unknown>;
    switch (event.kind) {
      case "decision": {
        decisions += 1;
        const plan = (content.plan as unknown[] | undefined) ?? [];
        const label = decisions === 1 && plan.length
          ? `Planned ${plan.length} research question${plan.length > 1 ? "s" : ""}`
          : ACTION_LABEL[String(content.action)] ?? "Decided the next step";
        add({ id: `decision-${event.id}`, agent: "coordinator", state: "done", label,
              detail: (content.fallback ? "Fallback policy: " : "") + event.summary });
        break;
      }
      case "task":
        add({ id: `task-${content.task_id}`, agent: event.recipients[0], state: "running",
              label: clip(event.summary) });
        break;
      case "result": {
        const step = byId.get(`task-${content.task_id}`);
        if (!step) break;
        const found = (content.evidence_ids as string[] | undefined)?.length ?? 0;
        step.state = content.status === "failed" ? "failed" : content.status === "partial" ? "warn" : "done";
        step.detail = content.status === "failed"
          ? clip(String(content.summary ?? "failed"), 160)
          : `Found ${found} source${found === 1 ? "" : "s"}`;
        break;
      }
      case "brief": {
        const version = Number(content.version ?? 1);
        add({ id: `write-${version}`, agent: "writer", state: "running",
              label: version === 1 ? "Writing the answer" : `Revising the answer (draft ${version})` });
        break;
      }
      case "draft": {
        const version = Number(content.version ?? 1);
        const step = byId.get(`write-${version}`);
        if (step) {
          step.state = "done";
          step.label = version === 1 ? "Wrote the first draft" : `Revised to draft ${version}`;
          const fixed = event.summary.split("; ")[1];
          if (fixed) step.detail = fixed.charAt(0).toUpperCase() + fixed.slice(1);
        }
        reviewing = { id: `review-${version}`, agent: "critic", state: "running", label: `Fact-checking draft ${version}` };
        add(reviewing);
        break;
      }
      case "verdict": {
        if (!reviewing) break;
        const verdict = content.verdict as string | undefined;
        if (!verdict) {
          reviewing.state = "warn";
          reviewing.label = "Review skipped";
          reviewing.detail = event.summary;
        } else {
          const issues = (content.issues as unknown[] | undefined)?.length ?? 0;
          reviewing.state = verdict === "approve" ? "done" : "warn";
          reviewing.label = verdict === "approve"
            ? `Approved the answer (${content.score}/10)`
            : `Asked for changes (${content.score}/10, ${issues} issue${issues === 1 ? "" : "s"})`;
          reviewing.detail = clip(String(content.summary ?? ""), 180);
        }
        reviewing = null;
        break;
      }
    }
  }

  // While live, say why a busy agent is quiet (usually a rate-limit wait).
  if (view.status === "running") {
    for (const step of steps) {
      if (step.state !== "running") continue;
      const status = view.agents[step.agent];
      if (status?.state === "waiting") step.note = "waiting for the model provider's rate limit";
    }
  }
  return steps;
}

/** A one-line description of what is happening right now. */
export function currentActivity(view: RunView): string {
  if (view.status === "connecting") return "Connecting…";
  const running = deriveSteps(view).filter((s) => s.state === "running");
  if (running.length === 0) return view.timeline.length ? "Coordinator is deciding the next step…" : "Coordinator is planning…";
  const names = [...new Set(running.map((s) => participant(s.agent).label))];
  return `${names.join(" and ")} ${names.length > 1 ? "are" : "is"} working…`;
}
