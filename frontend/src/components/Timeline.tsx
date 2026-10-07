import {
  AlertTriangle,
  ArrowRight,
  Check,
  FilePlus2,
  History,
  Hourglass,
  Loader2,
  ShieldAlert,
  Shuffle,
  Wrench,
  X,
} from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { participant } from "../lib/agents";
import { formatArgs } from "../lib/format";
import type { NoticeTone, TimelineEntry } from "../lib/runState";

type Filter = "all" | "message" | "tool" | "notice";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "message", label: "Messages" },
  { id: "tool", label: "Tool calls" },
  { id: "notice", label: "Events" },
];

const NOTICE_STYLE: Record<NoticeTone, { icon: typeof Hourglass; className: string }> = {
  guard: { icon: ShieldAlert, className: "text-warn" },
  wait: { icon: Hourglass, className: "text-warn" },
  error: { icon: AlertTriangle, className: "text-bad" },
  fallback: { icon: Shuffle, className: "text-accent" },
  memory: { icon: History, className: "text-accent" },
  evidence: { icon: FilePlus2, className: "text-good" },
};

function Who({ id }: { id: string }) {
  const p = participant(id);
  return (
    <span className="inline-flex items-center gap-1 font-medium text-ink">
      <span className="size-2 rounded-full" style={{ background: p.color }} aria-hidden />
      {p.label}
    </span>
  );
}

function Time({ value }: { value: number }) {
  return <span className="w-12 shrink-0 pt-0.5 text-right font-mono text-[11px] text-ink-3 tabular-nums">{value.toFixed(1)}s</span>;
}

function Payload({ value }: { value: unknown }) {
  if (value === null || value === undefined) return null;
  return (
    <details className="group mt-1">
      <summary className="cursor-pointer text-[11px] text-ink-3 select-none hover:text-ink-2">payload</summary>
      <pre className="mt-1 max-h-72 overflow-auto rounded-md bg-sunken p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-ink-2">
        {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

function Entry({ entry }: { entry: TimelineEntry }) {
  if (entry.kind === "message") {
    const e = entry.event;
    return (
      <li className="flex gap-3 py-2">
        <Time value={entry.elapsed} />
        <div className="min-w-0 flex-1 text-sm">
          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
            <Who id={e.sender} />
            <ArrowRight className="size-3.5 text-ink-3" aria-label="to" />
            {e.recipients.map((r) => <Who key={r} id={r} />)}
            <span className="rounded bg-sunken px-1.5 py-px font-mono text-[10.5px] text-ink-2">{e.kind}</span>
          </div>
          <p className="mt-0.5 line-clamp-3 text-ink-2 [overflow-wrap:anywhere]">{e.summary}</p>
          <Payload value={e.content} />
        </div>
      </li>
    );
  }

  if (entry.kind === "tool") {
    const c = entry.call;
    const p = participant(c.agent);
    return (
      <li className="flex gap-3 py-1.5">
        <Time value={entry.elapsed} />
        <div className="min-w-0 flex-1 text-[13px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <Wrench className="size-3.5" style={{ color: p.color }} aria-hidden />
            <span className="text-ink-2">{p.label}</span>
            <code className="font-mono text-[12px] break-all text-ink">
              {c.tool}({formatArgs(c.args)})
            </code>
            {c.phase === "started" && <Loader2 className="size-3.5 animate-spin text-ink-3" aria-label="running" />}
            {c.phase === "completed" && (
              <span className="inline-flex items-center gap-0.5 text-[11px] text-good">
                <Check className="size-3.5" aria-hidden />
                {c.durationMs !== undefined && `${c.durationMs}ms`}
              </span>
            )}
            {c.phase === "failed" && (
              <span className="inline-flex items-center gap-0.5 text-[11px] text-bad">
                <X className="size-3.5" aria-hidden /> failed
              </span>
            )}
            {c.simulated && (
              <span className="rounded bg-bad/10 px-1.5 py-px text-[10.5px] font-medium text-bad">simulated outage</span>
            )}
          </div>
          {c.error && <p className="mt-0.5 text-[12px] text-bad [overflow-wrap:anywhere]">{c.error}</p>}
          {c.preview && <Payload value={c.preview} />}
        </div>
      </li>
    );
  }

  const style = NOTICE_STYLE[entry.tone];
  const Icon = style.icon;
  return (
    <li className="flex gap-3 py-1.5">
      <Time value={entry.elapsed} />
      <div className="flex min-w-0 flex-1 gap-1.5 text-[13px]">
        <Icon className={`mt-0.5 size-3.5 shrink-0 ${style.className}`} aria-hidden />
        <span className="min-w-0 text-ink-2 [overflow-wrap:anywhere]">
          <span className="font-medium text-ink">{participant(entry.agent).label}: </span>
          {entry.text}
        </span>
      </div>
    </li>
  );
}

export function Timeline({ entries, live }: { entries: TimelineEntry[]; live: boolean }) {
  const [filter, setFilter] = useState<Filter>("all");
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const shown = filter === "all" ? entries : entries.filter((e) => e.kind === filter);

  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [shown.length]);

  useEffect(() => {
    pinned.current = true;
  }, [filter]);

  return (
    <section aria-labelledby="timeline-heading" className="flex min-h-0 flex-col">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="timeline-heading" className="flex items-center gap-2 text-xs font-semibold tracking-wide text-ink-2 uppercase">
          Agent messages
          {live && <span className="size-1.5 animate-pulse rounded-full bg-good" aria-label="live" />}
        </h2>
        <div className="flex gap-1" role="tablist" aria-label="Filter events">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={`rounded-md px-2 py-0.5 text-xs ${filter === f.id ? "bg-accent-soft font-medium text-accent" : "text-ink-3 hover:text-ink-2"}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
        }}
        className="h-[460px] overflow-y-auto rounded-lg border border-line bg-panel px-3 lg:h-[540px]"
      >
        {shown.length === 0 ? (
          <p className="py-10 text-center text-sm text-ink-3">
            {live ? "Waiting for the first message…" : "Messages between the agents appear here as they work."}
          </p>
        ) : (
          <ol className="divide-y divide-line">
            {shown.map((entry) => (
              <Entry key={`${entry.kind}-${entry.seq}`} entry={entry} />
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
