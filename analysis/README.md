# Deterministic analysis

The scripts in this directory perform no model inference and make no network
requests. Install the analysis-only dependencies first when they are not
already available:

~~~powershell
python -m pip install -r analysis/requirements.txt
~~~

~~~powershell
python analysis/make_publication_artifacts.py
python analysis/validate_references.py
python analysis/run_checks.py --mode release-integrity
~~~

make_publication_artifacts.py recalculates the headline values from the
allowlisted audit and summary JSON, writes UTF-8/LF publication tables, and
writes results/recalculated_claims.json. It renders the six Pillow figures in
an ephemeral staging area and validates their dimensions without overwriting
the released PNGs. Font rasterization is not portable byte-for-byte; use
`--replace-canonical-figures` only for an explicit new-release update.

validate_references.py checks that each BibTeX record has a title, author,
year, and verifiable primary-source URL or DOI recorded in the manuscript
source notes. It writes results/reference_validation.json.

The reviewed publication PDF is a static artifact. This repository does not
include a public manuscript compiler or editable manuscript source.

run_checks.py has two explicit modes. `--mode release-integrity` verifies exact
released-byte hashes. `--mode calculation-reproduction` validates arithmetic,
metadata, safety, and generated text without claiming cross-platform PNG-byte
identity. Both write UTF-8/LF dynamic reports, which are excluded from the
release bundle hash.
