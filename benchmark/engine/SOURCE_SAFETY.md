# Source publication boundary

This directory is an allowlisted current reproduction harness. It contains post-run
improvements and is not byte-identical to the August 2026 historical source tree. It includes only the local
benchmark harness, its routing primitives, one focused test module, methodology, packaging
metadata, and the MIT license.

The export intentionally excludes personal paths and names, credentials, environment files,
private experiment databases, raw JSONL, logs, prompts, generated solutions, benchmark datasets,
model files, virtual environments, caches, GUI/provider integrations, internal planning files,
and unrelated SDK source or documentation.

Before the original sanitized export, the then-private project ran its 25-test
harness suite and compared representative routing decisions. This public
snapshot does not include that private historical test suite. The v1.1
publication checks compile and inspect this current harness, test the
publication analysis, and scan the public tree for paths and credential-shaped
values. Review the bundle and upstream licenses again before publication.
