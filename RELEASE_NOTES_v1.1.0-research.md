# Adaptive Workflow Research v1.1.0-research

This is a scientific and provenance correction to the public research bundle.
It is not a new benchmark run.

The corrected paper frames the historical Adaptive condition as an oracle-gated
complementarity study because the same EvalPlus Plus result controlled
acceptance/escalation and final scoring. It discloses the asymmetric attempt
structure, online selection bias, more-attempts confound, finite-test limits,
and metric-specific resource trade-offs. It makes no independent-verifier,
predictive-routing, equal-budget, or universal-efficiency superiority claim.

Historical results remain 331/542 Adaptive, 297/542 Strong-only, and 220/542
Small-only. Historical raw JSONL, SQLite, and source hashes remain unchanged.
No model inference or EvalPlus benchmark was rerun.

The v1.0.0-research tag is not rewritten. Its malformed truncated SQLite SHA
and stale publication-bundle SHA are documented in `docs/PROVENANCE.md`.
The v1.0 bundle procedure was platform-dependent: a POSIX/archive
reconstruction reproduces
`a82a61232f7d112405cd7d7f5f78239cd4e9020411363f354c7f4c40c69c6d03`, while
a Windows/CRLF reconstruction reproduces
`227f4891d8d5351cb066da12c8fcd8df41c4a78b95f28dae3d1895ac00510008`. These
are not a single portable canonical hash for the unchanged historical tag.

The final publication checks use an explicit relative POSIX-path ordering and
emit a complete excluded hash manifest, avoiding platform-dependent path
ordering. Sanitized task-level evidence for the six shared MBPP verifier
failures is included with direct-versus-inferred confidence labels. The paper
uses "paired pass-rate difference," cites the final ICLR 2025 Snell et al.
publication, and distributes the reviewed article as a static PDF.

The v1.1.0-research bundle is published in the public GitHub repository after
final user approval. No DOI or venue is claimed.
