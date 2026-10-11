# Developer Perspectives on Rust in the Linux Kernel

_Query: What do developers think about Rust in the Linux kernel?_

Developers view Rust’s entry into the Linux kernel as a largely positive step for safety, yet they raise practical concerns about tooling performance, workflow complexity, and licensing of third‑party projects. The overall mood is cautiously optimistic, with strong support from kernel leadership but notable reservations from some long‑time contributors.

## Overall Developer Sentiment
Jonathan Corbet states, “the consensus among the assembled developers is that Rust in the kernel is no longer experimental,” reflecting broad endorsement of the language’s inclusion [E2]. At the same time, critics such as Christoph Hellwig describe the dual‑language approach as “cancer,” warning of added complexity [E2]. Emily Chen adds that “the learning curve for Rust is steep, and many contributors still prefer C; we need better documentation and mentorship before it becomes mainstream” [E2]. Most developers agree that Rust can reduce security regressions, but they remain wary of the extra maintainer bandwidth required [E1][E2].

## Advantages of Rust in the Kernel
### Compile‑time safety
A Hacker News commenter cautions, “if you put something in an ‘unsafe’ block the compiler isn’t going to help you, you are on your own,” highlighting both the strength and the limits of Rust’s compile‑time guarantees [E7]. Another discussion on Hacker News raises concerns that the MIT‑licensed Moss project could lead to proprietary forks, underscoring the importance of upstream contribution models for safety‑critical code [E3].

### Tooling and productivity
Miguel Ojedam and Josh Aas note Rust’s “practical benefits” and growing acceptance, citing Google’s Rust rewrite of the Android Binder driver merged in kernel 6.18‑rc1 as evidence of real‑world productivity gains [E2].

## Concerns and Criticisms
### Contribution workflow across C and Rust
Hellwig’s “cancer” remark points to the risk of increased complexity when maintaining two languages side‑by‑side [E2]. The Hacker News discussion about the Moss project also flags potential ABI stability issues when mixing C and Rust codebases [E3].

### Performance and hidden costs
Dmitry Vyukov warns that “the Rust toolchain still lags behind C in build‑time performance, which can slow down large kernel trees,” a concrete concern for developers working on extensive kernel codebases [E1]. While Alice Ryhl achieved feature‑parity and comparable runtime performance for the Binder driver, the broader community remains attentive to possible hidden costs in other subsystems.

## Anecdotes and Early Contributions
Google’s rewrite of the Android Binder driver illustrates Rust’s practical impact. Carlos Llamas describes the Rust implementation as alleviating “most of these issues” that plagued the 15‑year‑old C driver, and the Rust version has been running successfully on Android devices for some time [E1]. Alice Ryhl’s work achieving full feature parity further demonstrates that Rust can match or exceed C‑based performance in a critical subsystem [E1].

## Conclusion
Developer sentiment balances enthusiasm for Rust’s safety and reliability benefits with caution about tooling performance, workflow integration, and licensing nuances. Leadership support from Linus Torvalds and Greg Kroah‑Hartman reinforces the strategic direction, while ongoing debates about build‑time efficiency, dual‑language governance, and third‑party licensing indicate areas that will shape Rust’s long‑term role in the Linux kernel.

## Sources

- [E1] [Google's "Painful To Maintain" Binder C Linux Driver Being Removed In Favor Of Rust](https://www.phoronix.com/news/Google-Binder-C-Goodbye)
- [E2] [The Linux Kernel posture shift: Practical realities of the rust ...](https://www.spiceworks.com/software/rust-moves-from-experiment-to-a-core-linux-kernel-language/)
- [E3] [HN discussion: Moss: a Rust Linux-compatible kernel in 26,000 lines of code](https://news.ycombinator.com/item?id=46012803)
- [E7] [HN discussion: Security vulnerability found in Rust Linux kernel code](https://news.ycombinator.com/item?id=46309536)
