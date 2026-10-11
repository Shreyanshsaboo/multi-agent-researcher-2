# What do developers think about Rust in the Linux kernel?

Run `c24a6258a8f6`: a real, unedited run, started from the web interface on 2026-10-10 while the
demo video was recorded, with the code at commit `cd12fe1` on Groq's free tier and the default
models. The request was:

```json
{"query": "What do developers think about Rust in the Linux kernel?", "options": {"depth": "quick"}}
```

The files are exported from the run's database in the formats the API serves:

| File | Contents | Same as |
|---|---|---|
| [trace.json](trace.json) | The run and all 189 events, in order | `GET /api/runs/{id}/trace` |
| [result.json](result.json) | The run result: report, evidence, review, plan, statistics | `result` of `GET /api/runs/{id}` |
| [report.md](report.md) | The report with its cited sources | `GET /api/runs/{id}/report.md` |

The formats are specified in [io-spec.md](../../io-spec.md).

## What happened

All six agents acted in this run.

| Turn | Time | Coordinator's decision | Outcome |
|---|---|---|---|
| 1 | 0–34s | Plan four sub-questions; send the HN Scout and the Web Researcher in parallel. Long-term memory had recalled an earlier run of the same question, and the coordinator passed the Hacker News threads it found to the HN Scout | T1 (HN Scout): success, with the most discussed thread and its top comments. T2 (Web Researcher): success, with Phoronix and Spiceworks articles. The figure check dropped three key points whose figures were not in the retrieved text |
| 2 | 41–59s | Send the Article Reader to read both articles in full, as two parallel tasks | T3 and T4: success. Their findings merge into E1 and E2, which are now marked as read in full |
| 3 | 70–75s | Draft | Writer: draft v1. Critic: **revise, 6/10**, with three major issues (claims cited to a source that does not say them) and two minor ones |
| 4 | 93–159s | Research the critic's issues: the Web Researcher for statements by kernel maintainers, the HN Scout for further threads | T5 and T6: partial. Four more sources (E4–E7), but not all the support the critic asked for |
| 5 | 174–199s | Draft | Writer: draft v2, revised against the critic's issues, though it did not mark each one fixed or disputed. Critic: **revise, 6/10**, with one major issue (the conclusion mentions maintainers' support without citing the sources that document it) and two minor ones |

The run then stopped at its turn limit. The report is the second draft, marked **accepted with
issues**: the result lists the critic's three open issues and its score, so the reader can see what
the review did not clear. 199 seconds, 6 tasks, 16 tool calls, 7 sources (4 cited), and about
70,000 tokens.

## Things to look for in the trace

- The `memory` event (seq 3): the earlier run of this question recalled with similarity 0.71, and the
  thread ids from it in the HN Scout's task (seq 9).
- `message` events with `kind` `task` from the coordinator to `article_reader` (seq 57 and 58), with
  the URLs to read, and the two `result` messages back.
- The two `review` events: the critic's issues on v1 and v2. The coordinator's decision at turn 4
  (seq 110) cites the critic's issues as its reason for more research.
- `guardrail` events: `ungrounded_figure` for each rejected key point, and `budget` when the run hit
  its turn limit.
