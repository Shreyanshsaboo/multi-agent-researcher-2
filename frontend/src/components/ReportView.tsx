import { AlertTriangle, BadgeCheck, CircleHelp, Download, FileJson, Info, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { SOURCE_LABELS } from "../lib/agents";
import { api } from "../lib/api";
import { domainOf } from "../lib/format";
import type { RunView } from "../lib/runState";
import type { Evidence, Review } from "../types";

const CITATION = /\[(E\d+)\](?!\()/g;

function Citation({ id, evidence }: { id: string; evidence?: Evidence }) {
  if (!evidence) {
    return <span className="rounded bg-bad/10 px-1 font-mono text-[11px] text-bad" title="Unknown source">{id}</span>;
  }
  return (
    <span className="group relative inline-block align-baseline">
      <a
        href={evidence.url}
        target="_blank"
        rel="noreferrer"
        className="mx-px rounded bg-accent-soft px-1 font-mono text-[11px] font-medium text-accent no-underline hover:underline"
      >
        {id}
      </a>
      <span
        role="tooltip"
        className="invisible absolute bottom-full left-1/2 z-20 mb-1.5 w-72 -translate-x-1/2 rounded-lg border border-line bg-panel p-3 text-left text-xs leading-snug text-ink-2 shadow-lg group-focus-within:visible group-hover:visible"
      >
        <span className="block font-medium text-ink">{evidence.title}</span>
        <span className="mt-0.5 block text-ink-3">
          {SOURCE_LABELS[evidence.source_type]} · {domainOf(evidence.url)}
          {evidence.full_text_read ? " · full text read" : ""}
        </span>
        {evidence.key_points[0] && <span className="mt-1.5 block">{evidence.key_points[0]}</span>}
      </span>
    </span>
  );
}

function ReviewBadge({ review }: { review?: Review }) {
  if (!review) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-sunken px-2.5 py-1 text-xs text-ink-2">
        <Loader2 className="size-3.5 animate-spin" aria-hidden /> Under review
      </span>
    );
  }
  if (!review.critique) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-sunken px-2.5 py-1 text-xs text-ink-2">
        <CircleHelp className="size-3.5" aria-hidden /> Not reviewed
      </span>
    );
  }
  const { verdict, score } = review.critique;
  return verdict === "approve" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-good/10 px-2.5 py-1 text-xs font-medium text-good">
      <BadgeCheck className="size-3.5" aria-hidden /> Approved by the Critic · {score}/10
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-warn/10 px-2.5 py-1 text-xs font-medium text-warn">
      <AlertTriangle className="size-3.5" aria-hidden /> Critic asked for revisions · {score}/10
    </span>
  );
}

export function ReportView({ view }: { view: RunView }) {
  const [picked, setPicked] = useState<number | null>(null);
  const evidenceById = useMemo(() => Object.fromEntries(view.evidence.map((e) => [e.id, e])), [view.evidence]);

  const latest = view.drafts[view.drafts.length - 1];
  const draft = view.drafts.find((d) => d.version === picked) ?? latest;
  const review = draft && view.reviews.find((r) => r.draft_version === draft.version);
  const result = view.result;
  // Run-level notes (coordinator message, open issues) belong to the final draft only.
  const final = result && draft?.version === latest?.version ? result : null;

  const markdown = useMemo(() => (draft ? draft.markdown.replace(CITATION, "[$1](#cite-$1)") : ""), [draft]);
  const cited = useMemo(() => {
    const ids = [...new Set([...(draft?.markdown.matchAll(CITATION) ?? [])].map((m) => m[1]))];
    return ids.map((id) => evidenceById[id]).filter(Boolean);
  }, [draft, evidenceById]);

  if (view.status === "rejected" && result) {
    return (
      <div className="flex gap-3 rounded-lg border border-line bg-sunken p-4 text-sm">
        <Info className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
        <div>
          <p className="font-medium text-ink">The coordinator declined this query.</p>
          <p className="mt-1 text-ink-2">{result.message}</p>
        </div>
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="py-12 text-center text-sm text-ink-3">
        {view.status === "running" || view.status === "connecting"
          ? "The team is researching. The report appears here when the Writer submits a draft."
          : view.status === "failed"
            ? `The run failed: ${view.error ?? "unknown error"}`
            : result?.message || "Ask a question to start a research run."}
      </div>
    );
  }

  return (
    <article>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-tight text-ink">{draft.title}</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {draft.fallback ? (
              <span className="rounded-full bg-warn/10 px-2.5 py-1 text-xs font-medium text-warn">
                Evidence digest (writer unavailable)
              </span>
            ) : (
              <ReviewBadge review={review} />
            )}
            {view.drafts.length > 1 && (
              <div className="flex gap-1" aria-label="Draft versions">
                {view.drafts.map((d) => (
                  <button
                    key={d.version}
                    onClick={() => setPicked(d.version)}
                    className={`rounded-md px-2 py-0.5 text-xs ${d.version === draft.version ? "bg-ink text-panel" : "bg-sunken text-ink-2 hover:text-ink"}`}
                  >
                    v{d.version}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        {result && view.runId && (
          <div className="flex gap-2">
            <a href={api.reportUrl(view.runId)} download className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-2 hover:text-ink">
              <Download className="size-3.5" aria-hidden /> Report .md
            </a>
            <a href={api.traceUrl(view.runId)} download className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-2 hover:text-ink">
              <FileJson className="size-3.5" aria-hidden /> Trace .json
            </a>
          </div>
        )}
      </div>

      {final?.message && (
        <p className="mt-4 flex gap-2 rounded-lg bg-sunken px-3 py-2 text-sm text-ink-2">
          <Info className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
          <span>
            <span className="font-medium text-ink">Coordinator: </span>
            {final.message}
          </span>
        </p>
      )}

      <div className="prose-report mt-5 max-w-3xl">
        <Markdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) =>
              href?.startsWith("#cite-") ? (
                <Citation id={href.slice(6)} evidence={evidenceById[href.slice(6)]} />
              ) : (
                <a href={href} target="_blank" rel="noreferrer" className="text-accent underline">
                  {children}
                </a>
              ),
          }}
        >
          {markdown}
        </Markdown>
      </div>

      {final && final.unresolved_issues.length > 0 && (
        <section className="mt-6 max-w-3xl rounded-lg border border-warn/40 bg-warn/5 p-4">
          <h3 className="text-sm font-semibold text-ink">Open issues from the Critic</h3>
          <ul className="mt-2 space-y-1.5 text-sm text-ink-2">
            {final.unresolved_issues.map((issue) => (
              <li key={issue.id}>
                <span className="font-mono text-xs text-ink-3">{issue.id} · {issue.severity}</span> {issue.detail}
              </li>
            ))}
          </ul>
        </section>
      )}

      {cited.length > 0 && (
        <section className="mt-8 max-w-3xl border-t border-line pt-4">
          <h3 className="text-sm font-semibold text-ink">Sources</h3>
          <ol className="mt-2 space-y-1.5 text-sm">
            {cited.map((e) => (
              <li key={e.id} className="flex gap-2">
                <span className="w-8 shrink-0 font-mono text-xs text-ink-3">{e.id}</span>
                <span className="min-w-0">
                  <a href={e.url} target="_blank" rel="noreferrer" className="text-ink hover:text-accent hover:underline">
                    {e.title}
                  </a>
                  <span className="text-ink-3"> · {SOURCE_LABELS[e.source_type]} · {domainOf(e.url)}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </article>
  );
}
