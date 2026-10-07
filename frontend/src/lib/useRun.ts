import { useCallback, useEffect, useReducer, useRef } from "react";

import type { RunEvent, RunOptions } from "../types";
import { api } from "./api";
import { applyEvent, initialRun, type RunView } from "./runState";

type Action =
  | { type: "open"; runId: string }
  | { type: "events"; events: RunEvent[] }
  | { type: "stream_closed"; runId: string; error: string };

function reducer(view: RunView, action: Action): RunView {
  switch (action.type) {
    case "open":
      return initialRun(action.runId);
    case "events":
      return action.events.reduce(applyEvent, view);
    case "stream_closed":
      // A stream that ends while the run still looks live never got its final event.
      if (action.runId !== view.runId) return view;
      return view.status === "running" || view.status === "connecting"
        ? { ...view, status: "failed", error: action.error }
        : view;
  }
}

function setRunInUrl(runId: string | null) {
  const url = new URL(window.location.href);
  if (runId) url.searchParams.set("run", runId);
  else url.searchParams.delete("run");
  window.history.replaceState(null, "", url);
}

/** Owns the event stream for one run: replays history, then follows it live. */
export function useRun() {
  const [view, dispatch] = useReducer(reducer, null, () => initialRun());
  const source = useRef<EventSource | null>(null);
  const buffer = useRef<RunEvent[]>([]);
  const frame = useRef<number | null>(null);

  const close = useCallback(() => {
    source.current?.close();
    source.current = null;
  }, []);

  const open = useCallback(
    (runId: string) => {
      close();
      buffer.current = [];
      dispatch({ type: "open", runId });
      setRunInUrl(runId);

      const es = new EventSource(api.eventsUrl(runId));
      source.current = es;
      // A finished run replays hundreds of events at once; apply them once per frame.
      es.onmessage = (message) => {
        buffer.current.push(JSON.parse(message.data) as RunEvent);
        if (frame.current === null) {
          frame.current = requestAnimationFrame(() => {
            frame.current = null;
            const events = buffer.current;
            buffer.current = [];
            dispatch({ type: "events", events });
          });
        }
      };
      es.addEventListener("end", () => {
        if (source.current !== es) return;
        close();
        // Queued after any pending flush, so it sees the final events first.
        requestAnimationFrame(() =>
          dispatch({
            type: "stream_closed",
            runId,
            error: "The run stopped without a result (the server may have restarted).",
          }),
        );
      });
      // EventSource retries on its own and resumes via Last-Event-ID. Only a
      // closed stream (e.g. the run does not exist) is treated as lost.
      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED && source.current === es) {
          dispatch({ type: "stream_closed", runId, error: "Lost the connection to the server." });
        }
      };
    },
    [close],
  );

  const start = useCallback(
    async (query: string, options: RunOptions) => {
      const { run_id } = await api.startRun(query, options);
      open(run_id);
      return run_id;
    },
    [open],
  );

  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("run");
    if (runId) open(runId);
    return close;
  }, [open, close]);

  return { view, open, start };
}
