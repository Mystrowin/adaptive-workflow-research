# Skeptical review audit

This document records an adversarial, publication-stage review of the
manuscript against the immutable audit and sanitized result export.

| Reviewer objection | Valid? | Manuscript/repository change | Remaining unresolved limitation |
| --- | --- | --- | --- |
| The 331 versus 297 comparison could be presented as universal superiority. | Yes | Abstract, Results, Analysis, and Conclusion now use bounded operating-point language and explicitly state that no universal advantage is established. | Generalization requires new tasks, seeds, and hardware. |
| Weighted tokens could be mistaken for FLOPs or generic compute. | Yes | Every use is labeled a model-size-weighted token cost proxy; raw tokens and physical measurements are reported separately. | Parameter-weighted tokens remain an approximate accounting device. |
| Prompt/prefill work might be omitted. | Yes | Input, output, and total tokens are reported; the total proxy includes input tokens. | One reconciled attempt lacks original timing/status fields even though token totals were recovered. |
| Adaptive receives up to three attempts while Strong-only receives one. | Yes | Operational final pass rate is separated from expenditure discussion; equal-budget curves and their failure are described. | The frozen historical curve is nondiscriminating because actual spending is below the first cutoff. |
| BALANCED outcomes are selected after failures and are not a baseline. | Yes | Conditional tier rows are explicitly labeled observed conditional outcomes; no standalone Balanced claim is made. | A future Balanced-only and fixed-cascade ablation is required. |
| Initial routing may be overinterpreted as intelligent prediction. | Yes | The paper reports FAST 531, BALANCED 0, BEST 11 and calls evidence for initial predictive routing weak. | The historical online state was reconstructed rather than persisted at every decision. |
| The cascade might be described as failure-feedback repair. | Yes | Architecture and related-work sections state that later tiers received the original prompt and no failed output or verifier feedback. | Feedback-aware escalation remains future work. |
| Six verifier failures could be hidden by excluding them. | Yes | The primary denominator retains all 542 tasks; 536-task values are clearly post-hoc diagnostics. | The shared infrastructure defect was not repaired and rerun for the historical study. |
| McNemar significance could replace practical effect size. | Yes | The test is labeled post-hoc and paired risk difference and counts are reported alongside it. | No preregistered statistical analysis exists for this historical run. |
| Public benchmark contamination could invalidate absolute scores. | Yes | HumanEval/MBPP age and plausible contamination are listed as threats; no general-intelligence claim is made. | Newer/private task sets are needed. |
| External leaderboard rankings could create unfair comparisons. | Yes | No GPT/Claude/Gemini ranking is reproduced; only method-level related work is cited. | Independent same-protocol comparisons remain future work. |
| Historical outputs cannot be independently re-executed. | Yes | The output-retention limitation is stated in the method text, limitations, conclusion, and reproducibility guide. | Exact old generated programs were not retained. |
| Citation metadata might be corrupted or fabricated. | Yes | Twelve references are checked by analysis/validate_references.py against primary-source URLs/DOIs and a validation report is included. | URLs should be rechecked if a future release changes versions. |
| The paper could imply the study is an EHMN benchmark. | Yes | The title, abstract, README, and methodology identify it as an Adaptive Workflow study and explicitly distinguish it from EHMN. | The related conceptual paper is not analyzed as an experimental baseline. |
| Privacy review might miss private paths or credentials. | Yes | The public bundle is allowlisted, the source snapshot omits private state, and analysis/run_checks.py records zero matches. | Users must review licenses and any later additions before release. |

## Review conclusion

The valid objections are addressed in the manuscript and the reproducibility
bundle. The remaining issues are empirical limitations that cannot be fixed
without a new preregistered benchmark run. No historical records were modified
to address the review.
