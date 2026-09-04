# Reproducibility

## Publication analysis

From the repository root with Python 3.11 or newer:

~~~powershell
python -m pip install -r analysis/requirements.txt
python analysis/make_publication_artifacts.py
python analysis/validate_references.py
python analysis/run_checks.py --mode release-integrity
~~~

These commands regenerate publication tables and stage-render figures, validate 16 references,
and run privacy/integrity checks. They do not invoke a model or rerun EvalPlus.
The reviewed article is intentionally distributed as a static PDF; no public
manuscript compiler or editable manuscript source is included.

## Release-byte integrity versus calculation reproduction

`release-integrity` verifies the exact checked-in release bytes against the
recorded bundle/source hashes. It is the mode used before publication. All
generated text is UTF-8/LF and deterministic. PNG figures are not promised to
be cross-platform byte-identical because Pillow font rasterization depends on
available fonts and rendering libraries. By default the artifact script renders
them in a temporary staging directory and validates their dimensions without
touching the released PNGs.

For an independent calculation-level check on another platform, run:

~~~powershell
python analysis/make_publication_artifacts.py
python analysis/validate_references.py
python analysis/run_checks.py --mode calculation-reproduction
~~~

That mode validates the calculations, required artifacts, privacy, and metadata
without treating a noncanonical PNG rendering difference as a release failure.
Replacing canonical figures requires the explicit
`--replace-canonical-figures` option and a new release-byte hash.

## Historical boundary

The run retained task identity, tier/model metadata, tokens, verification
status, telemetry, manifests, and raw artifact hashes. Exact generated programs
and their hashes were not retained. The published material therefore supports
calculation-level reproduction, not output-level re-evaluation of the August
2026 candidates.

The current `benchmark/engine/` harness includes post-run audit and future-run
improvements. It is not byte-identical to the historical source. The public Git
history does not contain a tree matching the preserved historical source hash,
so no snapshot is fabricated.

## Future runs

A future experiment must use a new experiment ID, local-only inference, frozen
data/model manifests, and private exact-output retention. Preparation is the
only network-enabled phase. Docker and Ollama are separately installed system
prerequisites; preparation does not silently install them.

## Private/public boundary

Do not publish private raw databases, prompts, generated code, model weights,
logs, credentials, or local paths. `results/` is an allowlisted sanitized
export; its checksums cover historical published result files. Current release
bundle hashes are separate from historical raw and source hashes.
