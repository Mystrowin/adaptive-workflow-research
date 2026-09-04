# Adaptive Workflow Research

This repository contains the corrected v1.1 paper, deterministic analysis,
sanitized results, provenance, and audit for a fixed-workload oracle-gated
model-cascade study. It evaluates Adaptive Workflow; it is not an EHMN
benchmark.

The historical Adaptive condition used the same EvalPlus Plus outcome to
accept or escalate a candidate and to define the primary endpoint. It therefore
measures model-tier complementarity under oracle test gating, not performance
of an independent deployment verifier.

## Primary result

| Condition | EvalPlus Plus test passes | Pass rate |
| --- | ---: | ---: |
| Adaptive | 331 / 542 | 61.07% |
| Strong-only | 297 / 542 | 54.80% |
| Small-only | 220 / 542 | 40.59% |

Adaptive retained 34 passes not present in Strong-only (+6.27 percentage
points; +11.45% successful tasks on this fixed workload). FAST produced 22 and
BALANCED 12; BEST produced none. Adaptive could retain earlier-tier passes and
later fall back to the same BEST tier as Strong-only, and it received more
oracle-checked attempts. The experiment does not isolate predictive routing,
independent verification, equal-budget performance, or universal efficiency.

## Historical mechanism

The cascade generated one candidate per tier in the order FAST -> BALANCED ->
BEST after Plus-test failure. Later tiers received the original frozen prompt,
not failed code or verifier feedback. Initial routes were FAST 531, BALANCED 0,
and BEST 11. The router used hand-written task features plus online statistics;
its confidence value was fixed rather than calibrated. Earlier EvalPlus labels
could influence later decisions, so this was an online sequential evaluation,
not a held-out frozen-router evaluation.

## Reproduce the publication analysis

These commands do not rerun the benchmark or contact a model provider:

~~~powershell
python -m pip install -r analysis/requirements.txt
python analysis/make_publication_artifacts.py
python analysis/validate_references.py
python analysis/run_checks.py --mode release-integrity
~~~

The reviewed publication PDF is a static artifact. The repository publishes
the experiment-replication material, not a public manuscript-building tool.

Publication analysis has two reproducibility boundaries. Generated tables and
JSON use deterministic UTF-8/LF output. Pillow figures are rendered and checked
in temporary staging by default because font rasterization is not portable
byte-for-byte; the checked-in PNGs are exact release artifacts. Use
`run_checks.py --mode release-integrity` to verify those exact bytes, or
`--mode calculation-reproduction` when validating calculations on another
platform without claiming PNG-byte identity.

The historical run did not retain exact generated programs or their hashes, so
the release is calculation-reproducible but not exact-output-reproducible. The
current public harness includes post-run audit and future-reproducibility
improvements and is not byte-identical to the historical source identified by
the preserved SHA-256.

## Repository map

- `paper/`: reviewed PDF, references, figures, and tables.
- `results/`: allowlisted sanitized export and read-only scientific audit.
- `analysis/`: deterministic publication and integrity checks.
- `benchmark/`: publication-safe current harness; not the exact historical tree.
- `docs/`: methodology, reproducibility, limitations, privacy, and provenance.
- `licenses/`: project, paper, benchmark, OpenAI, and Qwen notices.

## Limitations

The experiment used one deterministic task order, seed, hardware configuration,
Qwen2.5-Coder family, and Q4_K_M quantization. Balanced-only, fixed-cascade,
repeated-BEST, repeated-FAST, and budget-matched alternatives were not run.
HumanEval/MBPP are old public function-synthesis benchmarks with plausible
contamination. EvalPlus is a finite test instrument, not proof of semantic
correctness. See `docs/LIMITATIONS.md` and the paper.

## Citation and release state

See `CITATION.cff`. v1.1.0-research is published in this public GitHub
repository; no DOI or venue is claimed. The historical v1.0.0-research tag remains unchanged;
its tag-message checksum errors are documented in `docs/PROVENANCE.md`.

## License

Original project software is MIT. OpenAI-derived portions retain OpenAI's 2025
MIT notice. Paper text and original figures/tables are CC BY 4.0. HumanEval,
MBPP, EvalPlus, Plus derivatives, Qwen model artifacts, and all other
third-party materials retain their upstream terms and are not relicensed by
this repository. See `licenses/README.md`.
