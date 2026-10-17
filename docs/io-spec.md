# Input and output specification

This document defines what goes into a run, what comes out, and what the agents exchange on the
way. The Pydantic models in [`backend/app/schemas.py`](../backend/app/schemas.py) are the source of
truth. The samples are real: they are taken from the run in
[samples/llm-inference-costs/](samples/llm-inference-costs/) (run `cli-d3c6ff50`), shortened for
reading: strings cut for length end in `…`, and long lists keep only their first items. The files
themselves hold every event and field, and [samples/](samples/) has two more runs in the same formats.

## Contents

1. [Input: the run request](#1-input-the-run-request)
2. [Output: the run result](#2-output-the-run-result)
3. [The event trace](#3-the-event-trace)
4. [What the agents exchange](#4-what-the-agents-exchange)

## 1. Input: the run request

A run is started with `POST /api/runs` (or `python -m app.cli`, which builds the same request).

| Field | Type | Required | Rules |
|---|---|---|---|
| `query` | string | yes | 3–500 characters after collapsing whitespace, with at least 3 letters or digits |
| `options.depth` | `"quick"` \| `"standard"` \| `"deep"` | no, default `"standard"` | Selects the budget (turns, drafts, parallel tasks, findings per task, URLs per read, time limit) |
| `options.simulate_failures` | list of `"hn_scout"`, `"web_researcher"`, `"article_reader"` | no, default `[]` | Every tool call of these workers fails, to demonstrate recovery |
| `thread_id` | string, up to 64 characters | no | Continue an existing conversation. The run sees the earlier questions, answers and cited sources |

The sample run's request:

```json
{
  "query": "How are teams cutting LLM inference costs in 2026?",
  "options": {
    "depth": "quick",
    "simulate_failures": []
  },
  "thread_id": null
}
```

| Response | When |
|---|---|
| `202 {"run_id": "...", "thread_id": "..."}` | The run started. A new conversation's `thread_id` equals its `run_id` |
| `422` | The request does not match the schema |
| `404` | `thread_id` names no conversation |
| `429` | `MAX_ACTIVE_RUNS` runs are already in progress, or `MAX_RUNS_PER_DAY` runs started in the last 24 hours |
| `503` | No model is configured on the server |

## 2. Output: the run result

When a run ends, its result is available from `GET /api/runs/{id}` (field `result`) and as the
payload of the final `run_completed` event. The report alone is served as Markdown from
`GET /api/runs/{id}/report.md`.

| Field | Type | Meaning |
|---|---|---|
| `run_id`, `query` | string | The run and its question |
| `status` | `"completed"` \| `"rejected"` \| `"failed"` | `rejected`: the coordinator judged the query unresearchable |
| `title`, `report_markdown` | string | The report. Claims cite evidence as `[E1]`, `[E2][E5]` |
| `message` | string | A note for the user, such as why the run stopped early |
| `evidence` | list of Evidence | Every source the team collected (below) |
| `cited_ids` | list of string | The evidence ids the report cites, in order of first citation |
| `review_status` | `"approved"` \| `"accepted_with_issues"` \| `"unreviewed"` \| `"none"` | Whether the critic approved the final draft, the coordinator accepted it with open issues, it was never reviewed, or there is no report |
| `final_score` | integer 1–10 or null | The critic's score for the final draft |
| `unresolved_issues` | list of Issue | Critic issues still open in the final draft |
| `plan` | list of PlanItem | The coordinator's final plan: `id`, `question`, `status` (`open`, `in_progress`, `answered`, `dropped`) |
| `stats` | object | `turns`, `tasks`, `failed_tasks`, `tool_calls`, `drafts`, `duration_s`, and `tokens` per agent |

An **Evidence** item:

| Field | Meaning |
|---|---|
| `id` | `E1`, `E2`, … in the order sources were first saved |
| `url`, `title` | The source as its tool returned it |
| `source_type` | `hackernews`, `web`, `news` or `article` |
| `found_by` | The agents that reported it; findings for the same URL merge |
| `key_points` | Up to 6 facts, figures or attributed opinions, each checked against the retrieved text |
| `full_text_read` | Whether the article reader (or a comment-thread read) saw the full text |
| `published` | Publication date, when known |
| `meta` | Source details, such as HN points and comments, or the publisher |

The sample run's result, with the evidence list shortened to its first item:

```json
{
  "run_id": "cli-d3c6ff50",
  "query": "How are teams cutting LLM inference costs in 2026?",
  "status": "completed",
  "title": "Cost‑Cutting Strategies for LLM Inference in 2026",
  "report_markdown": "Teams cutting LLM inference costs in 2026 rely on a combination of hardware efficiencies, software techniques, and cloud‑operational tactics that are documented in recent 2026 sources.\n\n## Hardware and Accelerator Choices\nEvidence shows tha…",
  "message": "Stopped early (turn limit of 5 reached); this is the latest draft.",
  "evidence": [
    {
      "id": "E1",
      "url": "https://research.ibm.com/blog/running-open-models-on-h100-gpus-with-llmd",
      "title": "How llm-d makes the most of the hardware you already have",
      "source_type": "web",
      "found_by": [
        "web_researcher"
      ],
      "key_points": [
        "IBM and Red Hat deployed a 753B open‑source model on NVIDIA H100 GPUs, achieving 5‑10× lower cost per token compared with commercial API pricing.",
        "The llm‑d stack combined TensorRT‑based kernel fusion, dynamic batching, and Kubernetes autoscaling to serve thousands of concurrent coding agents."
      ],
      "full_text_read": false,
      "published": null,
      "meta": {
        "publisher": "research.ibm.com"
      }
    }
  ],
  "cited_ids": [
    "E1",
    "E9",
    "E10",
    "E3",
    "E2"
  ],
  "final_score": 8,
  "review_status": "approved",
  "unresolved_issues": [],
  "plan": [
    {
      "id": 1,
      "question": "What operational approaches (spot instances, serverless inference, multi‑tenant serving) are being adopted in 2025‑2026 to cut LLM inference costs?",
      "status": "open"
    },
    {
      "id": 2,
      "question": "What evidence exists for ARM-based accelerators or custom ASICs being used for LLM inference in 2025‑2026?",
      "status": "answered"
    }
  ],
  "stats": {
    "turns": 5,
    "tasks": 5,
    "failed_tasks": 1,
    "tool_calls": 12,
    "drafts": 2,
    "duration_s": 132.3,
    "tokens": {
      "coordinator": 13568,
      "web_researcher": 17584,
      "hn_scout": 10524,
      "writer": 5829,
      "critic": 6703
    }
  }
}
```

## 3. The event trace

A run's trace is the ordered list of everything that happened in it. It is streamed live from
`GET /api/runs/{id}/events` (server-sent events, resumable with `Last-Event-ID`) and downloaded
from `GET /api/runs/{id}/trace` as `{"run": {...}, "events": [...]}`.

Every event has the same envelope:

| Field | Meaning |
|---|---|
| `seq` | Position in the run, from 1 |
| `ts` | Unix time |
| `elapsed` | Seconds since the run started |
| `type` | One of the types below |

| Type | Emitted when | Payload |
|---|---|---|
| `run_started` | The run begins | `run_id`, `thread_id`, `query`, `options`, `budget`, `agents` (each agent's role, model and tools), `follow_up` |
| `message` | One agent addresses another (section 4) | `id`, `sender`, `recipients`, `kind`, `summary`, `content` |
| `agent_status` | An agent starts or stops work | `agent`, `state` (`thinking`, `working`, `writing`, `reviewing`, `waiting`, `idle`), `detail` |
| `plan` | The coordinator returns its plan | `turn`, `items` |
| `tool_call` | A tool call starts and ends | `agent`, `task_id`, `call_id`, `tool`, `phase` (`started`, `completed`, `failed`), then `args`, or `preview` / `error` and `duration_ms` |
| `evidence` | A finding passes its checks and is saved | `agent`, `task_id`, `created` (false when merged into an existing item), `item` |
| `metrics` | An agent's model call finishes | `agent`, `model`, `input_tokens`, `output_tokens`, `duration_s`, `tool_calls`, and `served_by` when some calls ran on another model |
| `guardrail` | A guardrail acts | `agent`, `rule` (`unseen_source`, `ungrounded_figure`, `salvaged`, `decision_corrected`, `budget`, `malformed_output`, `malformed_tool_call`), `detail` |
| `rate_limited` | A call waits for model quota | `agent`, `model`, `retry_after_s`, `detail` |
| `model_fallback` | A call moves to another model | `agent`, `primary`, `fallback`, `detail` |
| `agent_error` | An agent fails | `agent`, `error` |
| `draft` | The writer produces a draft | `draft`: `version`, `title`, `markdown`, `responses`, `fallback` |
| `review` | The critic reviews a draft | `review`: `draft_version`, `critique`, `checks` (the citation check), `error` |
| `memory` | Similar past research is recalled | `items` |
| `context` | A follow-up carries sources from earlier answers | `turns`, `carried` |
| `run_completed` | The run ends with a result | `result` (section 2) |
| `run_failed` | The run ends without one | `error` |

Sample events from the trace, in order:

```json
[
  {
    "seq": 1,
    "ts": 1791619480.0144079,
    "elapsed": 0.0,
    "type": "run_started",
    "run_id": "cli-d3c6ff50",
    "thread_id": "cli-d3c6ff50",
    "query": "How are teams cutting LLM inference costs in 2026?",
    "options": {
      "depth": "quick",
      "simulate_failures": []
    },
    "budget": {
      "max_turns": 5,
      "max_drafts": 2,
      "max_tasks_per_turn": 2,
      "max_findings_per_task": 4,
      "max_urls_per_read": 2,
      "time_limit_s": 360
    },
    "agents": [
      {
        "id": "coordinator",
        "name": "Coordinator",
        "kind": "orchestrator",
        "role": "Breaks the query into a research plan, decides which agent acts next, re-plans when tasks fail or the critic finds gaps, and decides when the report is done.",
        "tools": [],
        "model": "openai/gpt-oss-120b"
      }
    ],
    "follow_up": false
  },
  {
    "seq": 2,
    "ts": 1791619480.028169,
    "elapsed": 0.01,
    "type": "message",
    "id": "m1",
    "sender": "user",
    "recipients": [
      "coordinator"
    ],
    "kind": "query",
    "summary": "How are teams cutting LLM inference costs in 2026?",
    "content": null
  },
  {
    "seq": 6,
    "ts": 1791619481.7490282,
    "elapsed": 1.74,
    "type": "plan",
    "turn": 1,
    "items": [
      {
        "id": 1,
        "question": "What hardware‑level optimizations (e.g., quantization, sparsity, specialized accelerators) are teams using in 2026 to reduce LLM inference cost?",
        "status": "open"
      },
      {
        "id": 2,
        "question": "Which software‑stack strategies (e.g., model serving frameworks, batching, caching, pipeline parallelism) are being adopted to cut inference expenses?",
        "status": "open"
      },
      {
        "id": 3,
        "question": "What operational approaches (e.g., workload scheduling, spot instances, multi‑tenant serving, serverless inference) are teams employing to lower cost?",
        "status": "open"
      },
      {
        "id": 4,
        "question": "Are there any notable case studies or public reports from 2025‑2026 describing cost reductions achieved by specific companies or open‑source projects?",
        "status": "open"
      }
    ]
  },
  {
    "seq": 8,
    "ts": 1791619481.7494779,
    "elapsed": 1.74,
    "type": "message",
    "id": "m3",
    "sender": "coordinator",
    "recipients": [
      "hn_scout"
    ],
    "kind": "task",
    "summary": "Search Hacker News comments and posts from Jan 2025 to Sep 2026 for discussions about cutting LLM inference costs, focusing on hardware quantization, sparsity, accelerator use, bat…",
    "content": {
      "agent": "hn_scout",
      "instruction": "Search Hacker News comments and posts from Jan 2025 to Sep 2026 for discussions about cutting LLM inference costs, focus…",
      "urls": [],
      "rationale": "Gather practitioner insights and recent community debates.",
      "task_id": "T1"
    }
  },
  {
    "seq": 12,
    "ts": 1791619482.465216,
    "elapsed": 2.45,
    "type": "tool_call",
    "phase": "started",
    "args": {
      "query": "LLM inference cost cutting 2026",
      "sort": "relevance",
      "days": 365
    },
    "agent": "hn_scout",
    "task_id": "T1",
    "call_id": "T1.1",
    "tool": "search_hackernews"
  },
  {
    "seq": 15,
    "ts": 1791619483.431496,
    "elapsed": 3.42,
    "type": "tool_call",
    "phase": "completed",
    "preview": "No Hacker News stories matched 'LLM inference cost cutting 2026'. Try fewer or broader keywords.",
    "duration_ms": 966,
    "agent": "hn_scout",
    "task_id": "T1",
    "call_id": "T1.1",
    "tool": "search_hackernews"
  },
  {
    "seq": 23,
    "ts": 1791619486.6740422,
    "elapsed": 6.66,
    "type": "model_fallback",
    "agent": "hn_scout",
    "primary": "openai/gpt-oss-20b",
    "fallback": "openai/gpt-oss-120b",
    "detail": "openai/gpt-oss-20b has no tokens left this minute; calls go to openai/gpt-oss-120b meanwhile"
  },
  {
    "seq": 24,
    "ts": 1791619487.35159,
    "elapsed": 7.34,
    "type": "rate_limited",
    "agent": "hn_scout",
    "retry_after_s": 7.0,
    "model": "openai/gpt-oss-120b",
    "detail": "openai/gpt-oss-120b has no tokens left this minute"
  },
  {
    "seq": 32,
    "ts": 1791619494.555758,
    "elapsed": 14.54,
    "type": "evidence",
    "agent": "web_researcher",
    "task_id": "T2",
    "created": true,
    "item": {
      "id": "E1",
      "url": "https://research.ibm.com/blog/running-open-models-on-h100-gpus-with-llmd",
      "title": "How llm-d makes the most of the hardware you already have",
      "source_type": "web",
      "found_by": [
        "web_researcher"
      ],
      "key_points": [
        "IBM and Red Hat deployed a 753B open‑source model on NVIDIA H100 GPUs, achieving 5‑10× lower cost per token compared with commercial API pricing.",
        "The llm‑d stack combined TensorRT‑based kernel fusion, dynamic batching, and Kubernetes autoscaling to serve thousands of concurrent coding agents."
      ],
      "full_text_read": false,
      "published": null,
      "meta": {
        "publisher": "research.ibm.com"
      }
    }
  },
  {
    "seq": 33,
    "ts": 1791619494.556106,
    "elapsed": 14.54,
    "type": "guardrail",
    "agent": "web_researcher",
    "task_id": "T2",
    "rule": "ungrounded_figure",
    "detail": "Dropped 2 point(s) for https://arxiv.org/pdf/2509.18886 with figures not in the source: Running inference on NVIDIA H100 Confidential Compute GPUs incurred only a 4‑8% throughput p…"
  },
  {
    "seq": 36,
    "ts": 1791619497.684161,
    "elapsed": 17.67,
    "type": "metrics",
    "agent": "hn_scout",
    "model": "openai/gpt-oss-20b",
    "input_tokens": 9902,
    "output_tokens": 622,
    "duration_s": 15.94,
    "tool_calls": 4,
    "served_by": {
      "openai/gpt-oss-20b": 6,
      "openai/gpt-oss-120b": 1
    }
  },
  {
    "seq": 41,
    "ts": 1791619497.6855109,
    "elapsed": 17.67,
    "type": "message",
    "id": "m5",
    "sender": "hn_scout",
    "recipients": [
      "coordinator"
    ],
    "kind": "result",
    "summary": "[partial] I located several recent Hacker News stories discussing LLM inference cost reductions, but none had any comments yet, so I could not capture practitioner opinions. The Co…",
    "content": {
      "task_id": "T1",
      "agent": "hn_scout",
      "instruction": "Search Hacker News comments and posts from Jan 2025 to Sep 2026 for discussions about cutting LLM inference costs, focus…",
      "status": "partial",
      "summary": "I located several recent Hacker News stories discussing LLM inference cost reductions, but none had any comments yet, so…",
      "evidence_ids": [
        "E2",
        "E3"
      ],
      "tool_calls": 4,
      "errors": [],
      "duration_s": 15.9
    }
  },
  {
    "seq": 55,
    "ts": 1791619512.013251,
    "elapsed": 32.0,
    "type": "draft",
    "draft": {
      "version": 1,
      "title": "2026 LLM Inference Cost‑Reduction Strategies",
      "markdown": "In 2026, teams are aggressively trimming LLM inference expenses through coordinated hardware, software, and operational tactics. Quantization, sparsity, and cutting‑edge accelerato…",
      "responses": [],
      "fallback": false
    }
  },
  {
    "seq": 125,
    "ts": 1791619568.440043,
    "elapsed": 88.43,
    "type": "guardrail",
    "agent": "orchestrator",
    "rule": "decision_corrected",
    "detail": "Dropped a web_researcher task that repeats T3 ([success]). Change the angle or keywords, use another agent, or draft from the evidence you have."
  },
  {
    "seq": 172,
    "ts": 1791619612.3543649,
    "elapsed": 132.34,
    "type": "message",
    "id": "m24",
    "sender": "coordinator",
    "recipients": [
      "user"
    ],
    "kind": "final",
    "summary": "Stopped early (turn limit of 5 reached); this is the latest draft.",
    "content": {
      "status": "completed",
      "review_status": "approved"
    }
  }
]
```

## 4. What the agents exchange

Agents never call each other. Every exchange goes through the orchestrator and is recorded as a
`message` event whose `content` holds the structured payload.

| `kind` | From → to | `content` |
|---|---|---|
| `query` | user → coordinator | none; the query is the summary |
| `decision` | coordinator → addressed agents | CoordinatorDecision, plus `turn` and `fallback` |
| `task` | coordinator → researcher | TaskSpec, plus `task_id` |
| `result` | researcher → coordinator | TaskResult |
| `brief` | coordinator → writer | `version` of the draft to write |
| `draft` | writer → critic | `version`, `title`, `responses` |
| `verdict` | critic → coordinator | Critique |
| `critique` | critic → writer | the Critique's issues |
| `final` | coordinator → user | `status`, `review_status` |

### CoordinatorDecision

| Field | Meaning |
|---|---|
| `thought` | 1–3 sentences on why this action now |
| `plan` | The full, updated plan |
| `action` | `delegate`, `draft`, `finish` or `reject` |
| `tasks` | For `delegate`: TaskSpecs (`agent`, `instruction`, `urls` for the article reader as URLs or evidence ids, `rationale`) |
| `writer_brief` | For `draft`: structure, emphasis, issues to fix |
| `message` | For `finish` or `reject`: a note for the user |

The coordinator's first decision in the sample run:

```json
{
  "thought": "Start by breaking the query into concrete sub‑questions and launch parallel scouting on Hacker News and web sources to gather recent practices and cost‑cutting techniques for LLM inference in 2026.",
  "plan": [
    {
      "id": 1,
      "question": "What hardware‑level optimizations (e.g., quantization, sparsity, specialized accelerators) are teams using in 2026 to reduce LLM inference cost?",
      "status": "open"
    },
    {
      "id": 2,
      "question": "Which software‑stack strategies (e.g., model serving frameworks, batching, caching, pipeline parallelism) are being adopted to cut inference expenses?",
      "status": "open"
    },
    {
      "id": 3,
      "question": "What operational approaches (e.g., workload scheduling, spot instances, multi‑tenant serving, serverless inference) are teams employing to lower cost?",
      "status": "open"
    },
    {
      "id": 4,
      "question": "Are there any notable case studies or public reports from 2025‑2026 describing cost reductions achieved by specific companies or open‑source projects?",
      "status": "open"
    }
  ],
  "action": "delegate",
  "tasks": [
    {
      "agent": "hn_scout",
      "instruction": "Search Hacker News comments and posts from Jan 2025 to Sep 2026 for discussions about cutting LLM inference costs, focusing on hardware quantization, sparsity, accelerator use, batching, caching, and spot instance strategies.",
      "urls": [],
      "rationale": "Gather practitioner insights and recent community debates."
    },
    {
      "agent": "web_researcher",
      "instruction": "Find recent (2025‑2026) articles, blog posts, and technical reports on LLM inference cost‑saving techniques, including hardware (e.g., NVIDIA H100, AMD Instinct, custom ASICs), software (e.g., TensorRT, vLLM, DeepSpeed), and operational met…",
      "urls": [],
      "rationale": "Collect authoritative sources and concrete numbers."
    }
  ],
  "writer_brief": "",
  "message": "",
  "turn": 1,
  "fallback": false
}
```

### TaskResult

A researcher's work on one task, as the coordinator sees it on its next turn:

```json
{
  "task_id": "T1",
  "agent": "hn_scout",
  "instruction": "Search Hacker News comments and posts from Jan 2025 to Sep 2026 for discussions about cutting LLM inference costs, focusing on hardware quantization, sparsity, accelerator use, batching, caching, and spot instance strategies.",
  "status": "partial",
  "summary": "I located several recent Hacker News stories discussing LLM inference cost reductions, but none had any comments yet, so I could not capture practitioner opinions. The Coordinator should look for newer posts or use a broader search to find…",
  "evidence_ids": [
    "E2",
    "E3",
    "E4"
  ],
  "tool_calls": 4,
  "errors": [],
  "duration_s": 15.9
}
```

The researcher itself ends its tool loop with a plain-text report, which is parsed into the
summary and findings above; findings are saved only after the checks in
[design.md](design.md#7-guardrails):

```text
STATUS: success | partial | failed
REPORT: 1-3 sentences on what was found, what failed, and what to do next
FINDING: <exact url from tool output>
TITLE: <short title>
- <key point>
```

### WriterOutput

`title`, `report_markdown`, and when revising, `responses`: one per critic issue with `issue_id`,
`action` (`fixed` or `disputed`) and `note`. The orchestrator records it as a Draft.

### Critique

| Field | Meaning |
|---|---|
| `verdict` | `approve` (no major issues and score 7 or more) or `revise` |
| `score` | 1–10 |
| `summary` | One paragraph |
| `issues` | Up to 5, each with `id`, `severity` (`minor`, `major`), `kind` (`unsupported_claim`, `citation_error`, `missing_coverage`, `contradiction`, `clarity`), `detail`, `suggestion` |
| `research_requests` | Up to 2 gaps the evidence cannot fill, each with the worker best placed to fill it |
| `rulings` | One per issue the writer disputed: `issue_id`, `accepted`, `note` |

The critic's first verdict in the sample run:

```json
{
  "verdict": "revise",
  "score": 5,
  "summary": "The draft covers the plan's sub-questions but relies heavily on general knowledge to fill gaps not supported by the provided evidence, leading to several unsupported claims.",
  "issues": [
    {
      "id": "I1",
      "severity": "major",
      "kind": "unsupported_claim",
      "detail": "The claim that 'Emerging ARM-based accelerators are also being explored' and 'Custom ASICs tailored for transformer workloads are beginning to surface' is not supported by any of the provided evidence sources.",
      "suggestion": "Remove these specific hardware claims or add a citation if new evidence is found; otherwise, generalize the statement to reflect only what is in the evidence (e.g., H100s and TensorRT)."
    },
    {
      "id": "I2",
      "severity": "major",
      "kind": "unsupported_claim",
      "detail": "The section on Operational Approaches makes specific claims about 'Spot and preemptible instances,' 'Serverless inference platforms,' and 'Multi-tenant serving' that are not backed by any of the four evidence items provided.",
      "suggestion": "Either remove these specific operational tactics or mark them as general industry context not derived from the specific 2026 case studies in the evidence, or request new evidence covering these operational strategies."
    },
    {
      "id": "I3",
      "severity": "minor",
      "kind": "unsupported_claim",
      "detail": "The mention of 'DeepSpeed, vLLM, and TensorRT-LLM' in the Software-Stack section is not supported by the evidence, which only explicitly mentions the 'llm-d stack' and 'TensorRT-based kernel fusion' in [E1].",
      "suggestion": "Limit the software framework discussion to llm-d and TensorRT as evidenced, or clearly distinguish between general industry tools and the specific tools cited in the evidence."
    },
    {
      "id": "I4",
      "severity": "minor",
      "kind": "clarity",
      "detail": "The introductory paragraph contains a list of strategies (quantization, sparsity, spot instances, etc.) that are largely unsupported by the specific evidence provided, creating a misleading impression that the report will substantiate all t…",
      "suggestion": "Revise the introduction to focus on the specific techniques supported by the evidence (e.g., llm-d, prompt caching, lossless compression) or clearly label the broader context as general background."
    }
  ],
  "research_requests": [
    {
      "agent": "web_researcher",
      "instruction": "Find specific 2025-2026 case studies or reports detailing the use of spot instances, serverless inference, or multi-tenant serving for LLM cost reduction to support the Operational Approaches section."
    },
    {
      "agent": "web_researcher",
      "instruction": "Search for recent (2025-2026) evidence regarding the adoption of ARM-based accelerators or custom ASICs specifically for LLM inference to validate the hardware claims in the draft."
    }
  ],
  "rulings": []
}
```
