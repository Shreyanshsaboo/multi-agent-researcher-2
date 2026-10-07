import { useMemo } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { SOURCE_LABELS } from "../lib/agents";
import { domainOf } from "../lib/format";
import type { Evidence } from "../types";

const CITATION = /\[(E\d+)\](?!\()/g;

/** Evidence ids in order of first citation, so sources can be numbered 1, 2, 3 for readers. */
export function citationOrder(markdown: string): string[] {
  return [...new Set([...markdown.matchAll(CITATION)].map((m) => m[1]))];
}

function Citation({ n, evidence }: { n: number; evidence?: Evidence }) {
  if (!evidence) return null;
  return (
    <span className="group relative inline-block align-baseline">
      <a
        href={evidence.url}
        target="_blank"
        rel="noreferrer"
        aria-label={`Source ${n}: ${evidence.title}`}
        className="mx-0.5 inline-flex min-w-[1.15rem] items-center justify-center rounded-md bg-sunken px-1 text-[10.5px] leading-[1.15rem] font-semibold text-ink-2 no-underline transition hover:bg-ink hover:text-canvas"
      >
        {n}
      </a>
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-full left-1/2 z-20 mb-2 w-72 -translate-x-1/2 rounded-xl border border-line bg-panel p-3 text-left text-xs leading-snug text-ink-2 opacity-0 shadow-xl transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        <span className="block text-[11px] text-ink-3">
          {domainOf(evidence.url)} · {SOURCE_LABELS[evidence.source_type]}
        </span>
        <span className="mt-0.5 block font-medium text-ink">{evidence.title}</span>
        {evidence.key_points[0] && <span className="mt-1.5 block">{evidence.key_points[0]}</span>}
      </span>
    </span>
  );
}

export function AnswerBody({ markdown, evidence }: { markdown: string; evidence: Evidence[] }) {
  const byId = useMemo(() => Object.fromEntries(evidence.map((e) => [e.id, e])), [evidence]);
  const order = useMemo(() => citationOrder(markdown).filter((id) => byId[id]), [markdown, byId]);
  const numbered = useMemo(() => markdown.replace(CITATION, "[$1](#cite-$1)"), [markdown]);

  return (
    <div>
      <div className="prose-report">
        <Markdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => {
              if (href?.startsWith("#cite-")) {
                const id = href.slice(6);
                return <Citation n={order.indexOf(id) + 1} evidence={byId[id]} />;
              }
              return (
                <a href={href} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2">
                  {children}
                </a>
              );
            },
          }}
        >
          {numbered}
        </Markdown>
      </div>

      {order.length > 0 && (
        <section className="mt-5" aria-label="Sources">
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-ink-3 uppercase">Sources</h3>
          <ol className="grid gap-2 sm:grid-cols-2">
            {order.map((id, i) => {
              const e = byId[id];
              return (
                <li key={id}>
                  <a
                    href={e.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex h-full gap-2.5 rounded-xl border border-line bg-panel p-2.5 transition hover:border-accent/50"
                  >
                    <span className="mt-px flex size-5 shrink-0 items-center justify-center rounded-md bg-sunken text-[10.5px] font-semibold text-ink-2">
                      {i + 1}
                    </span>
                    <span className="min-w-0">
                      <span className="line-clamp-2 text-[13px] leading-snug text-ink">{e.title}</span>
                      <span className="mt-0.5 block truncate text-[11px] text-ink-3">
                        {domainOf(e.url)} · {SOURCE_LABELS[e.source_type]}
                      </span>
                    </span>
                  </a>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </div>
  );
}
