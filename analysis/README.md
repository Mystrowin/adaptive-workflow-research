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
python analysis/build_paper_pdf.py
python analysis/run_checks.py
~~~

make_publication_artifacts.py recalculates the headline values from the
allowlisted audit and summary JSON, writes publication tables, and generates
six deterministic PNG figures with Pillow. It also writes
results/recalculated_claims.json.

validate_references.py checks that each BibTeX record has a title, author,
year, and verifiable primary-source URL or DOI recorded in the manuscript
source notes. It writes results/reference_validation.json.

build_paper_pdf.py builds paper/paper.pdf with the native LaTeX toolchain when
available. If no LaTeX engine is installed, it records that fact and produces
a deterministic ReportLab PDF fallback; paper/main.tex remains the canonical
source for a native rebuild.

run_checks.py validates result hashes and safety metadata, scans the public
tree for credential-shaped strings and local paths, checks generated artifacts,
and writes results/privacy_scan.json and results/publication_checks.json. Run it
after the PDF build so the bundle hash covers the final PDF.
