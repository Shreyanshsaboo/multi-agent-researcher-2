import { ArrowUp, FlaskConical, Loader2 } from "lucide-react";
import { type FormEvent, useState } from "react";

import { participant } from "../lib/agents";
import type { Depth, RunOptions, WorkerId } from "../types";

const EXAMPLES = [
  "How are teams cutting LLM inference costs in 2026?",
  "What do developers think about Rust in the Linux kernel?",
  "Is SQLite a good choice for production web apps?",
  "What changed in the EU AI Act rules for general-purpose models?",
];

const DEPTHS: { id: Depth; label: string; hint: string }[] = [
  { id: "quick", label: "Quick", hint: "5 turns, up to 2 drafts" },
  { id: "standard", label: "Standard", hint: "8 turns, up to 3 drafts" },
  { id: "deep", label: "Deep", hint: "12 turns, up to 4 drafts" },
];

const WORKERS: WorkerId[] = ["hn_scout", "web_researcher", "article_reader"];

export function QueryForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (query: string, options: RunOptions) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState<Depth>("quick");
  const [failures, setFailures] = useState<WorkerId[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const disabled = busy || submitting;

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = query.trim();
    if (!text || disabled) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(text, { depth, simulate_failures: failures });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the run.");
    } finally {
      setSubmitting(false);
    }
  }

  function toggleFailure(id: WorkerId) {
    setFailures((current) => (current.includes(id) ? current.filter((f) => f !== id) : [...current, id]));
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-line bg-panel p-4 shadow-sm">
      <label htmlFor="query" className="sr-only">Research question</label>
      <div className="flex items-end gap-2">
        <textarea
          id="query"
          rows={2}
          maxLength={500}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder="Ask a research question, e.g. how are teams cutting LLM inference costs?"
          className="min-h-[3.25rem] flex-1 resize-none bg-transparent text-[15px] text-ink placeholder:text-ink-3 focus:outline-none"
        />
        <button
          type="submit"
          disabled={disabled || !query.trim()}
          aria-label="Start research"
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {disabled ? <Loader2 className="size-5 animate-spin" /> : <ArrowUp className="size-5" />}
        </button>
      </div>

      {error && <p className="mt-2 text-sm text-bad" role="alert">{error}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-line pt-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-ink-3">Depth</span>
          <div className="flex rounded-lg bg-sunken p-0.5" role="radiogroup" aria-label="Research depth">
            {DEPTHS.map((d) => (
              <button
                type="button"
                key={d.id}
                role="radio"
                aria-checked={depth === d.id}
                title={d.hint}
                onClick={() => setDepth(d.id)}
                className={`rounded-md px-2.5 py-1 text-xs ${depth === d.id ? "bg-panel font-medium text-ink shadow-sm" : "text-ink-2 hover:text-ink"}`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center gap-1 text-xs text-ink-3" title="Make every tool call of these agents fail, to watch the team re-plan around them">
            <FlaskConical className="size-3.5" aria-hidden /> Simulate outage
          </span>
          {WORKERS.map((id) => {
            const on = failures.includes(id);
            return (
              <button
                type="button"
                key={id}
                aria-pressed={on}
                onClick={() => toggleFailure(id)}
                className={`rounded-full border px-2.5 py-0.5 text-xs ${on ? "border-bad/50 bg-bad/10 text-bad" : "border-line text-ink-2 hover:text-ink"}`}
              >
                {participant(id).label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {EXAMPLES.map((example) => (
          <button
            type="button"
            key={example}
            onClick={() => setQuery(example)}
            className="rounded-full bg-sunken px-2.5 py-1 text-xs text-ink-2 hover:text-ink"
          >
            {example}
          </button>
        ))}
      </div>
    </form>
  );
}
