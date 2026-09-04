# Methodology

## Scope and conditions

The fixed workload contains 164 HumanEval+ and 378 MBPP+ tasks. Base and Plus
are two test views of the same completion, not 1,084 independent observations.

- `small_only`: one FAST attempt.
- `strong_only`: one BEST attempt.
- `adaptive`: one attempt per reached tier, FAST -> BALANCED -> BEST.

No historical Balanced-only, fixed-cascade, repeated-BEST, repeated-FAST, or
budget-matched repeated-sampling baseline was run.

## Oracle gate and structural asymmetry

The same pinned EvalPlus Plus outcome controlled Adaptive acceptance/escalation
and defined the primary endpoint. This is evaluator leakage by design and makes
the experiment an oracle-gated complementarity study, not evidence for an
independent verifier. Adaptive could retain an earlier-tier pass and later fall
back to the same BEST tier used once by Strong-only. The design also gives
Adaptive more oracle-checked attempts, so it does not isolate complementarity
from a general more-attempts effect.

Later tiers always received the original frozen task prompt. They did not
receive failed code, failure details, or evaluator feedback.

## Routing

The historical router used hand-written task features plus online
RoutingStatistics. It started 531 tasks at FAST, none at BALANCED, and 11 at
BEST. Its confidence field was a fixed implementation value, not a calibrated
probability. Statistics were updated using earlier EvalPlus outcomes, so this
was an online sequential evaluation rather than a held-out frozen-router test.
FAST, BALANCED, and BEST saw progressively selected task subsets; their
conditional success rates are not standalone capability estimates.

## Evaluation

Generated Python ran in the pinned EvalPlus Docker image with network disabled,
a read-only root, dropped capabilities, an unprivileged user, task-scoped
storage, PID/memory limits, timeout, and one worker. An EvalPlus Plus pass means
passing the pinned finite suite, not proof of semantic correctness. Oracle or
test-contract defects can cause false acceptance or rejection.

Six MBPP tasks produced condition-independent infrastructure errors and remain
in the primary denominator. Preserved errors directly establish the failure
symptoms; static evidence strongly indicates task-specific adapter,
deserialization, and cache-capacity causes; see `docs/PROVENANCE.md`.

## Expenditure accounting

For frozen parameter accounting value P in billions:

- `generation_cost_proxy = P * output_tokens`
- `total_token_cost_proxy = P * (input_tokens + output_tokens)`

These are model-size-weighted token accounting proxies, not FLOPs, hardware
work, energy, API usage, API credits, dollar cost, or generic resource
consumption. CPU-seconds are sample-integrated estimates from periodic CPU
samples. Wall seconds are summed generation-and-verification time, not total
experiment elapsed time.

The frozen B0 budget cutoffs were nondiscriminating because every condition
completed below the first cutoff. The successes-per-weighted-proxy ratio is a
post-hoc secondary diagnostic, not equal-budget evidence.

## Historical retention

Historical records retain task identity, tier/model metadata, tokens,
verification status, telemetry, manifests, and hashes. Exact historical
generated programs and their hashes were never retained, so output-level
re-evaluation is impossible. The current harness stores more evidence for
future runs and is not byte-identical to the historical source.
