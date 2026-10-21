import { useSyncExternalStore } from "react";

import type { RunEvent } from "../types";
import { api } from "./api";
import { applyEvent, initialRun, settleAgents, type RunView } from "./runState";

/**
 * One event stream per run, shared by every component showing that run.
 * A finished run replays its trace once and stays cached for the session.
 */
interface Entry {
  view: RunView;
  source: EventSource | null;
  buffer: RunEvent[];
  frame: number | null;
  listeners: Set<() => void>;
}

const entries = new Map<string, Entry>();

function notify(entry: Entry) {
  entry.listeners.forEach((listener) => listener());
}

function markClosed(entry: Entry, error: string) {
  if (entry.view.status === "running" || entry.view.status === "connecting") {
    entry.view = { ...entry.view, status: "failed", agents: settleAgents(entry.view.agents), error };
    notify(entry);
  }
}

function open(runId: string): Entry {
  const entry: Entry = { view: initialRun(runId), source: null, buffer: [], frame: null, listeners: new Set() };
  entries.set(runId, entry);

  const es = new EventSource(api.eventsUrl(runId));
  entry.source = es;
  // A finished run replays hundreds of events at once; apply them once per frame.
  es.onmessage = (message) => {
    entry.buffer.push(JSON.parse(message.data) as RunEvent);
    if (entry.frame === null) {
      entry.frame = requestAnimationFrame(() => {
        entry.frame = null;
        const events = entry.buffer;
        entry.buffer = [];
        entry.view = events.reduce(applyEvent, entry.view);
        notify(entry);
      });
    }
  };
  es.addEventListener("end", () => {
    es.close();
    entry.source = null;
    // Queued after any pending flush, so the final events are applied first.
    requestAnimationFrame(() =>
      markClosed(entry, "The run stopped without a result (the server may have restarted)."),
    );
  });
  // EventSource retries by itself and resumes via Last-Event-ID; only a closed
  // stream (e.g. an unknown run) is final.
  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) {
      entry.source = null;
      markClosed(entry, "Lost the connection to the server.");
    }
  };
  return entry;
}

function entryFor(runId: string): Entry {
  return entries.get(runId) ?? open(runId);
}

const IDLE = initialRun();

export function useRunView(runId: string | null): RunView {
  return useSyncExternalStore(
    (listener) => {
      if (!runId) return () => {};
      const entry = entryFor(runId);
      entry.listeners.add(listener);
      return () => entry.listeners.delete(listener);
    },
    () => (runId ? entryFor(runId).view : IDLE),
  );
}
