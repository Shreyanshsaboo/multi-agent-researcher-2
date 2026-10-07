import { Brain, FileText, Globe, type LucideIcon, Newspaper, PenLine, ShieldCheck, User, Workflow } from "lucide-react";

import type { Evidence, Participant } from "../types";

interface ParticipantStyle {
  label: string;
  short: string;
  color: string;
  icon: LucideIcon;
}

// One hue per agent, used for graph nodes, timeline dots and evidence attributions.
export const PARTICIPANTS: Record<Participant, ParticipantStyle> = {
  user: { label: "You", short: "You", color: "#64748b", icon: User },
  orchestrator: { label: "Orchestrator", short: "Orch.", color: "#64748b", icon: Workflow },
  coordinator: { label: "Coordinator", short: "Coord.", color: "#8b5cf6", icon: Brain },
  hn_scout: { label: "HN Scout", short: "HN", color: "#f97316", icon: Newspaper },
  web_researcher: { label: "Web Researcher", short: "Web", color: "#0ea5e9", icon: Globe },
  article_reader: { label: "Article Reader", short: "Reader", color: "#14b8a6", icon: FileText },
  writer: { label: "Writer", short: "Writer", color: "#22c55e", icon: PenLine },
  critic: { label: "Critic", short: "Critic", color: "#f43f5e", icon: ShieldCheck },
};

export function participant(id: string): ParticipantStyle {
  return PARTICIPANTS[id as Participant] ?? { label: id, short: id, color: "#64748b", icon: Workflow };
}

export const SOURCE_LABELS: Record<Evidence["source_type"], string> = {
  hackernews: "Hacker News",
  web: "Web",
  news: "News",
  article: "Article",
};

export const MESSAGE_KINDS: Record<string, string> = {
  query: "query",
  decision: "decision",
  task: "task",
  result: "result",
  brief: "brief",
  draft: "draft",
  verdict: "verdict",
  critique: "critique",
  final: "final",
};
