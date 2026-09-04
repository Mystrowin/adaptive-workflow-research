# Adaptive Workflow Local Routing Benchmark Source

This directory is the sanitized current benchmark harness for future local-only Adaptive
Workflow studies. It contains post-run improvements and is not byte-identical to the August 2026
historical source tree, whose preserved SHA-256 is documented in the repository provenance file.
It excludes model weights, virtual environments, caches, private raw
results, credentials, browser data, and benchmark prompt/test assets.

Install Python 3.11+, Ollama, and Docker Desktop separately. Docker Desktop is never installed by
this project. From this directory:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

The benchmark defaults to same-family Qwen2.5-Coder 1.5B, 3B, and 7B local tiers. Preparation is
the only network-enabled phase; detached execution is loopback-only, local, and has no cloud
fallback.

In the historical study, the finite EvalPlus Plus result both controlled Adaptive escalation and
served as the endpoint. That oracle-gated, multi-attempt cascade does not establish independent-
verifier or predictive-routing superiority. Future runs should add held-out verification and
attempt-matched baselines when those claims are the target.

```powershell
.\.venv\Scripts\python.exe -m agents.adaptive_workflow benchmark prepare
.\.venv\Scripts\python.exe -m agents.adaptive_workflow benchmark run --detached
.\.venv\Scripts\python.exe -m agents.adaptive_workflow benchmark status <experiment_id>
.\.venv\Scripts\python.exe -m agents.adaptive_workflow benchmark results <experiment_id>
.\.venv\Scripts\python.exe -m agents.adaptive_workflow benchmark audit <experiment_id> --output-dir <audit_directory>
.\.venv\Scripts\python.exe -m agents.adaptive_workflow benchmark export-publishable --experiment <experiment_id>
```

`benchmark audit` is a read-only post-hoc analysis. The sibling research `audit/` directory
contains the completed-study JSON and Markdown audit; it does not modify historical raw data.
Review all benchmark licenses and every exported file before public release.
