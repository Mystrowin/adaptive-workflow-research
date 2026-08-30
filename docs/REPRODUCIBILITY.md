# Reproducibility

## Analysis-only reproduction

Use Python 3.11 or newer from the repository root:

~~~powershell
python -m pip install -r analysis/requirements.txt
python analysis/make_publication_artifacts.py
python analysis/validate_references.py
python analysis/build_paper_pdf.py
python analysis/run_checks.py
~~~

These commands read only results/audit.json, results/summary.json,
results/experiment_manifest.json, and other allowlisted result files. They
regenerate all paper tables, six figures, and the checked-in PDF without model
inference. The PDF builder uses a native TeX engine when one is already
available and otherwise creates the documented ReportLab fallback; it does not
install system software.

## Historical benchmark limitation

The completed run retained exact task prompts privately, verifier output, model
metadata, and raw response metadata, but not exact generated programs or their
hashes. Consequently, a third party can reproduce the calculations and audit,
but cannot independently rerun the old generated programs from this public
bundle. The exact raw JSONL and SQLite artifacts remain private and are
represented by their SHA-256 hashes.

## Future benchmark reproduction

The publication-safe source snapshot under benchmark/engine/ contains the
benchmark-local CLI and its documentation. A future experiment must be
prepared with local datasets and models, must freeze a new manifest, and must
preserve exact output hashes in a private experiment directory. It must not
reuse or overwrite the historical experiment identifier.

Preparation is the only network-enabled phase. Detached execution must use
loopback-only local inference and fail closed if a cloud provider is selected.
Docker Desktop and Ollama are system prerequisites; the benchmark never
silently installs them.

## Checksums

results/checksums.txt covers the sanitized result export. The source snapshot
contains its own safety notes. Do not publish private raw directories, model
weights, prompts, generated code, logs, credentials, or local home-directory
paths.
