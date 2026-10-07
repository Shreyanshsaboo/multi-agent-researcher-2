import type { AgentSpec, Budget, Depth, RunOptions, RunSummary, ThreadRun, ThreadSummary } from "../types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // keep the generic message
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  agents: () => request<{ agents: AgentSpec[]; budgets: Record<Depth, Budget> }>("/api/agents"),
  health: () => request<{ status: string; provider: string; llm_configured: boolean; active_runs: number }>("/api/health"),
  runs: (limit = 20) => request<{ runs: RunSummary[] }>(`/api/runs?limit=${limit}`),
  threads: (limit = 40) => request<{ threads: ThreadSummary[] }>(`/api/threads?limit=${limit}`),
  thread: (threadId: string) => request<{ thread_id: string; runs: ThreadRun[] }>(`/api/threads/${threadId}`),
  run: (runId: string) => request<{ id: string; thread_id: string }>(`/api/runs/${runId}`),
  startRun: (query: string, options: RunOptions, threadId: string | null) =>
    request<{ run_id: string; thread_id: string }>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ query, options, thread_id: threadId }),
    }),
  eventsUrl: (runId: string) => `/api/runs/${runId}/events`,
  traceUrl: (runId: string) => `/api/runs/${runId}/trace`,
  reportUrl: (runId: string) => `/api/runs/${runId}/report.md`,
};
