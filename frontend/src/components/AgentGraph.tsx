import type { CSSProperties } from "react";

import { participant } from "../lib/agents";
import { compactNumber } from "../lib/format";
import type { AgentView, Pulse } from "../lib/runState";
import type { AgentSpec, Participant } from "../types";

const W = 760;
const H = 340;
const NODE_W = 146;
const NODE_H = 58;

const POSITIONS: Record<Participant, { x: number; y: number }> = {
  user: { x: 380, y: 34 },
  coordinator: { x: 380, y: 142 },
  orchestrator: { x: 380, y: 142 },
  hn_scout: { x: 78, y: 278 },
  web_researcher: { x: 229, y: 278 },
  article_reader: { x: 380, y: 278 },
  writer: { x: 531, y: 278 },
  critic: { x: 682, y: 278 },
};

const EDGES: [Participant, Participant][] = [
  ["user", "coordinator"],
  ["coordinator", "hn_scout"],
  ["coordinator", "web_researcher"],
  ["coordinator", "article_reader"],
  ["coordinator", "writer"],
  ["writer", "critic"],
  ["critic", "coordinator"],
];

const ACTIVE = new Set(["thinking", "working", "writing", "reviewing"]);
const NODES: Participant[] = ["coordinator", "hn_scout", "web_researcher", "article_reader", "writer", "critic"];

function statusLine(view: AgentView | undefined): { text: string; tone: "active" | "wait" | "error" | "idle" } {
  if (!view) return { text: "idle", tone: "idle" };
  if (view.state === "error") return { text: "error, recovered", tone: "error" };
  if (view.state === "waiting") return { text: "rate limited, retrying", tone: "wait" };
  if (ACTIVE.has(view.state)) return { text: view.detail || view.state, tone: "active" };
  if (view.calls) return { text: `${view.calls} call${view.calls > 1 ? "s" : ""} · ${compactNumber(view.tokens)} tok`, tone: "idle" };
  return { text: "idle", tone: "idle" };
}

function UserNode() {
  const { x, y } = POSITIONS.user;
  return (
    <g>
      <rect x={x - 38} y={y - 16} width={76} height={32} rx={16} className="fill-sunken stroke-line" strokeWidth={1} />
      <text x={x} y={y + 5} textAnchor="middle" className="fill-ink-2 text-[13px] font-medium">You</text>
    </g>
  );
}

function AgentNode({ id, spec, view }: { id: Participant; spec?: AgentSpec; view?: AgentView }) {
  const { x, y } = POSITIONS[id];
  const style = participant(id);
  const Icon = style.icon;
  const status = statusLine(view);
  const ring = status.tone === "active" ? style.color : status.tone === "wait" ? "var(--warn)" : status.tone === "error" ? "var(--bad)" : null;
  const left = x - NODE_W / 2;
  const top = y - NODE_H / 2;
  const label = status.text.length > 24 ? `${status.text.slice(0, 23)}…` : status.text;
  const model = view?.model ?? spec?.model ?? "";
  const fellBack = !!spec && !!view?.model && view.model !== spec.model;

  return (
    <g>
      <title>{spec ? `${spec.name}: ${spec.role}\nModel: ${spec.model}${spec.tools.length ? `\nTools: ${spec.tools.join(", ")}` : ""}` : style.label}</title>
      {ring && (
        <rect
          x={left - 4} y={top - 4} width={NODE_W + 8} height={NODE_H + 8} rx={15}
          fill="none" stroke={ring} strokeWidth={2} className="node-active-ring"
        />
      )}
      <rect
        x={left} y={top} width={NODE_W} height={NODE_H} rx={12}
        className="fill-panel" stroke={ring ?? "var(--line)"} strokeWidth={ring ? 1.5 : 1}
      />
      <circle cx={left + 21} cy={y} r={13} fill={style.color} fillOpacity={0.15} />
      <Icon x={left + 12} y={y - 9} width={18} height={18} color={style.color} strokeWidth={2} />
      <text x={left + 40} y={y - 3} className="fill-ink text-[12.5px] font-semibold">{style.label}</text>
      <text x={left + 40} y={y + 14} className={`font-mono text-[11px] ${fellBack ? "fill-warn" : "fill-ink-3"}`}>
        {fellBack ? "↺ " : ""}
        {model.replace(/^.*\//, "")}
      </text>
      <text
        x={x} y={top + NODE_H + 17} textAnchor="middle"
        className={`text-[12px] ${status.tone === "wait" ? "fill-warn" : status.tone === "error" ? "fill-bad" : status.tone === "active" ? "fill-ink-2" : "fill-ink-3"}`}
      >
        {label}
      </text>
    </g>
  );
}

function PulseDot({ pulse }: { pulse: Pulse }) {
  const from = POSITIONS[pulse.from];
  const to = POSITIONS[pulse.to];
  if (!from || !to) return null;
  const color = participant(pulse.from).color;
  const vars = { "--x1": `${from.x}px`, "--y1": `${from.y}px`, "--x2": `${to.x}px`, "--y2": `${to.y}px` } as CSSProperties;
  return (
    <g>
      <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={color} strokeWidth={2.5} className="pulse-edge" />
      <circle r={5.5} fill={color} className="pulse-dot" style={vars} />
    </g>
  );
}

export function AgentGraph({
  specs,
  agents,
  pulses,
}: {
  specs: AgentSpec[];
  agents: Record<string, AgentView>;
  pulses: Pulse[];
}) {
  const specById = Object.fromEntries(specs.map((s) => [s.id, s]));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Agent communication graph">
      <style>{`
        @keyframes travel { from { transform: translate(var(--x1), var(--y1)); } to { transform: translate(var(--x2), var(--y2)); } }
        @keyframes fade { 0% { opacity: 0.9; } 100% { opacity: 0; } }
        .pulse-dot { animation: travel 0.9s ease-in-out forwards, fade 0.5s ease-in 0.9s forwards; }
        .pulse-edge { animation: fade 1.6s ease-out forwards; }
        @media (prefers-reduced-motion: reduce) { .pulse-dot { animation: fade 0.6s forwards; } }
      `}</style>
      {EDGES.map(([a, b]) => (
        <line
          key={`${a}-${b}`}
          x1={POSITIONS[a].x} y1={POSITIONS[a].y} x2={POSITIONS[b].x} y2={POSITIONS[b].y}
          stroke="var(--line)" strokeWidth={1.5}
          strokeDasharray={a === "critic" ? "4 4" : undefined}
        />
      ))}
      {pulses.map((p) => (
        <PulseDot key={p.id} pulse={p} />
      ))}
      <UserNode />
      {NODES.map((id) => (
        <AgentNode key={id} id={id} spec={specById[id]} view={agents[id]} />
      ))}
    </svg>
  );
}
