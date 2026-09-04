# Adaptive Workflow local routing benchmark

The benchmark subsystem supports local studies of verification-gated model cascading and routing.
It is an Adaptive Workflow benchmark, not an EHMN benchmark. The August 2026 study used the same
finite EvalPlus Plus result as Adaptive's acceptance/escalation oracle and reported endpoint; it
therefore does not establish independent-verifier effectiveness. Adaptive also received up to
three attempts while static conditions received one, so operational pass rates are not by
themselves equal-attempt or equal-budget evidence.

Normal Adaptive Workflow execution is unchanged. Benchmark state, models, prompts, and results use
a separate private directory and SQLite database. The detached worker accepts only a dedicated
loopback Ollama server and a pinned local Docker verifier. It strips cloud credentials and proxy
settings, never constructs a Codex/OpenAI provider, and does not download anything after
preparation.

## Prerequisites

Install and start Ollama and Docker Desktop separately. Preparation detects missing system
software and returns an actionable error; it never installs Docker Desktop or another privileged
system application. Install the ordinary benchmark Python dependencies with
`pip install -e .` from the engine directory.

The default same-family tiers are Qwen2.5-Coder 1.5B, 3B, and 7B. Preparation refuses to freeze the
study unless all three distinct models and the EvalPlus image fit the configured resource limits.
It downloads the pinned public benchmark artifacts, saves their licenses and SHA-256 hashes,
counts prompt tokens locally, and freezes the 542-task schedule and numeric budget.

## Commands

```powershell
python -m agents.adaptive_workflow benchmark prepare
python -m agents.adaptive_workflow benchmark run --detached
python -m agents.adaptive_workflow benchmark status <experiment_id>
python -m agents.adaptive_workflow benchmark results <experiment_id>
python -m agents.adaptive_workflow benchmark stop <experiment_id>
python -m agents.adaptive_workflow benchmark resume <experiment_id>
python -m agents.adaptive_workflow benchmark export-publishable --experiment <experiment_id>
python -m agents.adaptive_workflow benchmark audit <experiment_id> --output-dir <audit_directory>
```

Use `--private-root` and `--publishable-root` immediately after `benchmark` to override the two
roots. They must remain separate. The GUI's Benchmarks tab is intentionally read-only; benchmark
lifecycle operations remain CLI/backend responsibilities.

`benchmark audit` is read-only: it opens the completed SQLite database in read-only mode and
writes machine-readable `audit.json` plus human-readable `AUDIT.md` outside the experiment. It
does not rewrite raw results, manifests, reports, or publishable exports.

## Methodology

The conditions are Small-only, Strong-only, and Adaptive. Adaptive performs at most one verified
attempt per tier and may follow `FAST -> BALANCED -> BEST`; it does not retry a failed tier.
HumanEval+ and MBPP+ base and Plus scores are calculated from the same completion, so 542
completions per condition do not become 1,084 independent observations.

Every attempt records input, output, and total tokens when Ollama provides them. The report labels
`P * output_tokens` as a generation cost proxy and `P * total_tokens` as a total-token cost proxy,
where `P` is the frozen parameter value in billions. These are not measured FLOPs or hardware
compute. Primary fixed-budget curves use the predetermined 25%, 50%, 75%, and 100% cutoffs of the
Strong-only reserved total-token baseline. CPU, RAM, and time measurements are the physical
efficiency evidence.

The historical router used hand-written task features and online statistics, was overwhelmingly
FAST-first, and updated during the evaluation. FAST, BALANCED, and BEST observations are therefore
conditionally selected rather than standalone capability estimates. Later tiers receive the
original frozen prompt, not failed code or test feedback.

Windows Job Object controls cap the native benchmark process tree at 50% of system CPU capacity
and 50% of physical RAM, with 45% soft targets. Docker receives its own CPU, memory, PID, network,
filesystem, capability, and privilege restrictions. An observed hard-cap violation stops the
experiment and invalidates efficiency conclusions.

## Results and publication boundary

Private experiments contain prompts, generated code, raw JSONL, logs, and checkpoint SQLite state.
They are not publishable. Export creates a new versioned directory from an allowlist, removes raw
prompts/code/tests/private paths, copies required notices, scans for secrets and local paths,
generates checksums, and writes `publishable_safety_report.json`. It fails closed as
`publishable_export_blocked` if the experiment is incomplete or the projection cannot be proven
safe. Nothing is uploaded, committed, or published automatically; review all files and licenses
before release.

Future ablations can opt into `balanced_only` and `fixed_cascade` conditions. Router statistics are
explicitly `online` (updated during Adaptive evaluation) or `frozen` (a checksum-validated
calibration state required before held-out execution). Historical defaults remain Small-only,
Strong-only, and Adaptive.
