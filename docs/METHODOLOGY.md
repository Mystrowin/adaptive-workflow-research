# Methodology

## Scope

The experiment evaluates a local-only Adaptive Workflow benchmark. It uses
164 HumanEval+ tasks and 378 MBPP+ tasks, for 542 unique tasks. Base and Plus
scores are two verification views of the same generated completion, not
1,084 independent observations.

## Conditions

* small_only: one FAST local tier for every task.
* strong_only: one BEST local tier for every task.
* adaptive: initial route followed by at most one verified attempt per tier,
  in the historical order FAST -> BALANCED -> BEST after a deterministic
  failure. There are no same-tier retries.

The historical router was online-adaptive: routing statistics were updated as
the sequence progressed. The audit reconstructs the chronological replay and
does not treat the run as a frozen held-out router evaluation.

## Verification

Generated Python was evaluated with the pinned EvalPlus Docker image, with
network disabled, a read-only root, dropped capabilities, an unprivileged user,
task-scoped temporary storage, a PID cap, a timeout, and one verifier worker.
Deterministic test execution is authoritative. Six MBPP tasks produced shared
verifier/infrastructure failures in all three conditions; the primary result
keeps those cells in the denominator.

## Expenditure accounting

For a tier with frozen parameter value P in billions:

* generation_cost_proxy = P * output_tokens
* total_token_cost_proxy = P * (input_tokens + output_tokens)

These are model-size-weighted token proxies. They are not measured FLOPs,
hardware compute, energy, API usage, credits, or dollar cost. Physical evidence
is reported separately through CPU time/utilization, wall time, RAM, model-load
time, inference time, and verification time.

The frozen total-token baseline was B0 = 4,818,407.6; cutoffs were
25%, 50%, 75%, and 100% of B0. Every completed condition exhausted its
task list before the first cutoff, so the frozen curves are nondiscriminating.
The audit includes condition-relative cumulative curves as post-hoc diagnostics,
not as equal-budget evidence.

## Provenance

The frozen manifest records benchmark commits/versions, licenses, model names,
digests, sampling settings, resource limits, seed, task IDs, and source hash.
The private raw hashes are recorded in results/audit.json; private raw
prompts and generated programs are not included in this repository.
