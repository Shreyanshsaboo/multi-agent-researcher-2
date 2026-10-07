import { History } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../lib/api";
import { timeAgo } from "../lib/format";
import type { RunSummary } from "../types";

const STATUS_STYLE: Record<string, string> = {
  completed: "text-good",
  running: "text-accent",
  rejected: "text-ink-3",
  failed: "text-bad",
};

export function HistoryMenu({ onOpen }: { onOpen: (runId: string) => void }) {
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    api.runs().then((r) => setRuns(r.runs)).catch((e: Error) => setError(e.message));
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-2 hover:text-ink"
      >
        <History className="size-3.5" aria-hidden /> History
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-line bg-panel shadow-xl">
          <div className="border-b border-line px-3 py-2 text-xs font-semibold text-ink-2">Recent runs</div>
          <ul className="max-h-96 overflow-y-auto">
            {error && <li className="px-3 py-3 text-sm text-bad">{error}</li>}
            {runs?.length === 0 && <li className="px-3 py-3 text-sm text-ink-3">No runs yet.</li>}
            {runs?.map((run) => (
              <li key={run.id}>
                <button
                  onClick={() => {
                    setOpen(false);
                    onOpen(run.id);
                  }}
                  className="w-full px-3 py-2 text-left hover:bg-sunken"
                >
                  <div className="truncate text-sm text-ink">{run.title || run.query}</div>
                  <div className="mt-0.5 flex gap-2 text-[11px] text-ink-3">
                    <span className={STATUS_STYLE[run.status] ?? ""}>{run.status}</span>
                    {run.score !== null && <span>score {run.score}/10</span>}
                    <span>{timeAgo(run.created_at)}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
