# Synopsis

**Multi-Agent Researcher**: six cooperating LLM agents that research a question and return a cited,
peer-reviewed report.

Shreyansh Saboo · [github.com/Shreyanshsaboo/multi-agent-researcher-2](https://github.com/Shreyanshsaboo/multi-agent-researcher-2)

## Problem

Answering a current technical question well means searching more than one kind of source, reading
the few that matter, keeping facts apart from opinions, and writing it up with citations a reader can
check. A single LLM given every tool at once tends to skip steps, lose track of where a claim came
from, and state figures it never retrieved.

## Who it is for

Developers, engineering leads and computer science students who need a sourced overview of a
current technical topic: what is happening, and what practitioners think of it. Typical uses are
weighing up a tool before adopting it, preparing for a design discussion, or catching up on a debate
such as Rust in the Linux kernel. They want an answer in a few minutes, with every claim linked to a
source they can open, instead of an hour across Hacker News threads, search results and articles, or
a chatbot answer they cannot check.

## Approach

The work is split among six agents with narrow roles, coordinated at run time rather than by a fixed
pipeline:

- The **Coordinator** turns the question into sub-questions and, on every turn, decides what happens
  next: which researchers to send, what to read, when to draft, and when the report is good enough.
- Three researchers work in parallel with their own tools. The **HN Scout** reads Hacker News
  discussions for practitioner opinion, the **Web Researcher** searches the web and news for facts,
  and the **Article Reader** reads the full text of the sources that matter most.
- The **Writer** drafts the report from the shared evidence, citing a source for every claim.
- The **Critic**, on a different model family from the writer, checks each draft against the
  evidence. The writer fixes or disputes each issue, and the coordinator settles disagreements.

Findings reach the shared evidence store only if their source was really retrieved and their figures
appear in the retrieved text. Budgets bound every run, and failures of tools, agents or model quotas
are routed around, so a run always ends with a result.

## Changes since the CA2 proposal

The proposal had four agents, built as the v1 prototype that is kept in [`prototype/`](../prototype/):
a team lead, delegating through Agno's `Team`, and three researchers for Hacker News, web search and
articles. The team lead also wrote the report. The problem, the target user and the sources stay the
same. Three things changed, each because of what the prototype showed:

- **Six agents instead of four.** The team lead planned and wrote, and nothing checked its report, so
  unsupported claims and figures no source contained reached the user. Planning and writing are now
  separate agents (the Coordinator and the Writer), and a new Critic on a different model family
  reviews every draft before the user sees it.
- **Our own orchestration loop instead of Agno's `Team`.** `Team` delegation could not be budgeted,
  validated or traced step by step. The Coordinator now returns one structured decision per turn,
  which the orchestrator checks and executes, and every step is recorded in the run's trace.
- **A web app instead of Streamlit.** The React interface shows every agent, message and tool call
  live, keeps conversations for follow-up questions, and saves each run as a replayable trace.

## Input and output

- **Input**: a question, a depth (`quick`, `standard` or `deep`, which sets the budget), and
  optionally the conversation it follows up and simulated outages for a demonstration.
- **Output**: a Markdown report with numbered citations, its sources, the critic's verdict and score,
  the research plan, run statistics, and the complete event trace of the run.

Both are specified in [io-spec.md](io-spec.md).

## Outcome

The system runs end to end as a web app (live view of every agent, message and tool call), a CLI and
an API, packaged as one Docker container. Three real runs are captured in [samples/](samples/),
each with its full trace. On "How are teams cutting LLM inference costs in 2026?", the critic
rejected the first draft (5/10) for claims the evidence did not support and named two gaps; the
coordinator sent the web researcher after them, and the critic approved the revised draft (8/10).
On "What do developers think about Rust in the Linux kernel?", all six agents acted, including the
article reader reading two sources in full. In a third run, every web search failed on purpose, and
the coordinator switched to the other researchers and to sources recalled from earlier runs; the run
still ended with a cited, reviewed report. Each run took two to three and a half minutes on the free
tier.

## Technology

Python 3.12 with [Agno](https://github.com/agno-agi/agno) for the agents; Groq-hosted `gpt-oss-120b`,
`gpt-oss-20b` and `qwen3.8-27b` (or local models through Ollama); FastAPI with server-sent events;
SQLite; React 19 with Vite and Tailwind; Docker. The design and the reasons behind each choice are in
[design.md](design.md).

## Limitations and next steps

- On Groq's free tier a run takes two to three and a half minutes, mostly waiting for per-minute
  token quotas.
  A paid tier would bring it to well under a minute.
- Keyless web search often returns stale results for "latest news" questions; a search API would
  improve the researchers' raw material.
- Next steps: cache article reads across runs, recall past research by meaning rather than keywords,
  and add an evaluation set of questions with reference answers to measure report quality over time.
