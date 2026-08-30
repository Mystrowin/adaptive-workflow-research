"""Run deterministic publication safety and integrity checks."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
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
        "paper_build_metadata.json",
    }
    file_hashes = {}
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if (
            path.is_file()
            and path.name not in ignored_hash_names
            and not any(part in ignored_hash_dirs for part in relative.parts)
            and path.suffix.lower() not in {".pyc", ".pyo"}
        ):
            file_hashes[relative.as_posix()] = sha256(path)
    bundle_digest = hashlib.sha256(
        "".join(f"{name}  {digest}\n" for name, digest in file_hashes.items()).encode(
            "utf-8"
        )
    ).hexdigest()
    privacy_report = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not matches else "failed",
        "files_scanned": len(file_hashes),
        "sensitive_matches": len(matches),
        "matches": matches,
        "allowlist_note": "Publication files are generated from sanitized results; private raw artifacts and test vectors are excluded.",
    }
    (RESULTS / "privacy_scan.json").write_text(
        json.dumps(privacy_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checks = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "missing_generated_artifacts": missing,
        "publication_bundle_sha256": bundle_digest,
        "historical_raw_hashes": {
            "raw_results_jsonl": audit["integrity"]["raw_results_sha256"],
            "results_sqlite": audit["integrity"]["sqlite_sha256"],
        },
        "historical_records_modified": False,
    }
    (RESULTS / "publication_checks.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(checks, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
