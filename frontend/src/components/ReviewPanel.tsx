import { participant } from "../lib/agents";
import type { Draft, Review } from "../types";

function Verdict({ review }: { review: Review }) {
  if (!review.critique) return <span className="text-ink-3">not reviewed: {review.error}</span>;
  const { verdict, score } = review.critique;
  return (
    <span className={verdict === "approve" ? "font-medium text-good" : "font-medium text-warn"}>
      {verdict === "approve" ? "Approved" : "Revise"} · {score}/10
    </span>
  );
}

export function ReviewPanel({ drafts, reviews }: { drafts: Draft[]; reviews: Review[] }) {
  if (drafts.length === 0) {
    return <p className="py-12 text-center text-sm text-ink-3">Each draft and the Critic's review of it appear here.</p>;
  }
  return (
    <ol className="space-y-4">
      {drafts.map((draft) => {
        const review = reviews.find((r) => r.draft_version === draft.version);
        // The writer answers a review in its *next* draft.
        const answers = drafts.find((d) => d.version === draft.version + 1)?.responses ?? [];
        const c = review?.critique;
        return (
          <li key={draft.version} className="rounded-lg border border-line bg-panel p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold text-ink">
                Draft v{draft.version}
                <span className="font-normal text-ink-3"> · {draft.title}</span>
              </h3>
              {review ? <Verdict review={review} /> : <span className="text-xs text-ink-3">awaiting review</span>}
            </div>

            {review && (
              <p className="mt-1 text-xs text-ink-3">
                Automated check: cites {review.checks.cited_ids.length} of {review.checks.evidence_total} sources
                {review.checks.unknown_ids.length > 0 && `, unknown ids ${review.checks.unknown_ids.join(", ")}`}
                {review.checks.uncited_paragraphs.length > 0 && `, ${review.checks.uncited_paragraphs.length} uncited paragraph(s)`}
              </p>
            )}
            {c && <p className="mt-2 text-sm text-ink-2">{c.summary}</p>}

            {c && c.issues.length > 0 && (
              <ul className="mt-3 space-y-2">
                {c.issues.map((issue) => {
                  const answer = answers.find((a) => a.issue_id === issue.id);
                  const ruling = reviews
                    .find((r) => r.draft_version === draft.version + 1)
                    ?.critique?.rulings.find((r) => r.issue_id === issue.id);
                  return (
                    <li key={issue.id} className="rounded-md bg-sunken p-2.5 text-[13px]">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono text-[11px] text-ink-3">{issue.id}</span>
                        <span className={`rounded px-1.5 py-px text-[10.5px] font-medium ${issue.severity === "major" ? "bg-bad/10 text-bad" : "bg-panel text-ink-2"}`}>
                          {issue.severity}
                        </span>
                        <span className="text-[11px] text-ink-3">{issue.kind.replace(/_/g, " ")}</span>
                      </div>
                      <p className="mt-1 text-ink">{issue.detail}</p>
                      {issue.suggestion && <p className="mt-0.5 text-ink-3">Suggestion: {issue.suggestion}</p>}
                      {answer && (
                        <p className="mt-1.5 text-ink-2">
                          <span className="font-medium text-ink">
                            Writer {answer.action}:
                          </span>{" "}
                          {answer.note}
                        </p>
                      )}
                      {ruling && (
                        <p className="mt-1 text-ink-2">
                          <span className="font-medium text-ink">
                            Critic {ruling.accepted ? "accepted the dispute" : "rejected the dispute"}:
                          </span>{" "}
                          {ruling.note}
                        </p>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}

            {c && c.research_requests.length > 0 && (
              <div className="mt-3 text-[13px] text-ink-2">
                <span className="font-medium text-ink">Research gaps sent to the coordinator:</span>
                <ul className="mt-1 list-disc pl-5">
                  {c.research_requests.map((r, i) => (
                    <li key={i}>
                      {participant(r.agent).label}: {r.instruction}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
