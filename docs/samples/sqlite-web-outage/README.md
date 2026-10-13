# Is SQLite a good choice for production web apps? (with a web search outage)

Run `cli-c2193665`: a real, unedited run, captured on 2026-10-11 with the code at commit `ef60a94`
on Groq's free tier and the default models. Every tool call of the Web Researcher was made to fail,
to show how the team recovers when one agent's tools are down:

```bash
cd backend
python -m app.cli "Is SQLite a good choice for production web apps?" --depth quick --fail web_researcher
```

The files are exported from the run's database in the formats the API serves:

| File | Contents | Same as |
|---|---|---|
| [trace.json](trace.json) | The run and all 179 events, in order | `GET /api/runs/{id}/trace` |
| [result.json](result.json) | The run result: report, evidence, review, plan, statistics | `result` of `GET /api/runs/{id}` |
| [report.md](report.md) | The report with its cited sources | `GET /api/runs/{id}/report.md` |

The formats are specified in [io-spec.md](../../io-spec.md).

## What happened

| Turn | Time | Coordinator's decision | Outcome |
|---|---|---|---|
| 1 | 0–13s | Plan five sub-questions; send the HN Scout and the Web Researcher in parallel | T1 (HN Scout): failed. Its stories had almost no comments, so it saved nothing and suggested broader searches. T2 (Web Researcher): failed. Both its search tools were down, and its model replied with nothing, which the trace reports as an empty report |
| 2 | 18–81s | Try both again with broader instructions | T3 (HN Scout): partial, saving four threads (E1–E4). T4 (Web Researcher): failed again |
| 3 | 87–132s | **Change approach**: with web search down, send the Article Reader to read two of the HN threads in full, and two blog posts that long-term memory had recalled from earlier runs of this question | T5: partial; E1 and E2 are now read in full. T6: success, saving the first blog post (E5). The source check **rejected the second**, because the reader reported it under a mis-copied domain no tool had returned |
| 4 | 135–139s | Draft | Writer: draft v1. Critic: **revise, 6/10**, with three major issues (unsupported claims) and two minor ones |
| 5 | 160–177s | Draft, fixing the critic's issues | Writer: draft v2, marking all five issues fixed. Critic: **revise, 6/10**. Its rulings **accept three of the fixes and reject two**: the figures the writer kept are not in the evidence it cites |

The run then stopped at its turn limit. The report is the second draft, marked **accepted with
issues**, with the critic's two open issues listed in the result. Three of six tasks failed, yet the
run ended with a cited report from the sources the other agents could reach: 177 seconds, 16 tool
calls, 5 sources (all cited), and about 69,000 tokens.

## Things to look for in the trace

- `tool_call` events with phase `failed` and `simulated: true`: every call the Web Researcher made.
- The coordinator's `decision` at turn 3 (seq 96): it stops sending the Web Researcher and gives the
  Article Reader URLs from the HN threads and from the `memory` event (seq 3), which recalled two
  earlier runs of the question.
- The `guardrail` event with rule `unseen_source` (seq 130): the mis-copied URL being rejected.
- The `draft` event for v2 (seq 169) with the writer's response to each issue, and the `review`
  event that follows it, whose `rulings` reject two of them.
