# How are teams cutting LLM inference costs in 2026?

Run `cli-d3c6ff50`: a real, unedited run, captured on 2026-10-10 with the code at commit `825b6a3`
on Groq's free tier and the default models:

```bash
cd backend
python -m app.cli "How are teams cutting LLM inference costs in 2026?" --depth quick --trace trace.json
```

The files are exported from the run's database in the formats the API serves:

| File | Contents | Same as |
|---|---|---|
| [trace.json](trace.json) | The run and all 173 events, in order | `GET /api/runs/{id}/trace` |
| [result.json](result.json) | The run result: report, evidence, review, plan, statistics | `result` of `GET /api/runs/{id}` |
| [report.md](report.md) | The report with its cited sources | `GET /api/runs/{id}/report.md` |

The formats are specified in [io-spec.md](../../io-spec.md).

## What happened

| Turn | Time | Coordinator's decision | Outcome |
|---|---|---|---|
| 1 | 0–18s | Plan four sub-questions; send the HN Scout and the Web Researcher in parallel | T1 (HN Scout): partial. It saved three recent stories, none of which had comments yet. T2 (Web Researcher): success, saving an IBM report. The points it reported from an NVIDIA blog and an arXiv paper were rejected by the figure check |
| 2 | 18–39s | Draft | Writer: draft v1. Critic: **revise, 5/10**. Two major and two minor issues, mostly claims the evidence did not support, and two research gaps for the Web Researcher |
| 3 | 39–84s | Research the critic's two gaps, as two parallel Web Researcher tasks | T3: success, with case studies of spot and preemptible GPUs. T4: failed. Every key point it reported had figures that were not in the text its tools returned, so the figure check rejected them all |
| 4 | 84–110s | Two more Web Researcher tasks | The orchestrator **dropped one as a repeat of T3** and ran the other. T5: success, with ARM and custom-ASIC sources |
| 5 | 110–132s | More research, which the orchestrator **turned into a draft** because nothing researched on the last turn could reach the report | Writer: draft v2, marking all four issues fixed. Critic: **approve, 8/10** |

The coordinator never called the Article Reader in this run: it drafted from the search results
after the first turn, and the critic's gaps asked for new sources rather than closer reading.

The run then stopped at its turn limit with the approved draft: 132 seconds, 12 tool calls, 10
sources (9 cited), and about 54,000 tokens. Most of the time was spent waiting for per-minute token
quota. Each wait, and each call moved to a model with room, is in the trace as a `rate_limited` or
`model_fallback` event.

## Things to look for in the trace

- `message` events with `kind` `task` and `result`: the coordinator delegating and the researchers
  reporting back, including T4's failure.
- `guardrail` events: `ungrounded_figure` for each rejected key point, and `decision_corrected`
  for the dropped repeat task and the last-turn draft.
- `review` events: the critic's issues on v1 and its approval of v2. The `draft` event for v2 lists
  the writer's response to each issue.
- `metrics` events: tokens and duration per agent call, and `served_by` where some calls ran on
  another model.
