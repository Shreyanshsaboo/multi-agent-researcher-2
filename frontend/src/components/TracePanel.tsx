import { FileJson } from "lucide-react";

import { api } from "../lib/api";
import type { RunView } from "../lib/runState";

export function TracePanel({ view }: { view: RunView }) {
  const messages = view.timeline.filter((e) => e.kind === "message").length;
  const tools = view.timeline.filter((e) => e.kind === "tool").length;
  return (
    <div className="space-y-3 text-sm text-ink-2">
      <p>
        The trace is the complete, ordered record of this run as it happened: {view.lastSeq} events,
        including {messages} messages between agents and {tools} tool calls. It is what the server
        recorded live, and the same data this page is built from.
      </p>
      {view.runId && (
        <a
          href={api.traceUrl(view.runId)}
          download
          className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
        >
          <FileJson className="size-4" aria-hidden /> Download trace JSON
        </a>
      )}
      {view.options && (
        <dl className="grid max-w-md grid-cols-2 gap-y-1 text-[13px]">
          <dt className="text-ink-3">Run id</dt>
          <dd className="font-mono">{view.runId}</dd>
          <dt className="text-ink-3">Depth</dt>
          <dd>{view.options.depth}</dd>
          <dt className="text-ink-3">Simulated outages</dt>
          <dd>{view.options.simulate_failures.join(", ") || "none"}</dd>
          {view.result && (
            <>
              <dt className="text-ink-3">Failed tasks</dt>
              <dd>{view.result.stats.failed_tasks}</dd>
              <dt className="text-ink-3">Drafts</dt>
              <dd>{view.result.stats.drafts}</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}
