import { Menu } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ActivityDrawer } from "./components/ActivityDrawer";
import { Answer } from "./components/Answer";
import { Composer } from "./components/Composer";
import { HowItWorks } from "./components/HowItWorks";
import { Sidebar } from "./components/Sidebar";
import { api } from "./lib/api";
import { useRunView } from "./lib/runStore";
import type { AgentSpec, RunOptions, ThreadSummary } from "./types";

interface Turn {
  runId: string;
  query: string;
}

const EXAMPLES = [
  "How are teams cutting LLM inference costs in 2026?",
  "What do developers think about Rust in the Linux kernel?",
  "Is SQLite a good choice for production web apps?",
  "What changed in the EU AI Act rules for general-purpose models?",
];

function setThreadInUrl(threadId: string | null) {
  const url = new URL(window.location.href);
  url.searchParams.delete("run");
  if (threadId) url.searchParams.set("c", threadId);
  else url.searchParams.delete("c");
  window.history.replaceState(null, "", url);
}

export default function App() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [specs, setSpecs] = useState<AgentSpec[]>([]);
  const [configured, setConfigured] = useState(true);
  const [activityRun, setActivityRun] = useState<string | null>(null);
  const [showAbout, setShowAbout] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [prefill, setPrefill] = useState<{ text: string; key: number }>();
  const fill = (text: string) => setPrefill({ text, key: Date.now() });
  const latest = useRef<HTMLElement>(null);

  const lastRun = turns.at(-1)?.runId ?? null;
  const lastView = useRunView(lastRun);
  const busy = lastView.status === "running" || lastView.status === "connecting";

  const refreshThreads = useCallback(() => {
    api.threads().then((r) => setThreads(r.threads)).catch(() => undefined);
  }, []);

  const openThread = useCallback(async (id: string) => {
    setMenuOpen(false);
    try {
      const thread = await api.thread(id);
      setThreadId(thread.thread_id);
      setTurns(thread.runs.map((r) => ({ runId: r.id, query: r.query })));
      setThreadInUrl(thread.thread_id);
    } catch {
      setThreadInUrl(null);
    }
  }, []);

  useEffect(() => {
    refreshThreads();
    api.agents().then((r) => setSpecs(r.agents)).catch(() => undefined);
    api.health().then((h) => setConfigured(h.llm_configured)).catch(() => undefined);
    const params = new URLSearchParams(window.location.search);
    const thread = params.get("c");
    const run = params.get("run");
    if (thread) void openThread(thread);
    else if (run) api.run(run).then((r) => openThread(r.thread_id)).catch(() => undefined);
  }, [refreshThreads, openThread]);

  // Refresh the history once an answer is finished.
  useEffect(() => {
    if (lastRun && !busy) refreshThreads();
  }, [lastRun, busy, refreshThreads]);

  // Bring the newest question to the top of the view; its answer streams in below it.
  // Earlier answers replay asynchronously, so look again once they have rendered.
  useEffect(() => {
    if (turns.length === 0) return;
    const scroll = () => latest.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    scroll();
    const again = setTimeout(scroll, 600);
    return () => clearTimeout(again);
  }, [turns.length]);

  function newQuestion() {
    setThreadId(null);
    setTurns([]);
    setMenuOpen(false);
    setThreadInUrl(null);
  }

  async function ask(query: string, options: RunOptions) {
    const { run_id, thread_id } = await api.startRun(query, options, threadId);
    setThreadId(thread_id);
    setTurns((t) => [...t, { runId: run_id, query }]);
    setThreadInUrl(thread_id);
    refreshThreads();
  }

  return (
    <div className="flex h-dvh bg-canvas text-ink">
      <Sidebar
        threads={threads}
        activeThread={threadId}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        onNew={newQuestion}
        onOpen={(id) => void openThread(id)}
        onAbout={() => setShowAbout(true)}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-line px-4 py-3 md:hidden">
          <button onClick={() => setMenuOpen(true)} aria-label="Open menu" className="text-ink-2">
            <Menu className="size-5" />
          </button>
          <span className="font-serif text-[16px]">Multi-Agent Researcher</span>
        </div>

        {!configured && (
          <p className="border-b border-line bg-sunken px-4 py-2 text-center text-[13px] text-ink-2" role="alert">
            The server has no model API key configured, so new questions cannot be answered.
          </p>
        )}

        {turns.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10">
            <div className="w-full max-w-2xl">
              <h1 className="text-center font-serif text-3xl tracking-tight text-ink sm:text-[2.1rem]">
                What would you like to research?
              </h1>
              <p className="mx-auto mt-3 max-w-lg text-center text-[15px] leading-relaxed text-ink-3">
                A team of six agents searches Hacker News and the web, reads the sources, writes an
                answer and fact-checks it before you see it.
              </p>
              <div className="mt-8">
                <Composer busy={false} followUp={false} autoFocus draft={prefill} onSubmit={ask} />
              </div>
              <ul className="mt-6 space-y-1">
                {EXAMPLES.map((example) => (
                  <li key={example}>
                    <button
                      onClick={() => fill(example)}
                      className="w-full rounded-lg px-3 py-2 text-left text-sm text-ink-2 transition hover:bg-sunken hover:text-ink"
                    >
                      {example}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto">
              <div className="mx-auto max-w-3xl space-y-10 px-4 pt-8 pb-10">
                {turns.map((turn, i) => (
                  <section
                    key={turn.runId}
                    ref={i === turns.length - 1 ? latest : undefined}
                    className="scroll-mt-6 space-y-5"
                  >
                    <div className="flex justify-end">
                      <p className="max-w-[85%] rounded-2xl bg-sunken px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-ink">
                        {turn.query}
                      </p>
                    </div>
                    <Answer
                      runId={turn.runId}
                      onShowActivity={setActivityRun}
                      onRetry={() => fill(turn.query)}
                    />
                  </section>
                ))}
              </div>
            </div>
            <div className="border-t border-line bg-canvas px-4 pt-3 pb-4">
              <div className="mx-auto max-w-3xl">
                <Composer busy={busy} followUp draft={prefill} onSubmit={ask} />
              </div>
            </div>
          </>
        )}
      </main>

      {activityRun && <ActivityDrawer runId={activityRun} onClose={() => setActivityRun(null)} />}
      {showAbout && <HowItWorks specs={specs} onClose={() => setShowAbout(false)} />}
    </div>
  );
}
