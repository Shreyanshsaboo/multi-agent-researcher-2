import { useEffect, useState } from "react";

import { compactNumber, seconds } from "../lib/format";
import { type RunView, toolCallCount, totalTokens } from "../lib/runState";

function useElapsed(view: RunView): number {
  const [now, setNow] = useState(() => Date.now());
  const live = view.status === "running";
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [live]);
  if (view.result) return view.result.stats.duration_s;
  if (live && view.startedTs) return Math.max(view.lastElapsed, now / 1000 - view.startedTs);
  return view.lastElapsed;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-ink-3">{label}</div>
      <div className="font-mono text-sm font-medium text-ink tabular-nums">{value}</div>
    </div>
  );
}

export function StatsBar({ view }: { view: RunView }) {
  const elapsed = useElapsed(view);
  const budget = view.budget;
  return (
    <div className="grid grid-cols-3 gap-x-4 gap-y-3 sm:grid-cols-6">
      <Stat label="Elapsed" value={seconds(elapsed)} />
      <Stat label="Turn" value={budget ? `${view.turn} / ${budget.max_turns}` : `${view.turn}`} />
      <Stat label="Tasks" value={`${view.tasks}`} />
      <Stat label="Tool calls" value={`${toolCallCount(view)}`} />
      <Stat label="Sources" value={`${view.evidence.length}`} />
      <Stat label="Tokens" value={compactNumber(totalTokens(view))} />
    </div>
  );
}
