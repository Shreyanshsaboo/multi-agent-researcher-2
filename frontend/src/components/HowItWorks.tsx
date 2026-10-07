import { X } from "lucide-react";
import { useEffect } from "react";

import type { AgentSpec } from "../types";
import { AgentGraph } from "./AgentGraph";

export function HowItWorks({ specs, onClose }: { specs: AgentSpec[]; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:p-10" role="dialog" aria-modal="true" aria-labelledby="how-title">
      <div className="fixed inset-0 bg-black/30" onClick={onClose} aria-hidden />
      <div className="relative w-full max-w-3xl rounded-2xl border border-line bg-canvas p-6 shadow-2xl sm:p-8">
        <button onClick={onClose} className="absolute top-5 right-5 text-ink-3 hover:text-ink" aria-label="Close">
          <X className="size-5" />
        </button>
        <h2 id="how-title" className="font-serif text-2xl text-ink">How it works</h2>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
          Every question is handled by a team of six AI agents rather than one. The coordinator plans the
          research and decides who works next; three researchers search Hacker News and the web and read
          the most important sources; the writer drafts a cited answer; and the critic checks every claim
          against the sources and sends the draft back until it holds up.
        </p>
        <div className="mt-6">
          <AgentGraph specs={specs} agents={{}} pulses={[]} />
        </div>
        <dl className="mt-6 divide-y divide-line border-y border-line">
          {specs.map((spec) => (
            <div key={spec.id} className="grid gap-1 py-3 sm:grid-cols-[10rem_1fr] sm:gap-4">
              <dt>
                <span className="block text-sm font-medium text-ink">{spec.name}</span>
                <span className="block font-mono text-[11px] text-ink-3">{spec.model.replace(/^.*\//, "")}</span>
              </dt>
              <dd className="text-sm leading-relaxed text-ink-2">
                {spec.role}
                {spec.tools.length > 0 && (
                  <span className="mt-1 block font-mono text-[11px] text-ink-3">{spec.tools.join(" · ")}</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
