# Adaptive Workflow scientific-validity audit

Experiment: `awb-20260826T042018Z-s20260824-300eaad5`

This is a read-only post-hoc audit. The completed benchmark records and the historical 331/542 result were not modified.

## Integrity

- Tasks: 542; cells: 1626; raw attempts: 2176; derived attempts: 2176
- Duplicate attempt keys: 0; all cells completed: True
- Condition task orders identical: True
- Expected cells from the frozen manifest: 1626; historical three-condition expectation: 1626
- Historical frozen source hash: `0d24437e9297466c3f28a7af677a76d7e54c10dc6358edb7b724d586040e7859`; current source hash differs because audit tooling is newer: `1cec3afa76d22414d5c8db9339649b2cc0fd9138bc8385143663a2aed62471c7`

## Finding dispositions

| Finding | Disposition | Evidence |
|---:|---|---|
| 1 | CONFIRMED | worker._run_cells reuses the frozen BenchmarkTask; ollama.build_generation_prompt adds no prior output or verifier feedback. |
| 2 | PARTIALLY CONFIRMED | deterministic_equivalence finds zero observable metadata/outcome/token mismatches on 531 FAST/Small and 251 BEST/Strong overlaps; exact generated text was not historically persisted. |
| 3 | CONFIRMED | complementarity computes paired task-level matrices and the 34 Adaptive-only successes (22 FAST, 12 BALANCED, 0 BEST). |
| 4 | PARTIALLY CONFIRMED | initial routes are 531 FAST, 0 BALANCED, 11 BEST; online history also causes eight empty-state replay differences, so routing is not wholly static. |
| 5 | CONFIRMED | the immutable schedule contains only small_only, strong_only, and adaptive; BALANCED_ONLY is future-supported but has no retrospective score. |
| 6 | CONFIRMED | worker updates RoutingStatistics after Adaptive attempts; task order and online/frozen router-state persistence are now explicit for future runs. |
| 7 | CONFIRMED | failure_audit finds the six listed MBPP IDs in all three conditions (18 verifier-error attempts total). |
| 8 | CONFIRMED | historical raw attempts contain metadata but no generated program/output; future AttemptRecord stores private output plus hashes while public_task_result strips output. |
| 9 | CONFIRMED | reporting and audit label weighted token values as model-size-weighted token proxies and keep raw/system/resource metrics separate. |
| 10 | CONFIRMED | expenditure_audit recomputes the full Adaptive-versus-Strong tradeoff table and per-metric useful-work efficiencies. |
| 11 | CONFIRMED | no API pricing or dollar-cost inference is made; parameter count is never converted to commercial usage. |
| 12 | CONFIRMED | budget_audit verifies the first frozen cutoff exceeds each condition's actual total; post-hoc curves are labeled condition-relative and post-hoc. |
| 13 | CONFIRMED | condition_summary reports HumanEval+, MBPP+, task-weighted aggregate, and equal-benchmark macro average as distinct fields. |
| 14 | CONFIRMED | reports contain no external leaderboard superiority claim; controlled within-run comparisons are the only comparisons emitted. |
| 15 | CONFIRMED | manifest and generation_protocol record temperature 0, fixed seed, and one attempt per tier; limitations state that variance is unmeasured. |
| 16 | CONFIRMED | audit limitations flag plausible HumanEval/MBPP training contamination and avoid general-intelligence claims. |
| 17 | CONFIRMED | paired_statistics reports b=34, c=0, both-pass=297, both-fail=211 and labels exact McNemar as post-hoc. |
| 18 | CONFIRMED | benchmark audit writes separate audit.json and AUDIT.md through read-only SQLite access and reports historical_records_modified=false. |
| 19 | CONFIRMED | config/router/preparation/worker support Small, Balanced, Strong, fixed cascade, and Adaptive conditions; tests smoke the future modes without running the full ablation. |

## Task-weighted results (base and Plus share each completion)

| Condition | HumanEval+ | MBPP+ | Task-weighted | Equal-benchmark macro average |
|---|---:|---:|---:|---:|
| small_only | 26/164 (15.85%) | 194/378 (51.32%) | 220/542 (40.59%) | 33.59% |
| strong_only | 34/164 (20.73%) | 263/378 (69.58%) | 297/542 (54.80%) | 45.15% |
| adaptive | 43/164 (26.22%) | 288/378 (76.19%) | 331/542 (61.07%) | 51.20% |

