import { AlertTriangle, BadgeCheck, Check, Copy, Download, Network, RotateCcw } from "lucide-react";
import { useState } from "react";

import { api } from "../lib/api";
import { domainOf } from "../lib/format";
import type { RunView } from "../lib/runState";
import { useRunView } from "../lib/runStore";
import { AnswerBody, citationOrder } from "./AnswerBody";
import { Steps } from "./Steps";

function ReviewBadge({ view }: { view: RunView }) {
  const result = view.result;
  if (!result) return null;
  if (result.review_status === "approved") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-ink-3">
        <BadgeCheck className="size-3.5" aria-hidden /> Fact-checked by the Critic · {result.final_score}/10
      </span>
    );
  }
  if (result.review_status === "accepted_with_issues") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-warn">
        <AlertTriangle className="size-3.5" aria-hidden /> Critic still had concerns · {result.final_score}/10
      </span>
    );
  }
  if (result.review_status === "unreviewed") {
    return <span className="text-xs text-ink-3">Not fact-checked (the team ran out of time)</span>;
  }
  return null;
}

function asMarkdown(view: RunView): string {
  const draft = view.drafts.at(-1);
  if (!draft) return "";
  const byId = Object.fromEntries(view.evidence.map((e) => [e.id, e]));
  const order = citationOrder(draft.markdown).filter((id) => byId[id]);
  const body = draft.markdown.replace(/\[(E\d+)\]/g, (m, id) => (order.includes(id) ? `[${order.indexOf(id) + 1}]` : m));
  const sources = order.map((id, i) => `${i + 1}. [${byId[id].title}](${byId[id].url}) (${domainOf(byId[id].url)})`);
  return `## ${draft.title}\n\n${body}${sources.length ? `\n\nSources:\n${sources.join("\n")}` : ""}\n`;
}

function ActionButton({ onClick, href, icon: Icon, label }: {
  onClick?: () => void; href?: string; icon: typeof Copy; label: string;
}) {
  const className = "inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-ink-3 transition hover:bg-sunken hover:text-ink";
  return href ? (
    <a href={href} download className={className}><Icon className="size-3.5" aria-hidden />{label}</a>
  ) : (
    <button onClick={onClick} className={className}><Icon className="size-3.5" aria-hidden />{label}</button>
  );
}

export function Answer({
  runId,
  onShowActivity,
  onRetry,
}: {
  runId: string;
  onShowActivity: (runId: string) => void;
  onRetry: () => void;
}) {
  const view = useRunView(runId);
  const [copied, setCopied] = useState(false);
  const draft = view.drafts.at(-1);
  const live = view.status === "running" || view.status === "connecting";

  async function copy() {
    await navigator.clipboard.writeText(asMarkdown(view));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="flex">
      <div className="min-w-0 flex-1 space-y-4">
        <Steps view={view} />

        {view.status === "rejected" && view.result && (
          <p className="text-[15px] leading-relaxed text-ink">{view.result.message}</p>
        )}

        {view.status === "failed" && !draft && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-bad/30 bg-bad/5 px-4 py-3 text-sm">
            <span className="text-ink-2">Something went wrong: {view.error ?? "the run failed"}.</span>
            <button onClick={onRetry} className="inline-flex items-center gap-1 font-medium text-ink underline underline-offset-4">
              <RotateCcw className="size-3.5" aria-hidden /> Try again
            </button>
          </div>
        )}

        {view.status === "completed" && !draft && view.result?.message && (
          <p className="text-[15px] leading-relaxed text-ink-2">{view.result.message}</p>
        )}

        {draft && (
          <article className={live ? "opacity-70 transition" : "transition"}>
            {live && (
              <p className="mb-2 text-xs text-ink-3 italic">
                Draft {draft.version}, being fact-checked by the Critic…
              </p>
            )}
            <h2 className="mb-2 font-serif text-[1.35rem] leading-snug text-ink">{draft.title}</h2>
            <AnswerBody markdown={draft.markdown} evidence={view.evidence} />
          </article>
        )}

        {!live && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line pt-3">
            <ReviewBadge view={view} />
            <div className="ml-auto flex flex-wrap items-center gap-0.5">
              {draft && <ActionButton onClick={copy} icon={copied ? Check : Copy} label={copied ? "Copied" : "Copy"} />}
              {draft && <ActionButton href={api.reportUrl(runId)} icon={Download} label="Markdown" />}
              <ActionButton onClick={() => onShowActivity(runId)} icon={Network} label="Agent activity" />
            </div>
          </div>
        )}
        {live && (
          <button
            onClick={() => onShowActivity(runId)}
            className="inline-flex items-center gap-1.5 text-xs text-ink-3 hover:text-ink"
          >
            <Network className="size-3.5" aria-hidden /> Watch the agents work
          </button>
        )}
      </div>
    </div>
  );
}
