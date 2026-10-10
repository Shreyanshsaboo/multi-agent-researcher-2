import { ArrowUp, Loader2 } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { participant } from "../lib/agents";
import type { Depth, RunOptions, WorkerId } from "../types";

const DEPTHS: { id: Depth; label: string; hint: string }[] = [
  { id: "quick", label: "Quick", hint: "Fastest: up to 5 coordinator turns and 2 drafts" },
  { id: "standard", label: "Standard", hint: "Up to 8 turns and 3 drafts" },
  { id: "deep", label: "Deep", hint: "Most thorough: up to 12 turns and 4 drafts" },
];

const WORKERS: WorkerId[] = ["hn_scout", "web_researcher", "article_reader"];

export function Composer({
  busy,
  followUp,
  autoFocus,
  draft,
  onSubmit,
}: {
  onSubmit: (query: string, options: RunOptions) => Promise<void>;
  busy: boolean;
  followUp: boolean;
  autoFocus?: boolean;
  /** Text to place in the box, e.g. a chosen example; the key makes repeats count. */
  draft?: { text: string; key: number };
}) {
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState<Depth>("quick");
  const [failures, setFailures] = useState<WorkerId[]>([]);
  const [showDemo, setShowDemo] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  // Take over a new draft when the prop changes (during render, not in an effect). The one
  // present at mount is stale: it is the question that was just asked from the start page.
  const [adopted, setAdopted] = useState(draft);
  if (draft !== adopted) {
    setAdopted(draft);
    if (draft) setQuery(draft.text);
  }

  useEffect(() => {
    if (adopted) box.current?.focus();
  }, [adopted]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [query]);

  const disabled = busy || sending;

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = query.trim();
    if (!text || disabled) return;
    setSending(true);
    setError(null);
    try {
      await onSubmit(text, { depth, simulate_failures: failures });
      setQuery("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the question.");
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={submit} className="relative">
      <div className="rounded-2xl border border-line bg-panel shadow-sm transition focus-within:border-ink-3">
        <label htmlFor="question" className="sr-only">Your question</label>
        <textarea
          id="question"
          ref={box}
          rows={1}
          maxLength={500}
          autoFocus={autoFocus}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder={followUp ? "Ask a follow-up…" : "Ask a research question…"}
          className="block max-h-[200px] w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-[15px] text-ink placeholder:text-ink-3 focus:outline-none"
        />
        <div className="flex items-center gap-1.5 px-2.5 pb-2.5">
          <div className="flex rounded-lg bg-sunken p-0.5" role="radiogroup" aria-label="Research depth">
            {DEPTHS.map((d) => (
              <button
                type="button"
                key={d.id}
                role="radio"
                aria-checked={depth === d.id}
                title={d.hint}
                onClick={() => setDepth(d.id)}
                className={`rounded-md px-2 py-0.5 text-xs ${depth === d.id ? "bg-panel font-medium text-ink shadow-sm" : "text-ink-3 hover:text-ink-2"}`}
              >
                {d.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setShowDemo((s) => !s)}
            aria-expanded={showDemo}
            title="Demo: simulate an outage"
            className={`rounded-lg px-2 py-1 text-xs ${failures.length ? "text-bad" : "text-ink-3 hover:text-ink-2"}`}
          >
            {failures.length ? `${failures.length} simulated outage${failures.length > 1 ? "s" : ""}` : "Options"}
          </button>
          <button
            type="submit"
            disabled={disabled || !query.trim()}
            aria-label="Send"
            className="ml-auto inline-flex size-8 items-center justify-center rounded-full bg-ink text-canvas transition hover:opacity-90 disabled:opacity-30"
          >
            {disabled ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
          </button>
        </div>
      </div>

      {showDemo && (
        <div className="absolute bottom-full left-0 z-20 mb-2 w-80 rounded-xl border border-line bg-panel p-3 shadow-xl">
          <p className="text-xs font-semibold text-ink">Simulate an outage</p>
          <p className="mt-0.5 text-xs text-ink-3">
            Every tool call these agents make will fail, so you can watch the coordinator re-plan around them.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {WORKERS.map((id) => {
              const on = failures.includes(id);
              return (
                <button
                  type="button"
                  key={id}
                  aria-pressed={on}
                  onClick={() => setFailures((f) => (on ? f.filter((x) => x !== id) : [...f, id]))}
                  className={`rounded-full border px-2.5 py-0.5 text-xs ${on ? "border-ink bg-ink text-canvas" : "border-line text-ink-2 hover:text-ink"}`}
                >
                  {participant(id).label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {error && <p className="mt-2 px-1 text-sm text-bad" role="alert">{error}</p>}
      {busy && <p className="mt-2 px-1 text-xs text-ink-3">The team is still working on your last question.</p>}
    </form>
  );
}
