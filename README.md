# Multi-Agent AI Researcher

A Streamlit application that coordinates a team of specialized LLM agents to research a topic on HackerNews, read the underlying articles, enrich them with web search, and return a single cited report.

I built this to explore how far task decomposition gets you in practice. A single agent given search, extraction, and synthesis responsibilities all at once tends to drop steps or hallucinate sources. Here each capability lives in its own narrowly scoped agent with exactly one tool, and an orchestrator decides who runs, in what order, and how to merge the results.

The project ships in two variants: a hosted version backed by the OpenAI API, and a fully local version backed by Ollama.

## Contents

- [System architecture](#system-architecture)
- [Request lifecycle](#request-lifecycle)
- [Design decisions](#design-decisions)
- [Variants](#variants)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Roadmap](#roadmap)

## System architecture

The system is four layers: a thin presentation layer, a coordination layer that owns the workflow, a set of stateless worker agents, and the external services those workers reach through tools.

```
+----------------------------------------------------------------------+
| PRESENTATION                                                         |
|                                                                      |
| Streamlit UI                                                         |
| query input  ->  rendered markdown report                            |
+----------------------------------------------------------------------+
                                   |  query string
                                   v
+----------------------------------------------------------------------+
| COORDINATION                                                         |
|                                                                      |
| HackerNews Team  (Agno Team, orchestrator)                           |
|   holds the workflow instructions                                    |
|   selects the member agent for each step                             |
|   passes artifacts between steps                                     |
|   synthesizes the final report                                       |
+----------------------------------------------------------------------+
         | delegate                | delegate                | delegate
         v                         v                         v
+------------------+      +------------------+      +------------------+
| AGENT LAYER      |      |                  |      |                  |
|                  |      |                  |      |                  |
| HackerNews       |      | Article Reader   |      | Web Searcher     |
| Researcher       |      |                  |      |                  |
|                  |      | extracts full    |      | broadens         |
| finds stories    |      | text from a URL  |      | context off HN   |
+------------------+      +------------------+      +------------------+
         | tool call               | tool call               | tool call
         v                         v                         v
+------------------+      +------------------+      +------------------+
| TOOL LAYER       |      |                  |      |                  |
|                  |      |                  |      |                  |
| HackerNewsTools  |      | Newspaper4kTools |      | DuckDuckGoTools  |
+------------------+      +------------------+      +------------------+
         |                         |                         |
         v                         v                         v
+------------------+      +------------------+      +------------------+
| EXTERNAL         |      |                  |      |                  |
|                  |      |                  |      |                  |
| HackerNews API   |      | Article hosts    |      | DuckDuckGo       |
| (Firebase)       |      | (HTTP + parse)   |      | search index     |
+------------------+      +------------------+      +------------------+

Inference backend, shared by the team and every member agent:
    OpenAIChat gpt-4o-mini        or        Ollama llama3.2
```

The orchestrator is the only component that knows the full task. Member agents receive a delegated subtask and have no knowledge of each other, which keeps their prompts short and their tool selection unambiguous. Agents hold no state between steps; anything a downstream agent needs is passed to it explicitly by the orchestrator.

### Components

| Component | Responsibility | Tool | State |
|---|---|---|---|
| HackerNews Team | Plans the workflow, delegates, merges member output into the final report | none | Owns run context |
| HackerNews Researcher | Retrieves top and topic-relevant stories with their URLs | `HackerNewsTools` | Stateless |
| Article Reader | Fetches and parses full article text behind a URL | `Newspaper4kTools` | Stateless |
| Web Searcher | Gathers supplementary context outside HackerNews | `DuckDuckGoTools` | Stateless, date-aware |

## Request lifecycle

```
User            Streamlit             Team              HN Researcher          Article Reader           Web Searcher
  |                 |                   |                     |                       |                       |
  |-- query -------->                   |                     |                       |                       |
  |                 |-- team.run() ----->                     |                       |                       |
  |                 |                   |                     |                       |                       |
  |                 |                   |-- find stories ----->                       |                       |
  |                 |                   <-- titles + URLs ----|                       |                       |
  |                 |                   |                     |                       |                       |
  |                 |                   |-- read these URLs -------------------------->                       |
  |                 |                   <-- full article text ------------------------|                       |
  |                 |                   |                     |                       |                       |
  |                 |                   |-- context per story ------------------------------------------------>
  |                 |                   <-- snippets + sources -----------------------------------------------|
  |                 |                   |                     |                       |                       |
  |                 |                   |  synthesize         |                       |                       |
  |                 <-- report ---------|                     |                       |                       |
  <-- markdown -----|                   |                     |                       |                       |
```

1. The user submits a query through the Streamlit interface.
2. The orchestrator delegates story discovery to the HackerNews Researcher.
3. Retrieved URLs are passed explicitly to the Article Reader for full text extraction. The instruction set forces this handoff, because the reader has no way to discover URLs on its own.
4. The Web Searcher enriches each story with outside context. The current date is injected into its context so recency-sensitive queries resolve correctly.
5. The orchestrator merges every member response into one markdown report and returns it to the UI.

## Design decisions

**One tool per agent.** Tool selection accuracy drops sharply once an agent has several plausible options for the same step. Giving each agent a single tool removes the choice entirely, and the orchestrator absorbs the routing decision instead.

**Explicit artifact passing.** The Article Reader is never asked to "read the stories." It is handed a concrete list of URLs. Any implicit handoff between agents is a place where the pipeline silently produces an empty result.

**Date injection at the agent level.** Only the Web Searcher gets `add_datetime_to_context=True`. Models have no reliable sense of the current date, so queries like "today's top stories" otherwise resolve against the training cutoff.

**Token ceilings on the local variant.** `llama3.2` members are capped at 1024 tokens. Local models tend to pad delegated subtask responses, which inflates the orchestrator's context and degrades the final synthesis.

## Variants

| File | Model | Notes |
|---|---|---|
| `research_agent.py` | `gpt-4o-mini` via OpenAI API | Key is entered in the UI at runtime and never written to disk |
| `research_agent_llama3.py` | `llama3.2` via Ollama | Runs entirely locally with no API key and no network LLM calls |

## Requirements

- Python 3.8 or later
- An OpenAI API key for the hosted variant
- A local [Ollama](https://ollama.com/) install with `llama3.2` pulled, for the local variant

## Installation

```bash
git clone https://github.com/Shreyanshsaboo/multi-agent-researcher.git
cd multi-agent-researcher
pip install -r requirements.txt
pip install ddgs newspaper4k lxml_html_clean
```

The second install covers the extraction and search backends the Agno tool wrappers call into. They are not pulled in by `agno` itself, and the tools fail at call time rather than import time if they are missing.

For the local variant, pull the model:

```bash
ollama pull llama3.2
```

## Usage

Hosted variant:

```bash
streamlit run research_agent.py
```

Enter your OpenAI API key in the field at the top of the page, then submit a query.

Local variant:

```bash
streamlit run research_agent_llama3.py
```

No key required. Make sure the Ollama daemon is running first.

### Example queries

- Summarize the top AI and machine learning stories on HackerNews today
- Find recent discussions about large language model inference costs
- Research trending developer tools mentioned on HackerNews this week

## Configuration

The model is set per agent at construction time. To trade cost for capability in the hosted variant:

```python
model=OpenAIChat(id="gpt-4o")
```

Agents run with `debug_mode=True` and `show_members_responses=True`, which surfaces each member's intermediate output. Both are useful while tracing a delegation path and should be turned off for a clean end-user report.

The orchestrator's `instructions` list is the workflow definition. Changing the order of those lines changes the pipeline, which is the fastest way to experiment with a different research strategy.

## Project structure

```
multi-agent-researcher/
├── research_agent.py           OpenAI-backed variant
├── research_agent_llama3.py    Ollama-backed local variant
├── requirements.txt
└── README.md
```

## Roadmap

- Provider abstraction so the backend is selectable at runtime instead of per file
- Response caching to avoid refetching articles across related queries
- Report export to PDF, JSON, and Markdown
- Vector store for semantic retrieval over previously researched material
- Containerized deployment

## Credits

Built on the [Agno](https://github.com/agno-agi/agno) agent framework. The initial agent scaffolding was adapted from the `multi_agent_researcher` example in [awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps), Apache 2.0.

## License

Apache License 2.0.

## Author

Shreyansh Saboo, [@Shreyanshsaboo](https://github.com/Shreyanshsaboo)
