# Adaptive Workflow Local Routing Benchmark

Experiment: `awb-20260826T042018Z-s20260824-300eaad5`

This report evaluates Adaptive Workflow. It is not an EHMN benchmark.
Base and Plus scores use the same generated completions and are not independent samples.
Model-weighted token values are cost proxies, not measured FLOPs or hardware compute.
No efficiency advantage is claimed automatically; interpret budget curves together with measured CPU, RAM, and time.

## Results

| Condition | Benchmark | n | Base pass rate | Plus pass rate | Escalations |
|---|---:|---:|---:|---:|---:|
| adaptive | humaneval | 164 | 0.2622 | 0.2622 | 255 |
| adaptive | mbpp | 378 | 0.8492 | 0.7619 | 295 |
| adaptive | overall | 542 | 0.6716 | 0.6107 | 550 |
| small_only | humaneval | 164 | 0.1707 | 0.1585 | 0 |
| small_only | mbpp | 378 | 0.5899 | 0.5132 | 0 |
| small_only | overall | 542 | 0.4631 | 0.4059 | 0 |
| strong_only | humaneval | 164 | 0.2073 | 0.2073 | 0 |
| strong_only | mbpp | 378 | 0.7989 | 0.6958 | 0 |
| strong_only | overall | 542 | 0.6199 | 0.5480 | 0 |

## Post-run telemetry reconciliation

1 attempt had token counters recovered from the checksum-bound benchmark-owned Ollama log. The raw SQLite and JSONL measurements remain unchanged; only derived token totals and cost proxies use the reconciled counters. The original attempt status and verification outcome were not changed.

Raw token coverage: 2175/2176 attempts. Reconciled derived coverage: 2176/2176 attempts. Wall time, model-load time, inference time, generated code, and correctness were not reconstructed for the affected attempt.

## Interpretation limits

The saved paired task-level data supports later statistical analysis. This deterministic report does not fabricate significance tests. A negative or null result is retained.
