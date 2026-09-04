# Adaptive Workflow oracle-gated cascade results

Experiment: `awb-20260826T042018Z-s20260824-300eaad5`

This is a fixed-workload Adaptive Workflow study, not an EHMN benchmark. Base
and Plus are two test views of each completion. The same EvalPlus Plus outcome
controlled Adaptive acceptance/escalation and the primary endpoint, so results
measure oracle-gated complementarity rather than independent-verifier
performance.

| Condition | HumanEval+ | MBPP+ | Overall |
| --- | ---: | ---: | ---: |
| Adaptive | 43/164 (26.22%) | 288/378 (76.19%) | 331/542 (61.07%) |
| Strong-only | 34/164 (20.73%) | 263/378 (69.58%) | 297/542 (54.80%) |
| Small-only | 26/164 (15.85%) | 194/378 (51.32%) | 220/542 (40.59%) |

Adaptive retained 34 passes not present in Strong-only: FAST 22, BALANCED 12,
BEST 0. Paired outcomes are 297 both pass, 34 Adaptive only, 0 Strong-only
only, and 211 both fail. Adaptive can retain earlier-tier passes and fall back
to the same BEST tier, so this comparison is architecturally asymmetric and
does not isolate the more-attempts effect.

Adaptive used 259,722 raw total tokens versus 117,500; 1,092 model calls versus
542; 1,091 evaluator calls versus 542; 38,137.61 versus 33,421.46
sample-integrated CPU-seconds; and 78,701.93 versus 47,582.32 summed
generation-and-verification wall seconds. The weighted total-token accounting
proxy was 899,462.8 versus 893,000.0. Parameter-weighted tokens are not FLOPs,
hardware work, energy, API usage, credits, or dollar cost. The 10.65%
successes-per-proxy diagnostic is post-hoc and secondary; the frozen budget
curve is nondiscriminating and provides no equal-budget evidence.

Initial routing was FAST 531, BALANCED 0, BEST 11. The heuristic router used
online statistics and a fixed confidence field. Earlier EvalPlus labels could
influence later decisions, and tier histories are conditionally selected.

Six shared MBPP infrastructure failures remain in the denominator. Preserved
errors and static inspection strongly indicate bypassed EvalPlus MBPP input
deserialization for five tasks and a 512 MiB tmpfs binding limit for Mbpp/255;
the failure symptoms are direct evidence, while the causal mapping is a strong
inference because exact historical source is unavailable. Corrected
outcomes would require a new run. Exact historical generated programs were not retained. No universal efficiency,
predictive-routing, or general coding superiority claim is supported.
