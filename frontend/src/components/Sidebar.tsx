import { Plus, X } from "lucide-react";

import { timeAgo } from "../lib/format";
import type { ThreadSummary } from "../types";

export function Sidebar({
  threads,
  activeThread,
  open,
  onClose,
  onNew,
  onOpen,
  onAbout,
}: {
  threads: ThreadSummary[];
  activeThread: string | null;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onOpen: (threadId: string) => void;
  onAbout: () => void;
}) {
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/30 md:hidden" onClick={onClose} aria-hidden />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-line bg-sunken transition-transform md:static md:z-auto md:w-64 md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}
        aria-label="Conversations"
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-3">
          <a href="/" className="font-serif text-[17px] tracking-tight text-ink">Multi-Agent Researcher</a>
          <button onClick={onClose} className="text-ink-3 hover:text-ink md:hidden" aria-label="Close menu">
            <X className="size-4" />
          </button>
        </div>

        <div className="px-3">
          <button
            onClick={onNew}
            className="flex w-full items-center gap-2 rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink transition hover:border-ink-3"
          >
            <Plus className="size-4 text-ink-3" aria-hidden /> New question
          </button>
        </div>

        <nav className="mt-5 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          <p className="px-2 pb-1.5 text-[11px] font-medium tracking-wide text-ink-3 uppercase">History</p>
          {threads.length === 0 ? (
            <p className="px-2 text-sm text-ink-3">Your questions will appear here.</p>
          ) : (
            <ul className="space-y-px">
              {threads.map((t) => (
                <li key={t.thread_id}>
                  <button
                    onClick={() => onOpen(t.thread_id)}
                    aria-current={t.thread_id === activeThread ? "page" : undefined}
                    className={`w-full rounded-lg px-2 py-1.5 text-left transition ${t.thread_id === activeThread ? "bg-panel text-ink" : "text-ink-2 hover:bg-panel/60 hover:text-ink"}`}
                  >
                    <span className="block truncate text-[13.5px]">{t.title}</span>
                    <span className="block text-[11px] text-ink-3">
                      {t.status === "running" ? "In progress" : timeAgo(t.updated_at)}
                      {t.turns > 1 && ` · ${t.turns} questions`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>

        <div className="border-t border-line px-4 py-3">
          <button onClick={onAbout} className="text-[13px] text-ink-2 underline-offset-4 hover:text-ink hover:underline">
            How it works
          </button>
        </div>
      </aside>
    </>
  );
}
