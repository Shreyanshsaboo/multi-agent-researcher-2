import { AlertTriangle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AgentGraph } from "./components/AgentGraph";
import { EvidenceList } from "./components/EvidenceList";
import { HistoryMenu } from "./components/HistoryMenu";
import { PlanPanel } from "./components/PlanPanel";
import { QueryForm } from "./components/QueryForm";
import { ReportView } from "./components/ReportView";
import { ReviewPanel } from "./components/ReviewPanel";
import { StatsBar } from "./components/StatsBar";
import { Timeline } from "./components/Timeline";
import { TracePanel } from "./components/TracePanel";
import { participant } from "./lib/agents";
import { api } from "./lib/api";
import { useRun } from "./lib/useRun";
import type { AgentSpec } from "./types";

type Tab = "report" | "sources" | "review" | "trace";

const STATUS_LABEL: Record<string, string> = {
  connecting: "Connecting",
  running: "Researching",
  completed: "Done",
  rejected: "Declined",
  failed: "Failed",
};

function TeamOverview({ specs }: { specs: AgentSpec[] }) {
  return (
    <section className="rounded-xl border border-line bg-panel p-4">
      <h2 className="text-xs font-semibold tracking-wide text-ink-2 uppercase">The team</h2>
      <p className="mt-1 max-w-3xl text-sm text-ink-2">
        The coordinator plans the research and decides who acts next. Three researchers work in
        parallel with their own tools, the writer drafts a cited report, and the critic checks every
        draft against the evidence and sends it back until it holds up.
      </p>
      <div className="mx-auto mt-4 max-w-3xl">
        <AgentGraph specs={specs} agents={{}} pulses={[]} />
      </div>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {specs.map((spec) => {
          const p = participant(spec.id);
          const Icon = p.icon;
          return (
            <li key={spec.id} className="rounded-lg border border-line p-3">
              <div className="flex items-center gap-2">
                <span className="inline-flex size-7 items-center justify-center rounded-md" style={{ background: `${p.color}22` }}>
                  <Icon className="size-4" style={{ color: p.color }} aria-hidden />
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-ink">{spec.name}</div>
                  <div className="truncate font-mono text-[11px] text-ink-3">{spec.model}</div>
                </div>
              </div>
              <p className="mt-2 text-[13px] text-ink-2">{spec.role}</p>
              {spec.tools.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {spec.tools.map((tool) => (
                    <code key={tool} className="rounded bg-sunken px-1.5 py-px font-mono text-[10.5px] text-ink-2">{tool}</code>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function App() {
  const { view, open, start } = useRun();
  const [tab, setTab] = useState<Tab>("report");
  const [team, setTeam] = useState<AgentSpec[]>([]);
  const [configured, setConfigured] = useState(true);

  useEffect(() => {
    api.agents().then((r) => setTeam(r.agents)).catch(() => undefined);
    api.health().then((h) => setConfigured(h.llm_configured)).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (view.status === "completed" || view.status === "rejected") setTab("report");
  }, [view.status]);

  const specs = view.specs.length ? view.specs : team;
  const live = view.status === "running" || view.status === "connecting";
  const cited = useMemo(() => new Set(view.result?.cited_ids ?? []), [view.result]);

  const tabs: { id: Tab; label: string }[] = [
    { id: "report", label: view.drafts.length > 1 ? `Report (v${view.drafts.length})` : "Report" },
    { id: "sources", label: `Sources (${view.evidence.length})` },
    { id: "review", label: `Review (${view.reviews.length})` },
    { id: "trace", label: "Trace" },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3">
          <a href="/" className="flex min-w-0 items-center gap-2.5">
            <img src="/favicon.svg" alt="" className="size-8" />
            <div className="min-w-0">
              <h1 className="text-[15px] font-semibold tracking-tight text-ink">Multi-Agent Researcher</h1>
              <p className="hidden truncate text-xs text-ink-3 sm:block">
                Six agents plan, research, write and fact-check a cited report
              </p>
            </div>
          </a>
          <HistoryMenu onOpen={open} />
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-5">
        {!configured && (
          <p className="flex items-center gap-2 rounded-lg border border-warn/40 bg-warn/5 px-3 py-2 text-sm text-ink-2" role="alert">
            <AlertTriangle className="size-4 text-warn" aria-hidden />
            The server has no LLM API key configured, so new runs cannot start. Past runs can still be opened.
          </p>
        )}

        <QueryForm
          busy={live}
          onSubmit={async (query, options) => {
            setTab("report");
            await start(query, options);
          }}
        />

        {!view.runId ? (
          specs.length > 0 && <TeamOverview specs={specs} />
        ) : (
          <>
            <section className="rounded-xl border border-line bg-panel p-4">
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                <p className="min-w-0 text-[15px] font-medium text-ink">{view.query || "Loading run…"}</p>
                <span
                  className={`text-xs font-medium ${view.status === "failed" ? "text-bad" : view.status === "completed" ? "text-good" : "text-accent"}`}
                >
                  {STATUS_LABEL[view.status] ?? view.status}
                </span>
              </div>
              <StatsBar view={view} />
              {view.status === "failed" && view.error && (
                <p className="mt-3 text-sm text-bad" role="alert">{view.error}</p>
              )}
            </section>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
              <section className="space-y-5 rounded-xl border border-line bg-panel p-4">
                <AgentGraph specs={specs} agents={view.agents} pulses={view.pulses} />
                <PlanPanel plan={view.plan} turn={view.planTurn} replanned={view.replanned} />
              </section>
              <Timeline entries={view.timeline} live={live} />
            </div>

            <section className="rounded-xl border border-line bg-panel">
              <div className="flex gap-1 overflow-x-auto border-b border-line px-3" role="tablist">
                {tabs.map((t) => (
                  <button
                    key={t.id}
                    role="tab"
                    aria-selected={tab === t.id}
                    onClick={() => setTab(t.id)}
                    className={`-mb-px border-b-2 px-3 py-2.5 text-sm whitespace-nowrap ${tab === t.id ? "border-accent font-medium text-ink" : "border-transparent text-ink-3 hover:text-ink-2"}`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="p-4 sm:p-6">
                {tab === "report" && <ReportView view={view} />}
                {tab === "sources" && <EvidenceList evidence={view.evidence} cited={cited} />}
                {tab === "review" && <ReviewPanel drafts={view.drafts} reviews={view.reviews} />}
                {tab === "trace" && <TracePanel view={view} />}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
