# Limitations and threats to validity

1. The result is one deterministic run on one Windows machine and one hardware
   configuration.
2. HumanEval and MBPP are old public benchmarks; training-set contamination is
   plausible.
3. The run used one same-family Qwen2.5-Coder tier set. Results may not transfer
   to other model families, quantizations, runtimes, or hardware.
4. BALANCED and later BEST attempts were conditional on earlier deterministic
   failures. Their observed overlap is not a full 542-task standalone baseline.
5. There was no historical Balanced-only condition and no fixed-cascade ablation.
6. The router updated statistics online. It was not evaluated as a frozen router
   on an untouched held-out set.
7. The historical run did not retain exact generated programs or output hashes,
   preventing exact output-level re-evaluation.
8. Six MBPP verifier/infrastructure failures were shared across conditions.
   They remain in the primary denominator; excluding them is post-hoc only.
9. The frozen equal-budget cutoffs were above every condition's actual
   expenditure, so the stored budget curves do not discriminate conditions.
10. Token proxies multiply parameter count by token counts. Parameter count does
    not equal measured FLOPs, and the proxies do not represent energy, API
    price, or generic resource consumption.
11. CPU, wall time, RAM, and model-load measurements are machine-specific and
    should not be generalized as universal costs.
12. A single deterministic completion per task does not estimate pass@k or
    stochastic variability.
13. The task set measures function-level Python synthesis, not repository-scale
    software engineering or general intelligence.
