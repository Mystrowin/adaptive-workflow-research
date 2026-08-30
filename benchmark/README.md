# Benchmark source and provenance

engine/ is a publication-safe snapshot of the benchmark-local Adaptive
Workflow subsystem. It is intentionally not the whole private application.
The snapshot includes the local-only adapter, router, verifier integration,
resource accounting, lifecycle, audit, reporting, and export code needed to
understand the protocol.

The historical run used:

* HumanEval commit 6d43fb980f9fee3c892a914eda09951f772ad10d (MIT repository
  license).
* MBPP commit f46ca8374b4cddef97ca4208ad986049d74d296a (CC BY 4.0 dataset
  attribution; Apache-2.0 repository source).
* EvalPlus v0.3.1 (Apache-2.0).
* HumanEval+ v0.1.10 and MBPP+ v0.2.0 (Apache-2.0 with upstream
  obligations retained).

The exact source URLs, artifact hashes, retrieval timestamp, and license-file
hashes are in results/benchmark_sources.json. Required notices are in
licenses/.

The public snapshot does not include benchmark datasets, prompts, tests,
generated answers, model weights, private databases, or credentials. A fresh
benchmark preparation must obtain approved artifacts separately and freeze a
new experiment manifest.
