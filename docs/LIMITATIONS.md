# Limitations and threats to validity

1. The same EvalPlus Plus result controlled escalation and final scoring. The
   experiment is oracle-gated and does not establish independent-verifier
   effectiveness.
2. Adaptive could retain earlier-tier passes and fall back to BEST, while
   Strong-only received one BEST attempt. Zero Strong-only-only passes is
   structurally unsurprising under deterministic-equivalent common attempts.
3. The more-attempts confound is unresolved. Balanced-only, fixed cascade,
   repeated-BEST, repeated-FAST, and budget-matched alternatives were not run.
4. The router used hand-written features, online statistics, and a fixed
   confidence value. It was overwhelmingly FAST-first, not a trained predictive
   router.
5. Online updates used earlier EvalPlus labels. One task order was tested, and
   later routing can be order-sensitive.
6. FAST saw nearly all tasks; BALANCED and BEST saw selected harder residuals.
   Conditional tier rates are not standalone capability estimates.
7. Later tiers received the original prompt only. No feedback-guided repair was
   evaluated.
8. EvalPlus is a finite measurement instrument, not proof of semantic
   correctness. Oracle/test defects may cause false rejection or acceptance.
9. Six shared MBPP failures remain in the 542-task denominator. Their preserved
   evidence is documented, but the historical run was not rerun after fixes.
10. Exact historical generated programs and output hashes were not retained,
    preventing output-level re-evaluation.
11. HumanEval and MBPP are old public benchmarks; contamination is plausible.
    They do not measure repository-scale engineering or general modern coding
    ability. LiveCodeBench and BigCodeBench are future contexts, not results.
12. One model family, Q4_K_M quantization family, hardware configuration,
    runtime configuration, seed, deterministic sampling setting, and task order
    were tested. No multi-seed robustness study was run.
13. Model-size-weighted token proxies are not FLOPs, energy, API cost, or
    hardware work. The +10.65% successes-per-proxy value is post-hoc and
    secondary.
14. CPU-seconds are sample-integrated estimates and can miss sub-sample spikes.
    Wall time is summed generation-and-verification time, not end-to-end elapsed
    experiment time.
15. The frozen equal-budget cutoffs are nondiscriminating and provide no
    equal-budget evidence.
16. The current public harness contains post-run improvements and is not
    byte-identical to the historical source identified by the preserved hash.
