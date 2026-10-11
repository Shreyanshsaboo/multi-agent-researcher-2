# Sample runs

Three real, unedited runs of the system on Groq's free tier with the default models. Each folder
holds one run, exported from the run database in the formats the API serves, and a README that
walks through it turn by turn:

| File | Contents | Same as |
|---|---|---|
| `trace.json` | The run and every event, in order | `GET /api/runs/{id}/trace` |
| `result.json` | The run result: report, evidence, review, plan, statistics | `result` of `GET /api/runs/{id}` |
| `report.md` | The report with its cited sources | `GET /api/runs/{id}/report.md` |

The formats are specified in [io-spec.md](../io-spec.md).

| Run | Question | What it shows | Outcome |
|---|---|---|---|
| [rust-in-the-kernel](rust-in-the-kernel/) | What do developers think about Rust in the Linux kernel? | **All six agents.** Long-term memory recalls an earlier run; the coordinator sends the Article Reader to read two sources in full; the critic sends back both drafts, and the coordinator researches its issues in between | Accepted with 3 open issues, 6/10. 199 s, 7 sources |
| [llm-inference-costs](llm-inference-costs/) | How are teams cutting LLM inference costs in 2026? | **The writer–critic loop.** The critic rejects the first draft and names two gaps, the coordinator researches them, and the orchestrator drops a repeated task and turns research on the last turn into a draft | Approved, 8/10. 132 s, 10 sources |
| [sqlite-web-outage](sqlite-web-outage/) | Is SQLite a good choice for production web apps? | **Recovery.** Every Web Researcher tool call fails. The coordinator switches to the Article Reader and sources recalled from memory, the source check rejects a mis-copied URL, and the critic rejects two of the writer's claimed fixes | Accepted with 2 open issues, 6/10. 177 s, 5 sources |

Each run took a different path, because the coordinator decides every step at run time.

The CLI command or request that started each run, the date and the commit are in its README. The
three runs used about 54,000, 70,000 and 69,000 tokens.
