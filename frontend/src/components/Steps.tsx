import { AlertTriangle, Check, ChevronDown, ChevronUp, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { participant } from "../lib/agents";
import { seconds } from "../lib/format";
import type { RunView } from "../lib/runState";
import { currentActivity, deriveSteps, type Step } from "../lib/steps";

function useElapsed(view: RunView): number {
  const [now, setNow] = useState(() => Date.now());
  const live = view.status === "running";
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [live]);
  if (view.result) return view.result.stats.duration_s;
  if (live && view.startedTs) return Math.max(view.lastElapsed, now / 1000 - view.startedTs);
  return view.lastElapsed;
}

function StepIcon({ step }: { step: Step }) {
  if (step.state === "running") return <Loader2 className="size-3.5 animate-spin text-ink-3" aria-label="in progress" />;
  if (step.state === "failed") return <X className="size-3.5 text-bad" aria-label="failed" />;
  if (step.state === "warn") return <AlertTriangle className="size-3.5 text-warn" aria-label="needs attention" />;
  return <Check className="size-3.5 text-ink-3" aria-label="done" />;
}

/** The team's progress on one question: expanded while working, one line once done. */
export function Steps({ view }: { view: RunView }) {
  const live = view.status === "running" || view.status === "connecting";
  // Open while the team works and closed once it is done, unless the reader chose otherwise.
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open = toggled ?? live;
  const steps = deriveSteps(view);
  const elapsed = useElapsed(view);

  const agentsUsed = new Set(steps.map((s) => s.agent)).size;
  const summary = live
    ? currentActivity(view)
    : `Worked through ${steps.length} step${steps.length === 1 ? "" : "s"} with ${agentsUsed} agent${agentsUsed === 1 ? "" : "s"}`;

  return (
    <div className="rounded-xl border border-line bg-panel">
      <button
        onClick={() => setToggled(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[13px]"
      >
        {live ? <Loader2 className="size-4 shrink-0 animate-spin text-ink-3" aria-hidden /> : <Check className="size-4 shrink-0 text-ink-3" aria-hidden />}
        <span className="min-w-0 flex-1 truncate text-ink-2">{summary}</span>
        <span className="font-mono text-[11px] text-ink-3 tabular-nums">{seconds(elapsed)}</span>
        {open ? <ChevronUp className="size-4 shrink-0 text-ink-3" aria-hidden /> : <ChevronDown className="size-4 shrink-0 text-ink-3" aria-hidden />}
      </button>
      {open && (
        <ol className="space-y-2.5 border-t border-line px-3 py-3">
          {steps.length === 0 && <li className="text-[13px] text-ink-3">The coordinator is reading your question…</li>}
          {steps.map((step) => {
            const who = participant(step.agent);
            return (
              <li key={step.id} className="flex gap-2.5">
                <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center">
                  <StepIcon step={step} />
                </span>
                <div className="min-w-0 text-[13px] leading-snug">
                  <span className="mr-1.5 font-medium text-ink">{who.label}</span>
                  <span className="text-ink-2">{step.label}</span>
                  {step.detail && <p className="mt-0.5 text-ink-3">{step.detail}</p>}
                  {step.note && <p className="mt-0.5 text-warn">{step.note}</p>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
