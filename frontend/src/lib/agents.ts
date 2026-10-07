import { Brain, FileText, Globe, type LucideIcon, Newspaper, PenLine, ShieldCheck, User, Workflow } from "lucide-react";

import type { Evidence, Participant } from "../types";

interface ParticipantStyle {
  label: string;
  short: string;
  color: string;
  icon: LucideIcon;
}

// Agents are told apart by name and icon, not colour; every agent shares the neutral ink.
export const PARTICIPANTS: Record<Participant, ParticipantStyle> = {
  user: { label: "You", short: "You", color: "var(--ink-2)", icon: User },
  orchestrator: { label: "Orchestrator", short: "Orch.", color: "var(--ink-2)", icon: Workflow },
  coordinator: { label: "Coordinator", short: "Coord.", color: "var(--ink-2)", icon: Brain },
  hn_scout: { label: "HN Scout", short: "HN", color: "var(--ink-2)", icon: Newspaper },
  web_researcher: { label: "Web Researcher", short: "Web", color: "var(--ink-2)", icon: Globe },
  article_reader: { label: "Article Reader", short: "Reader", color: "var(--ink-2)", icon: FileText },
  writer: { label: "Writer", short: "Writer", color: "var(--ink-2)", icon: PenLine },
  critic: { label: "Critic", short: "Critic", color: "var(--ink-2)", icon: ShieldCheck },
};

export function participant(id: string): ParticipantStyle {
  return PARTICIPANTS[id as Participant] ?? { label: id, short: id, color: "var(--ink-2)", icon: Workflow };
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
