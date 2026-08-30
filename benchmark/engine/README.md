# Adaptive Workflow Local Routing Benchmark Source

This directory is the sanitized, reproducible source snapshot for the local-only Adaptive
Workflow routing benchmark. It excludes model weights, virtual environments, caches, private raw
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
