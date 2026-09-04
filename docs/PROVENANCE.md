# Historical and release provenance

## Immutable historical benchmark facts

The August 2026 run used 542 tasks and produced 331 Adaptive, 297 Strong-only,
and 220 Small-only EvalPlus Plus test passes. No benchmark task, completion,
result, or historical measurement was changed for v1.1.

Preserved historical hashes:

- raw JSONL: `6926147073d0e5b3ffe93ecb3d9c8619707b24f0b48a843d25db6627602268da`
- SQLite: `138d04bc1c2f3b6609a56cc2a5e77a6d024035f22d948f81a674139ef06976e7`
- frozen source tree: `0d24437e9297466c3f28a7af677a76d7e54c10dc6358edb7b724d586040e7859`

The public repository begins after the historical run. No reachable or
unreachable Git object reconstructs the exact frozen tree matching the third
hash. The public `benchmark/engine/` tree contains post-run audit and
future-reproducibility improvements. It must not be described as byte-identical
historical source.

## Six shared MBPP infrastructure failures

Static inspection of preserved error records, the publication-safe harness,
and pinned EvalPlus source directly established the failure symptoms and
strongly indicates the following causes without rerunning the benchmark. The
sanitized evidence and confidence classification are in
`docs/MBPP_VERIFIER_FAILURE_ROOT_CAUSE.md`:

- `Mbpp/106`, `Mbpp/124`, `Mbpp/252`, `Mbpp/580`, and `Mbpp/720`: the
  preserved errors are consistent with raw MBPP+ JSON reaching ground-truth
  execution without EvalPlus's
  `get_mbpp_plus()` / `mbpp_deserialize_inputs` path. Canonical solutions then
  received serialized list/string forms incompatible with their expected
  inputs, producing repeatable type errors in all three conditions.
- `Mbpp/255`: the Plus input contains 1,663,740 tuples of length 77. Ground
  truth computation completed, and the evaluator's cache pickle write failed
  with `OSError: [Errno 28]`. The public harness documents a 512 MiB `/tmp`
  tmpfs, and the expanded tuple/list structure is approximately 1.10 GB before
  pickle overhead. Together these facts strongly indicate, but do not directly
  prove from the unavailable exact historical source, that tmpfs capacity was
  the binding limit.

All 18 condition-task records show the same task-specific errors. The failure
symptoms are direct evidence; the deserialization and 512 MiB binding-limit
causes are classified as strong inferences because the exact historical source
tree is unavailable. These remain in the 542-task primary denominator. The
historical experiment was not rerun.

## v1.0.0-research errata

The historical `v1.0.0-research` tag remains unchanged.

1. Its annotated message records malformed truncated SQLite text
   `138d04bc1c2f3b6609a56cc2a5e77e7`. The correct full SQLite SHA-256 is
   `138d04bc1c2f3b6609a56cc2a5e77a6d024035f22d948f81a674139ef06976e7`.
   The GitHub release body and research artifacts preserve the full value.
2. The tag records publication-bundle SHA-256
   `6eec2f7d16a48ee0c5d0efeb3699439307406e74a56d99fcada5953486afb860`.
   The tagged `analysis/run_checks.py` hashes every file under the tag root
   except five dynamic basenames (`publication_checks.json`,
   `privacy_scan.json`, `reference_validation.json`, `RELEASE_METADATA.json`,
   cache/VCS directories, and bytecode. It
   sorts discovered `Path` objects, then hashes lines of the form
   `<relative-posix-path>  <file-sha256>\n`. That procedure was not
   platform-independent: it depended on checkout bytes/newline normalization
   and platform-specific `Path` ordering. A POSIX/archive reconstruction of
   the immutable tagged contents reproduces
   `a82a61232f7d112405cd7d7f5f78239cd4e9020411363f354c7f4c40c69c6d03`,
   while a Windows/CRLF reconstruction reproduces
   `227f4891d8d5351cb066da12c8fcd8df41c4a78b95f28dae3d1895ac00510008`.
   These are hashes of the same tagged logical tree under different
   byte-normalization behavior, not a single portable canonical bundle hash.
   The tag is documented rather than rewritten.

v1.1 uses explicit relative POSIX-path ordering for exact release-byte
integrity. Its bundle manifest identifies the released bytes; calculation-level
reproduction is separately documented because Pillow figure rasterization is
not cross-platform byte-identical. This does not alter the immutable v1.0 tag.

## v1.1.0-research

v1.1.0-research is a scientific/provenance correction, not a new experiment.
It corrects oracle-gate interpretation, attempt asymmetry, resource terminology,
source/PDF consistency, citation metadata, licenses, and release provenance.
The authoritative final v1.1 publication/source hashes are recorded in
`RELEASE_METADATA.json`, `results/publication_checks.json`, and the excluded
dynamic `results/publication_bundle_manifest.json` after final validation.
