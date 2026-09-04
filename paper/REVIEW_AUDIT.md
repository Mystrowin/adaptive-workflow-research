# Final scientific review audit

This review checks the corrected v1.1 manuscript against the immutable audit
and sanitized result export. It does not rerun the benchmark.

| Reviewer objection | Resolution in v1.1 | Remaining limitation |
| --- | --- | --- |
| The same EvalPlus Plus result controlled escalation and scored the endpoint. | The study is consistently labeled oracle-gated and no independent-verifier claim is made. | A held-out or deployment verifier requires a new experiment. |
| Adaptive had up to three attempts while Strong-only had one. | The structural asymmetry and more-attempts confound are explicit; +34 tasks and +6.27 points are emphasized. | Repeated-FAST, repeated-BEST, fixed-cascade, Balanced-only, and budget-matched baselines were not run. |
| McNemar's result could be overinterpreted. | The exact p-value is labeled post-hoc, secondary, and architecturally asymmetric. | There was no preregistered analysis. |
| Tier success rates could be read as standalone capability. | FAST saw nearly all tasks; BALANCED and BEST saw selected residual failures. Tier-use composition is not called efficiency. | A full static Balanced-only condition is absent. |
| Routing could be mistaken for a trained predictive router. | The paper states that hand-written features and online statistics routed 531 FAST, 0 BALANCED, and 11 BEST, with a fixed confidence value. | Predictive-routing superiority is not established. |
| Online statistics can leak earlier labels into later routing. | The run is described as online sequential evaluation, not held-out frozen-router evaluation; task-order sensitivity is explicit. | Multiple orders and a frozen-router study require new runs. |
| Escalation could be described as feedback-guided repair. | Later tiers are stated to receive the original prompt only, not failed code or test feedback. | Feedback-aware repair remains future work. |
| Weighted tokens could be mistaken for physical compute or cost. | They are labeled model-size-weighted token accounting proxies. Raw tokens, calls, sample-integrated CPU estimates, RAM, and summed generation-and-verification time remain visible. | No FLOP, energy, API-credit, or dollar-cost measurement exists. |
| The +10.65% successes-per-proxy value could become the headline. | It is retained only as a post-hoc secondary diagnostic. | The frozen budget curve is nondiscriminating and gives no equal-budget evidence. |
| EvalPlus passing could be presented as proof of correctness. | The endpoint is called a finite Plus-test pass; false acceptance or rejection remains possible. | Independent re-evaluation of old candidates is impossible because generated programs were not retained. |
| Six MBPP failures could be hidden. | All remain in the 542-task denominator. Sanitized tracebacks directly establish the failures; combined static evidence strongly indicates five deserialization mismatches and a tmpfs binding limit for Mbpp/255. | Exact historical source is unavailable, and corrected task outcomes require a new benchmark run. |
| Old public benchmarks may be contaminated. | Plausible contamination and lack of repository-scale coverage are explicit; LiveCodeBench and BigCodeBench are cited as modern context only. | New benchmark experiments were not run. |
| Current code could be mistaken for the historical source. | Documentation distinguishes the post-run improved harness from the unrecoverable exact historical tree and preserves its hash. | Exact historical source reconstruction is unavailable. |
| Model licenses could be flattened under MIT. | The paper/repository separates project MIT, paper CC BY 4.0, OpenAI notices, benchmark obligations, and Qwen tier licenses. | Users must review upstream terms before redistributing model artifacts. |
| AI involvement could be understated. | The paper and repository use the transparent AI-assistance disclosure. | AI assistance is not independent peer review. |

## Conclusion

The manuscript and repository now support only the bounded conclusion that the
three deterministic Qwen2.5-Coder tiers had non-nested EvalPlus pass sets and
that an oracle-gated cascade retained 34 passes absent from the single 7B
condition at this operating point. No historical result was modified.