## Verified equivalence and complementarity

Adaptive FAST vs Small-only: 531 common attempts, 0 observable mismatches.
Adaptive BEST vs Strong-only: 251 common attempts, 0 observable mismatches.
Adaptive-only Plus passes vs Strong-only: 34 (FAST 22, BALANCED 12, BEST 0).
Adaptive successful tasks avoiding BEST: 285/331 (86.10%).

## Routing and failures

Initial Adaptive tiers: {'FAST': 531, 'BEST': 11}; decisions differing from FAST-first: 11.
Reconstructed online router rows: 1091; recorded-vs-online replay mismatches: 0.
Common verifier-infrastructure tasks: 6; total verifier-error attempts: 18.
Post-hoc diagnostic excluding shared verifier failures: {'small_only': {'task_weighted': {'n': 536, 'passes': 220, 'rate': 0.41044776119402987}, 'by_benchmark': {'humaneval': {'n': 164, 'passes': 26, 'rate': 0.15853658536585366}, 'mbpp': {'n': 372, 'passes': 194, 'rate': 0.521505376344086}}, 'equal_benchmark_macro_average': 0.34002098085496985}, 'strong_only': {'task_weighted': {'n': 536, 'passes': 297, 'rate': 0.5541044776119403}, 'by_benchmark': {'humaneval': {'n': 164, 'passes': 34, 'rate': 0.2073170731707317}, 'mbpp': {'n': 372, 'passes': 263, 'rate': 0.706989247311828}}, 'equal_benchmark_macro_average': 0.45715316024127983}, 'adaptive': {'task_weighted': {'n': 536, 'passes': 331, 'rate': 0.6175373134328358}, 'by_benchmark': {'humaneval': {'n': 164, 'passes': 43, 'rate': 0.2621951219512195}, 'mbpp': {'n': 372, 'passes': 288, 'rate': 0.7741935483870968}}, 'equal_benchmark_macro_average': 0.5181943351691581}}.

## Expenditure terminology

All weighted token values below are model-size-weighted token proxies, not FLOPs, hardware compute, energy, API usage, credits, or dollar cost.

| Metric | Adaptive | Strong-only | Difference |
|---|---:|---:|---:|
| Plus successes | 331 | 297 | 34 |
| Raw input tokens | 166716 | 78993 | 87723 |
| Raw output tokens | 93006 | 38507 | 54499 |
| Raw total tokens | 259722 | 117500 | 142222 |
| Weighted input proxy | 579460.7 | 600346.8 | -20886.1 |
| Weighted output proxy | 320002.1 | 292653.2 | 27348.9 |
| Weighted total proxy | 899462.8 | 893000.0 | 6462.8 |
| CPU time (seconds) | 38137.61 | 33421.46 | 4716.15 |
| Wall time (seconds) | 78701.93 | 47582.32 | 31119.61 |
| Peak CPU (%) | 47.1225 | 46.8875 | 0.2350 |
| Peak RAM (bytes) | 6897147346 | 6999388192 | -102240846 |
| Model calls | 1092 | 542 | 550 |
| Verifier calls | 1091 | 542 | 549 |

Adaptive vs Strong-only weighted total-token proxy: 6462.8 (0.72%); raw total tokens: 142222 (121.04%); CPU time: 4716.15s (14.11%); wall time: 31119.61s (65.40%).
Frozen budget warning: The frozen 25/50/75/100% B0 cutoffs are nondiscriminating for this completed run: the first cutoff is at or above every condition's actual expenditure.
Post-hoc empirical cumulative curves are condition-relative and are not equal-budget evidence.

## Statistical note

Adaptive vs Strong-only exact two-sided McNemar test is post-hoc: b=34, c=0, p=1.16415321827e-10. This was not preregistered.

## Limitations

The run used one deterministic completion per tier and fixed seed; it does not measure sampling, seed, or prompt robustness. HumanEval/MBPP contamination is plausible. Exact generated programs were not persisted, so they cannot be independently re-evaluated. BALANCED and adaptive BEST outcomes are observed only after earlier-tier failures. The frozen budget curve is nondiscriminating because its first cutoff exceeds every method's actual expenditure. No external leaderboard or commercial API-cost claim is supported.
