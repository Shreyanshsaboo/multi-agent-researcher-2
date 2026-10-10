# Synopsis

**Multi-Agent Researcher**: six cooperating LLM agents that research a question and return a cited,
peer-reviewed report.

Shreyansh Saboo · [github.com/Shreyanshsaboo/multi-agent-researcher-2](https://github.com/Shreyanshsaboo/multi-agent-researcher-2)

## Problem

Answering a current technical question well means searching more than one kind of source, reading
the few that matter, keeping facts apart from opinions, and writing it up with citations a reader can
check. A single LLM given every tool at once tends to skip steps, lose track of where a claim came
from, and state figures it never retrieved.

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

## Input and output

- **Input**: a question, a depth (`quick`, `standard` or `deep`, which sets the budget), and
  optionally the conversation it follows up and simulated outages for a demonstration.
- **Output**: a Markdown report with numbered citations, its sources, the critic's verdict and score,
  the research plan, run statistics, and the complete event trace of the run.

Both are specified in [io-spec.md](io-spec.md).

## Outcome

The system runs end to end as a web app (live view of every agent, message and tool call), a CLI and
an API, packaged as one Docker container. The [sample run](samples/) shows a complete cycle on the
question "How are teams cutting LLM inference costs in 2026?".
In 132 seconds on the free tier, over five coordinator turns, the team ran five research tasks and
collected ten sources. The critic rejected the first draft (5/10) for claims the evidence did not
support and named two gaps; the coordinator sent the web researcher after them, the orchestrator
dropped a task that repeated an earlier one, and the critic approved the revised draft (8/10), which
cites nine of the ten sources.

## Technology

Python 3.12 with [Agno](https://github.com/agno-agi/agno) for the agents; Groq-hosted `gpt-oss-120b`,
`gpt-oss-20b` and `qwen3.8-27b` (or local models through Ollama); FastAPI with server-sent events;
SQLite; React 19 with Vite and Tailwind; Docker. The design and the reasons behind each choice are in
[design.md](design.md).

## Limitations and next steps

- On Groq's free tier a run takes one to three minutes, mostly waiting for per-minute token quotas.
  A paid tier would bring it to well under a minute.
- Keyless web search often returns stale results for "latest news" questions; a search API would
  improve the researchers' raw material.
- Next steps: cache article reads across runs, recall past research by meaning rather than keywords,
  and add an evaluation set of questions with reference answers to measure report quality over time.
