# SQLite for Production Web Applications: A Practical Assessment

_Query: Is SQLite a good choice for production web apps?_

SQLite can be a viable backend for production web applications when the workload is read‑heavy or modest in scale, and when developers accept its single‑writer architecture and plan for durability and concurrency handling. Evidence from recent analyses shows that SQLite remains popular in production, especially when paired with managed services that add replication and edge distribution [E5][E3].

## 1. Performance characteristics
| Metric | Single‑threaded (typical) | Concurrent access (typical) |
|--------|---------------------------|-----------------------------|
| Read throughput | ~10–20 k reads / second | ~1–2 k reads / second |
| Write latency | sub‑millisecond (single writer) | limited by one writer at a time |
| CPU / memory | very low | low, but contention can increase latency |

SQLite delivers sub‑millisecond read latency in a single‑threaded workload and can sustain roughly 10–20 k reads / second, dropping to about 1–2 k reads / second when multiple clients issue reads concurrently [E5]. Writes are serialized in WAL mode, so write latency remains low but overall write throughput is bounded by the single‑writer limit. Compared with server‑grade databases, SQLite’s raw write throughput is lower, yet its minimal overhead and zero‑configuration make it competitive for small‑to‑medium traffic patterns, as demonstrated by a high‑traffic Nuxt‑based World Cup prediction app that succeeded after tuning WAL and busy‑timeout settings [E3].

## 2. Concurrency and write contention
SQLite uses file‑level locking: reads can proceed in parallel, but only one writer may commit at a time in WAL mode [E5]. HN discussions about Capsule and Potatoverse highlight this single‑writer bottleneck and note that bursts of writes can trigger `SQLITE_BUSY` errors, requiring retry/back‑off logic and careful `busy_timeout` configuration [E1][E4]. The Potatoverse thread also warns that placing the database on networked filesystems (e.g., NFS) can worsen locking behavior, though this observation is specific to that platform’s deployment model [E4]. Mitigation strategies include:
- Enabling WAL (`PRAGMA journal_mode=WAL`) and setting an appropriate `busy_timeout`.
- Limiting the number of concurrent connections per process.
- Using managed services (Turso, D1) that handle connection pooling and replication.

## 3. Durability and data integrity
When WAL mode is active, SQLite writes changes to a write‑ahead log before flushing to the main file, providing atomic commits and crash recovery [E5]. The article recommends `PRAGMA synchronous=NORMAL` for a balance of durability and performance, or `FULL` when maximum safety is required. Because SQLite lacks built‑in point‑in‑time recovery, regular backups—either by copying the database and WAL files or using the `.backup` command—are essential [E5]. HN commentary on the Capsule platform stresses keeping the database on stable local storage rather than bundling it with the application binary, to avoid data loss when the file is moved across devices [E1].

## 4. Tooling, ecosystem support, and deployment patterns
Modern managed offerings extend SQLite beyond a local file:
- **Turso, Cloudflare D1, and LibSQL** provide native replication and edge‑distributed hosting, turning SQLite into a high‑availability backend for small‑to‑medium apps, though they do not promise automatic failover [E5].
- **ORMs and drivers** such as Drizzle ORM and `better-sqlite3` (with built‑in busy‑timeout handling) simplify schema migrations and connection management [E5].
- **Static‑binary platforms** like Potatoverse bundle SQLite directly into executables for simple deployment, while the Capsule discussion shows SQLite embedded in single‑file web apps for zero‑config persistence [E1][E4].
- **WebAssembly deployments**: a note‑taking app compiled to WASM demonstrates that SQLite can run entirely in the browser, enabling offline‑first experiences, though the thread contains no performance data [E2].

## 5. Common pitfalls and best‑practice mitigations
| Pitfall | Mitigation |
|---------|------------|
| Single‑writer bottleneck | Use WAL, set `busy_timeout`, employ retry/back‑off, or offload writes to a managed service that distributes load [E5]. |
| File‑locking on networked storage | Prefer local SSDs; avoid NFS unless the platform explicitly supports it [E4]. |
| Durability concerns | Configure `synchronous` appropriately, schedule regular backups, and keep the DB on stable storage [E5][E1]. |
| Lack of built‑in HA | Deploy via Turso/D1/LibSQL for replication; implement application‑level health checks and reconnect logic [E5]. |
| Limited tooling for large migrations | Use Drizzle ORM or other migration frameworks that understand SQLite schema evolution [E5]. |

## Open questions and limitations
- **Quantitative write throughput**: The evidence provides read‑throughput ranges but does not give exact write‑per‑second numbers for typical production workloads.
- **Edge latency and pricing**: While Turso, D1, and LibSQL are noted for edge distribution, the sources do not detail latency impacts or cost structures, leaving a gap for budgeting decisions.
- **WASM performance**: The note‑taking app (E2) confirms SQLite can run in the browser, yet no benchmark data are available, so suitability for high‑frequency client‑side writes remains uncertain.
- **Failover semantics**: Managed services add replication, but the evidence does not confirm automatic failover; operators must design their own fallback logic.

## FAQ
**Q: Can SQLite replace PostgreSQL for a typical SaaS backend?**
A: It can for read‑heavy, low‑to‑moderate write workloads where simplicity and low overhead are priorities. For write‑intensive or highly concurrent scenarios, a server‑grade DB may still be preferable.

**Q: Is WAL mode required for production?**
A: Yes. WAL enables concurrent reads and provides atomic commit semantics; it is the recommended mode for any production deployment [E5].

**Q: Do I need a managed service?**
A: Not strictly, but services like Turso or D1 simplify replication, edge distribution, and connection pooling, reducing the engineering effort required to achieve high availability [E5].

**Q: How do I back up a live SQLite database?**
A: Use the `.backup` command or copy both the main database file and the WAL file while the database is in a consistent state; schedule this regularly [E5].

**Q: Is SQLite in WebAssembly production‑ready?**
A: It works for offline‑first apps, as shown by the note‑taking example [E2], but performance characteristics and durability under heavy client‑side writes are not quantified in the current evidence.

## Sources

- [E1] [HN discussion: Show HN: Capsule – Single-file web apps that save their data into SQLite](https://news.ycombinator.com/item?id=49712278)
- [E2] [HN discussion: Show HN: Local-first note taking web app powered by SQLite WASM – notem](https://news.ycombinator.com/item?id=49322163)
- [E3] [HN discussion: Show HN: Bench-Bets – A World Cup Prediction App Built with Nuxt and SQLite](https://news.ycombinator.com/item?id=48196996)
- [E4] [HN discussion: Show HN: Potatoverse platform for webapps, SQLite and static binary](https://news.ycombinator.com/item?id=47211374)
- [E5] [The SQLite Renaissance: Why the World's Most Deployed Database Is Taking Over Production in 2026](https://pockit.tools/blog/sqlite-renaissance-turso-d1-libsql-production-guide/)
