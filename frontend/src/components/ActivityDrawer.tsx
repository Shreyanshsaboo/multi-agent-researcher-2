import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useRunView } from "../lib/runStore";
import { AgentGraph } from "./AgentGraph";
import { EvidenceList } from "./EvidenceList";
import { PlanPanel } from "./PlanPanel";
import { ReviewPanel } from "./ReviewPanel";
import { StatsBar } from "./StatsBar";
import { Timeline } from "./Timeline";
import { TracePanel } from "./TracePanel";

type Tab = "agents" | "review" | "sources" | "trace";

/** Everything the agents did for one question: who talked to whom, the drafts and reviews, the raw trace. */
export function ActivityDrawer({ runId, onClose }: { runId: string; onClose: () => void }) {
  const view = useRunView(runId);
  const [tab, setTab] = useState<Tab>("agents");
  const cited = useMemo(() => new Set(view.result?.cited_ids ?? []), [view.result]);
  const live = view.status === "running" || view.status === "connecting";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tabs: { id: Tab; label: string }[] = [
    { id: "agents", label: "Agents" },
    { id: "review", label: `Drafts and review (${view.reviews.length})` },
    { id: "sources", label: `All sources (${view.evidence.length})` },
    { id: "trace", label: "Trace" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Agent activity">
      <div className="absolute inset-0 bg-black/25" onClick={onClose} aria-hidden />
      <div className="relative flex h-full w-full max-w-3xl flex-col border-l border-line bg-canvas shadow-2xl">
        <header className="flex items-start gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium tracking-wide text-ink-3 uppercase">Agent activity</p>
            <h2 className="mt-0.5 truncate font-serif text-lg text-ink">{view.query || "Loading…"}</h2>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-ink-3 hover:text-ink" aria-label="Close">
            <X className="size-5" />
          </button>
        </header>

        <div className="border-b border-line px-5 py-3">
          <StatsBar view={view} />
        </div>

        <nav className="flex gap-5 overflow-x-auto border-b border-line px-5" role="tablist">
          {tabs.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`-mb-px border-b py-2.5 text-[13px] whitespace-nowrap ${tab === t.id ? "border-ink text-ink" : "border-transparent text-ink-3 hover:text-ink-2"}`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {tab === "agents" && (
            <div className="space-y-6">
              <AgentGraph specs={view.specs} agents={view.agents} pulses={view.pulses} />
              <PlanPanel plan={view.plan} turn={view.planTurn} replanned={view.replanned} />
              <Timeline entries={view.timeline} live={live} />
            </div>
          )}
          {tab === "review" && <ReviewPanel drafts={view.drafts} reviews={view.reviews} />}
          {tab === "sources" && <EvidenceList evidence={view.evidence} cited={cited} />}
          {tab === "trace" && <TracePanel view={view} />}
        </div>
      </div>
    </div>
  );
}
