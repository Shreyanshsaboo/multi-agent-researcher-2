import { BookOpenCheck, ExternalLink } from "lucide-react";

import { participant, SOURCE_LABELS } from "../lib/agents";
import { domainOf } from "../lib/format";
import type { Evidence } from "../types";

export function EvidenceList({ evidence, cited }: { evidence: Evidence[]; cited: Set<string> }) {
  if (evidence.length === 0) {
    return <p className="py-12 text-center text-sm text-ink-3">Sources the researchers save appear here.</p>;
  }
  return (
    <ul className="grid gap-3 md:grid-cols-2">
      {evidence.map((e) => (
        <li key={e.id} className="rounded-lg border border-line bg-panel p-3">
          <div className="flex items-start gap-2">
            <span className="mt-0.5 rounded bg-sunken px-1.5 py-px font-mono text-[11px] text-ink-2">{e.id}</span>
            <div className="min-w-0 flex-1">
              <a
                href={e.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-start gap-1 text-sm font-medium text-ink hover:text-accent"
              >
                <span className="break-words">{e.title}</span>
                <ExternalLink className="mt-0.5 size-3 shrink-0 text-ink-3" aria-hidden />
              </a>
              <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-3">
                <span className="rounded bg-sunken px-1.5 py-px text-ink-2">{SOURCE_LABELS[e.source_type]}</span>
                <span>{domainOf(e.url)}</span>
                {e.published && <span>{e.published}</span>}
                {e.full_text_read && (
                  <span className="inline-flex items-center gap-0.5 text-good">
                    <BookOpenCheck className="size-3" aria-hidden /> full text
                  </span>
                )}
                {cited.has(e.id) && <span className="font-medium text-accent">cited</span>}
              </div>
            </div>
          </div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] text-ink-2">
            {e.key_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-ink-3">
            found by
            {e.found_by.map((agentId) => (
              <span key={agentId} className="inline-flex items-center gap-1 text-ink-2">
                <span className="size-1.5 rounded-full" style={{ background: participant(agentId).color }} aria-hidden />
                {participant(agentId).label}
              </span>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}
