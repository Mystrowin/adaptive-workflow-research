# Adaptive Workflow Research

This repository contains the paper, analysis code, sanitized results, provenance,
and a review audit for a local experiment on verification-gated model cascading
for code generation. It studies Adaptive Workflow; it is not an EHMN benchmark.

## Key result

On the task-weighted EvalPlus Plus result for the same 542 tasks:

| Condition | Verified Plus successes | Pass rate |
| --- | ---: | ---: |
| Adaptive | 331 / 542 | 61.07% |
| Strong-only | 297 / 542 | 54.80% |
| Small-only | 220 / 542 | 40.59% |

Adaptive therefore has 34 more verified Plus successes than Strong-only
(+6.27 percentage points; +11.45% relative successes). This is an observation
from one completed run, not a claim of universal superiority.

## What the system does

The historical system starts with a local model tier, generates one candidate,
and runs a deterministic verifier. A failed verification permits escalation to
the next local tier. Later tiers receive the original frozen task prompt; the
historical run did not pass generated code or verifier feedback into later
generations.

## Reproduce the published analysis

The commands below operate only on the sanitized artifacts in results/; they
do not rerun the benchmark or contact a model provider.

~~~powershell
python -m pip install -r analysis/requirements.txt
python analysis/make_publication_artifacts.py
python analysis/validate_references.py
python analysis/build_paper_pdf.py
python analysis/run_checks.py
~~~

The first command deterministically regenerates publication tables, figures,
and a numerical claim check. The second validates the bibliographic records
included in paper/references.bib. The third builds the checked-in PDF. The
fourth checks hashes, privacy, and the generated outputs. It uses the native
LaTeX path when a LaTeX engine is available and otherwise creates a
deterministic ReportLab fallback while preserving the complete LaTeX source
for a native rebuild.

The historical benchmark is not reproducible at output level because
the private run did not retain exact generated programs. The public repository
does retain the frozen configuration, task-level aggregate outcomes, audit
artifacts, source snapshot, and checksums. Future benchmark runs should use the
source snapshot and preserve private output hashes according to
benchmark/engine/docs/adaptive_workflow_benchmark.md.

## Repository map

* paper/ - LaTeX manuscript, references, figures, tables, PDF, and reviewer audit.
* results/ - allowlisted sanitized export and read-only scientific audit.
* analysis/ - deterministic table, figure, validation, and privacy scripts.
* benchmark/ - publication-safe benchmark harness source snapshot and provenance.
* docs/ - methodology, reproducibility, limitations, and security notes.
* licenses/ - project and upstream benchmark notices.

## Scientific audit

results/AUDIT.md and results/audit.json record the independent read-only
audit. It confirms that the raw JSONL and SQLite hashes are unchanged, that
the historical run completed all 1,626 condition-task cells, and that the
historical router was online-adaptive. The audit also documents conditional
tier selection, missing exact generated outputs, shared verifier failures,
and the budget-curve limitation.

## Limitations

This is a single deterministic run on one Windows machine, one same-family
model set, public benchmarks with plausible contamination, and an online
router. Balanced-only and fixed-cascade standalone baselines were not part of
the historical run. Model-size-weighted token values are explicitly labeled
cost proxies, not measured FLOPs, hardware compute, energy, API usage, or
dollar cost. See docs/LIMITATIONS.md and Section 7 of the paper.

## Citation

See CITATION.cff. The paper is a public GitHub-hosted preprint and has no DOI
or venue claim. Do not cite the result as a leaderboard comparison.

## License

Project code is MIT-licensed. Original Adaptive Workflow research and
benchmark-integration contributions are copyright (c) 2026 Neeraj Pragnya
Krishna Vasagiri. Code derived from the OpenAI Agents Python project retains
OpenAI's 2025 MIT copyright notice. The paper is provided for scholarly reuse;
the benchmark datasets and tools retain their upstream licenses in licenses/.
Those upstream notices are not relicensed by this repository.

This repository is publicly available on GitHub. The benchmark and export
tooling never automatically uploads, publishes, commits, or pushes artifacts;
review the contents and applicable licenses before creating a future release.
