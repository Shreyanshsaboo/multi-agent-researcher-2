import { CheckCircle2, Circle, CircleDashed, CircleSlash } from "lucide-react";

import type { PlanItem } from "../types";

const STATUS = {
  open: { icon: Circle, className: "text-ink-3", label: "open" },
  in_progress: { icon: CircleDashed, className: "text-accent", label: "in progress" },
  answered: { icon: CheckCircle2, className: "text-good", label: "answered" },
  dropped: { icon: CircleSlash, className: "text-ink-3", label: "dropped" },
} as const;

export function PlanPanel({ plan, turn, replanned }: { plan: PlanItem[]; turn: number; replanned: boolean }) {
  return (
    <section aria-labelledby="plan-heading">
      <div className="mb-2 flex items-center gap-2">
        <h2 id="plan-heading" className="text-xs font-semibold tracking-wide text-ink-2 uppercase">
          Research plan
        </h2>
        {turn > 0 && <span className="text-xs text-ink-3">turn {turn}</span>}
        {replanned && (
          <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">
            re-planned
          </span>
        )}
      </div>
      {plan.length === 0 ? (
        <p className="text-sm text-ink-3">The coordinator writes the plan on its first turn.</p>
      ) : (
        <ol className="space-y-1.5">
          {plan.map((item) => {
            const status = STATUS[item.status] ?? STATUS.open;
            const Icon = status.icon;
            return (
              <li key={item.id} className="flex gap-2 text-sm" title={status.label}>
                <Icon className={`mt-0.5 size-4 shrink-0 ${status.className}`} aria-label={status.label} />
                <span className={item.status === "dropped" ? "text-ink-3 line-through" : "text-ink"}>
                  {item.question}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
