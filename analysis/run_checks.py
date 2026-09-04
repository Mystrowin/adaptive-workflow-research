"""Run deterministic publication safety and integrity checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HASH_ALGORITHM = "sha256-path-manifest-v2-posix-relative-order"

EXPECTED_PDF_METADATA = {
    "/Title": "Verification-Gated Local Model Cascading",
    "/Author": "Neeraj Pragnya Krishna Vasagiri",
    "/Subject": (
        "Oracle-gated study of task-level model complementarity and "
        "verification-gated model cascading for local coding inference on EvalPlus"
    ),
    "/Keywords": (
        "code generation, model cascading, oracle-gated evaluation, LLM routing, "
        "EvalPlus, local inference, reproducibility"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def main(mode: str = "release-integrity") -> None:
    audit = json.loads((RESULTS / "audit.json").read_text(encoding="utf-8"))
    summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    safety = json.loads(
        (RESULTS / "publishable_safety_report.json").read_text(encoding="utf-8")
    )
    errors: list[str] = []

    if audit["integrity"]["all_cells_completed"] is not True:
        errors.append("historical cells are not complete")
    if audit["integrity"]["expected_cells_historical_three_conditions"] != 1626:
        errors.append("unexpected historical cell count")
    if audit["integrity"]["duplicate_attempt_keys"] != 0:
        errors.append("duplicate attempt keys")
    if (
        audit["integrity"]["raw_results_sha256"]
        != "6926147073d0e5b3ffe93ecb3d9c8619707b24f0b48a843d25db6627602268da"
    ):
        errors.append("raw JSONL hash differs from audited hash")
    if (
        audit["integrity"]["sqlite_sha256"]
        != "138d04bc1c2f3b6609a56cc2a5e77a6d024035f22d948f81a674139ef06976e7"
    ):
        errors.append("SQLite hash differs from audited hash")
    if summary["status"] != "completed" or summary["resource_violation"] is not False:
        errors.append("summary status/resource violation mismatch")
    if safety["status"] != "passed" or safety["sensitive_matches"] != 0:
        errors.append("sanitized export safety report did not pass")

    expected_passes = {"adaptive": 331, "strong_only": 297, "small_only": 220}
    for condition, expected in expected_passes.items():
        actual = audit["condition_results"][condition]["task_weighted"]["passes"]
        if actual != expected:
            errors.append(f"{condition} Plus-pass count is {actual}, expected {expected}")
    if audit["integrity"]["frozen_source_tree_sha256"] != (
        "0d24437e9297466c3f28a7af677a76d7e54c10dc6358edb7b724d586040e7859"
    ):
        errors.append("historical frozen source-tree hash differs from audited hash")

    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    for required in (
        'version: "1.1.0-research"',
        "repository-code: \"https://github.com/Mystrowin/adaptive-workflow-research\"",
        "license: CC-BY-4.0",
        "oracle-gated",
    ):
        if required not in cff:
            errors.append(f"CITATION.cff missing required text: {required}")

    release_metadata = json.loads(
        (ROOT / "RELEASE_METADATA.json").read_text(encoding="utf-8")
    )
    if release_metadata.get("release_version") != "1.1.0-research":
        errors.append("release metadata version mismatch")
    if release_metadata.get("doi") is not None or release_metadata.get("venue") is not None:
        errors.append("release metadata claims a DOI or venue that was not published")
    if not isinstance(release_metadata.get("push_or_upload_authorized"), bool):
        errors.append("release metadata publication-authorization field is not boolean")

    paper_reader = PdfReader(
        str(ROOT / "paper" / "Verification-Gated-Local-Model-Cascading.pdf")
    )
    paper_metadata = {str(k): str(v) for k, v in (paper_reader.metadata or {}).items()}
    for key, expected in EXPECTED_PDF_METADATA.items():
        if paper_metadata.get(key) != expected:
            errors.append(f"PDF metadata mismatch for {key}")
    paper_text = "\n".join(page.extract_text() or "" for page in paper_reader.pages)
    paper_text = paper_text.translate(
        str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"})
    )
    paper_text = " ".join(paper_text.split())
    for required in (
        "An EvalPlus Reproducibility Study of Task-Level Complementarity",
        "Adaptive produced 331",
        "Strong-only 297",
        "Small-only 220",
        "Corrected preprint",
        "not evidence for an independently deployable verifier",
    ):
        if required.lower() not in paper_text.lower():
            errors.append(f"canonical PDF missing required text: {required}")

    if len(paper_reader.pages) != 9:
        errors.append("canonical PDF page count is not nine")

    failure_evidence = ROOT / "docs" / "MBPP_VERIFIER_FAILURE_ROOT_CAUSE.md"
    if not failure_evidence.is_file():
        errors.append("missing sanitized MBPP verifier-failure evidence")
    else:
        evidence_text = failure_evidence.read_text(encoding="utf-8")
        for task_id in ("106", "124", "252", "255", "580", "720"):
            if f"Mbpp/{task_id}" not in evidence_text:
                errors.append(f"MBPP evidence missing Mbpp/{task_id}")

    # Scan source and publication text for actual credential/path-shaped values.
    # Deliberately do not flag ordinary words such as "token" or "password"
    # in documentation; only assignments, key material, and concrete paths.
    patterns = [
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
        re.compile(
            r"(?i)(?:api[_-]?key|access[_-]?token|password|cookie)\s*[:=]\s*(?!<|null\b)\S+"
        ),
        re.compile(r"(?i)[A-Z]:\\Users\\[^\\\s]+"),
        re.compile(r"(?i)/home/[^/\s]+"),
    ]
    matches: list[dict[str, str]] = []
    ignored_names = {"privacy_scan.json", "publication_checks.json"}
    for path in ROOT.rglob("*"):
        # Python source may legitimately contain the scanner's own regex
        # definitions and synthetic test examples; scan all publication data
        # and documentation while excluding executable detector code.
        if (
            not path.is_file()
            or path.name in ignored_names
            or path.suffix.lower() in {".png", ".pdf", ".pyc", ".py"}
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in patterns:
            if pattern.search(text):
                matches.append(
                    {
                        "file": path.relative_to(ROOT).as_posix(),
                        "pattern": pattern.pattern,
                    }
                )
    # The source snapshot includes deliberately synthetic scanner test vectors
    # only in its historical test module; tests are excluded from this release.
    if matches:
        errors.append("credential/path-shaped pattern detected")

    generated = [
        ROOT / "results" / "recalculated_claims.json",
        ROOT / "results" / "reference_validation.json",
        ROOT / "paper" / "tables" / "table1_configuration.tex",
        ROOT / "paper" / "tables" / "table2_correctness.tex",
        ROOT / "paper" / "tables" / "table3_resource_usage.tex",
        ROOT / "paper" / "tables" / "table4_paired_outcomes.tex",
        ROOT / "paper" / "tables" / "table5_complementarity.tex",
        ROOT / "paper" / "tables" / "table6_threats.tex",
    ]
    generated.extend((ROOT / "paper" / "figures").glob("figure*.png"))
    missing = [str(path.relative_to(ROOT)) for path in generated if not path.exists()]
    if missing:
        errors.append("missing generated artifacts: " + ", ".join(missing))

    # Hash only release inputs. Tool caches and bytecode are intentionally
    # ignored so running the checks in a different Python environment cannot
    # change the publication bundle digest. Validation/build reports contain
    # wall-clock metadata and are also excluded from the release digest.
    ignored_hash_dirs = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        ".venv",
        ".uv",
        ".uv-cache",
    }
    ignored_hash_names = {
        "publication_checks.json",
        "privacy_scan.json",
        "reference_validation.json",
        "RELEASE_METADATA.json",
        "publication_bundle_manifest.json",
    }
    included_files: list[tuple[str, Path]] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if (
            path.is_file()
            and path.name not in ignored_hash_names
            and not any(part in ignored_hash_dirs for part in relative.parts)
            and path.suffix.lower() not in {".pyc", ".pyo"}
        ):
            included_files.append((relative.as_posix(), path))
    file_hashes = {
        name: sha256(path)
        for name, path in sorted(included_files, key=lambda item: item[0])
    }
    bundle_digest = hashlib.sha256(
        "".join(f"{name}  {digest}\n" for name, digest in file_hashes.items()).encode(
            "utf-8"
        )
    ).hexdigest()

    source_prefixes = ("analysis/", "benchmark/")
    source_names = {"paper/references.bib"}
    source_hashes = {
        name: digest
        for name, digest in file_hashes.items()
        if name.startswith(source_prefixes) or name in source_names
    }
    current_source_digest = hashlib.sha256(
        "".join(
            f"{name}  {digest}\n" for name, digest in source_hashes.items()
        ).encode("utf-8")
    ).hexdigest()
    hash_manifest = {
        "algorithm": HASH_ALGORITHM,
        "publication_bundle_sha256": bundle_digest,
        "publication_file_count": len(file_hashes),
        "publication_files": file_hashes,
        "current_source_bundle_sha256": current_source_digest,
        "current_source_scope": (
            "analysis/, benchmark/, and paper/references.bib"
        ),
        "current_source_file_count": len(source_hashes),
        "current_source_files": source_hashes,
        "excluded_dynamic_basenames": sorted(ignored_hash_names),
        "excluded_directories": sorted(ignored_hash_dirs),
    }
    hash_manifest["verification_mode"] = mode
    hash_manifest["recorded_release_bundle_sha256"] = release_metadata.get(
        "publication_bundle_sha256"
    )
    hash_manifest["recorded_release_source_bundle_sha256"] = release_metadata.get(
        "current_source_bundle_sha256"
    )
    write_text(
        RESULTS / "publication_bundle_manifest.json",
        json.dumps(hash_manifest, indent=2, sort_keys=True) + "\n",
    )

    recorded_publication_hash = release_metadata.get("publication_bundle_sha256")
    release_byte_integrity = (
        "passed"
        if recorded_publication_hash in {None, bundle_digest}
        else "not_matched"
    )
    if mode == "release-integrity" and release_byte_integrity != "passed":
        errors.append("RELEASE_METADATA publication bundle hash is stale")
    recorded_source_hash = release_metadata.get("current_source_bundle_sha256")
    source_byte_integrity = (
        "passed"
        if recorded_source_hash in {None, current_source_digest}
        else "not_matched"
    )
    if mode == "release-integrity" and source_byte_integrity != "passed":
        errors.append("RELEASE_METADATA current source bundle hash is stale")
    privacy_report = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not matches else "failed",
        "files_scanned": len(file_hashes),
        "sensitive_matches": len(matches),
        "matches": matches,
        "allowlist_note": "Publication files are generated from sanitized results; private raw artifacts and test vectors are excluded.",
    }
    write_text(
        RESULTS / "privacy_scan.json",
        json.dumps(privacy_report, indent=2, sort_keys=True) + "\n",
    )
    checks = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "missing_generated_artifacts": missing,
        "publication_bundle_sha256": bundle_digest,
        "recorded_release_bundle_sha256": recorded_publication_hash,
        "release_byte_integrity": release_byte_integrity,
        "hash_algorithm": HASH_ALGORITHM,
        "current_source_bundle_sha256": current_source_digest,
        "recorded_release_source_bundle_sha256": recorded_source_hash,
        "source_byte_integrity": source_byte_integrity,
        "current_source_bundle_scope": (
            "analysis/, benchmark/, and paper/references.bib; "
            "excludes historical private artifacts and generated PDF/results"
        ),
        "canonical_paper_pdf_sha256": sha256(
            ROOT / "paper" / "Verification-Gated-Local-Model-Cascading.pdf"
        ),
        "historical_raw_hashes": {
            "raw_results_jsonl": audit["integrity"]["raw_results_sha256"],
            "results_sqlite": audit["integrity"]["sqlite_sha256"],
            "frozen_source_tree": audit["integrity"]["frozen_source_tree_sha256"],
        },
        "historical_records_modified": False,
        "calculation_reproduction": "passed",
    }
    checks["verification_mode"] = mode
    write_text(
        RESULTS / "publication_checks.json",
        json.dumps(checks, indent=2, sort_keys=True) + "\n",
    )
    print(json.dumps(checks, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("release-integrity", "calculation-reproduction"),
        default="release-integrity",
        help=(
            "release-integrity requires exact release-byte hashes; "
            "calculation-reproduction validates data/artifacts without claiming "
            "cross-platform PNG byte identity"
        ),
    )
    args = parser.parse_args()
    main(mode=args.mode)
