from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import public_task_result
from .provenance import sha256_file
from .reconciliation import apply_telemetry_reconciliation
from .store import BenchmarkStore

ALLOWED_FILENAMES = {
    "README.md",
    "REPORT.md",
    "methodology.md",
    "experiment_manifest.json",
    "summary.json",
    "summary.csv",
    "benchmark_sources.json",
    "task_results.jsonl",
    "export_manifest.json",
    "publishable_safety_report.json",
    "telemetry_reconciliation.json",
    "checksums.txt",
}
ALLOWED_SUFFIXES = {".md", ".json", ".jsonl", ".csv", ".txt"}
PROHIBITED_SUFFIXES = {".db", ".sqlite", ".log", ".env", ".pem", ".key", ".dmp", ".py"}


def export_publishable(
    *,
    experiment_id: str,
    experiment_directory: Path,
    publishable_root: Path,
) -> Path:
    database_path = experiment_directory / "results.sqlite"
    with BenchmarkStore(database_path, read_only=True) as store:
        status = store.status()
        if status["status"] != "completed":
            _blocked(
                experiment_directory,
                experiment_id,
                "experiment_not_completed",
            )
            raise RuntimeError("publishable_export_blocked: experiment_not_completed")
        raw_attempts = store.all_attempts()

    manifest = json.loads(
        (experiment_directory / "experiment_manifest.json").read_text(encoding="utf-8")
    )
    summary = json.loads((experiment_directory / "summary.json").read_text(encoding="utf-8"))
    sources = json.loads(
        (experiment_directory / "benchmark_sources.json").read_text(encoding="utf-8")
    )
    attempts, telemetry_reconciliation = apply_telemetry_reconciliation(
        raw_attempts, manifest, experiment_directory
    )
    if summary.get("telemetry_reconciliation") != telemetry_reconciliation:
        raise RuntimeError("derived summary is not synchronized with telemetry reconciliation")
    final_directory = _next_versioned_directory(publishable_root, experiment_id)
    publishable_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{experiment_id}-staging-", dir=publishable_root))
    try:
        (staging / "licenses").mkdir()
        (staging / "figures").mkdir()
        (staging / "tables").mkdir()
        _write_export_files(
            staging,
            manifest,
            summary,
            sources,
            attempts,
            experiment_directory,
            telemetry_reconciliation,
        )
        matches = _scan_staging(staging)
        if matches:
            raise RuntimeError("; ".join(matches[:20]))
        safety_report = {
            "experiment_id": experiment_id,
            "export_directory": final_directory.name,
            "validated_at": datetime.now(UTC).isoformat(),
            "status": "passed",
            "files_checked": 0,
            "sensitive_matches": 0,
            "licenses_included": bool(list((staging / "licenses").iterdir())),
            "checksums_generated": True,
        }
        (staging / "publishable_safety_report.json").write_text(
            json.dumps(safety_report, indent=2, sort_keys=True), encoding="utf-8"
        )
        export_manifest = {
            "experiment_id": experiment_id,
            "files": sorted(
                [
                    path.relative_to(staging).as_posix()
                    for path in staging.rglob("*")
                    if path.is_file()
                ]
                + ["checksums.txt", "export_manifest.json"]
            ),
        }
        safety_report["files_checked"] = len(export_manifest["files"])
        (staging / "publishable_safety_report.json").write_text(
            json.dumps(safety_report, indent=2, sort_keys=True), encoding="utf-8"
        )
        (staging / "export_manifest.json").write_text(
            json.dumps(export_manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        checksums = []
        for path in sorted(staging.rglob("*"), key=lambda candidate: candidate.as_posix()):
            if path.is_file() and path.name != "checksums.txt":
                checksums.append(f"{sha256_file(path)}  {path.relative_to(staging).as_posix()}")
        (staging / "checksums.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
        matches = _scan_staging(staging)
        if matches:
            raise RuntimeError("; ".join(matches[:20]))
        if final_directory.exists():
            raise FileExistsError(final_directory)
        staging.replace(final_directory)
        return final_directory
    except BaseException as exc:
        shutil.rmtree(staging, ignore_errors=True)
        _blocked(experiment_directory, experiment_id, str(exc))
        raise RuntimeError(f"publishable_export_blocked: {exc}") from exc


def _write_export_files(
    staging: Path,
    manifest: dict[str, Any],
    summary: dict[str, Any],
    sources: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    experiment_directory: Path,
    telemetry_reconciliation: dict[str, Any] | None,
) -> None:
    safe_manifest_keys = {
        "experiment_id",
        "adaptive_workflow_version",
        "source_tree_sha256",
        "os",
        "python_version",
        "cpu",
        "physical_ram_bytes",
        "ollama_version",
        "docker_image",
        "docker_image_digest",
        "models",
        "sampling",
        "benchmarks",
        "task_ids",
        "seed",
        "resource_limits",
        "routing",
        "verification",
        "budget",
        "started_at",
        "ended_at",
        "status",
        "exclusions",
    }
    safe_manifest = {key: manifest.get(key) for key in safe_manifest_keys if key in manifest}
    safe_sources: list[dict[str, Any]] = []
    for source in sources:
        license_source = Path(str(source["license_file"]))
        license_name = license_source.name
        destination = staging / "licenses" / license_name
        shutil.copyfile(license_source, destination)
        safe_sources.append(
            {
                key: value
                for key, value in source.items()
                if key
                in {
                    "benchmark",
                    "source",
                    "version",
                    "license",
                    "artifact_sha256",
                    "artifact_size",
                    "license_sha256",
                    "retrieved_at",
                    "derived_from",
                }
            }
            | {"license_file": f"licenses/{license_name}"}
        )
    (staging / "experiment_manifest.json").write_text(
        json.dumps(safe_manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    (staging / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    shutil.copyfile(experiment_directory / "summary.csv", staging / "summary.csv")
    shutil.copyfile(experiment_directory / "REPORT.md", staging / "REPORT.md")
    (staging / "benchmark_sources.json").write_text(
        json.dumps(safe_sources, indent=2, sort_keys=True), encoding="utf-8"
    )
    if telemetry_reconciliation is not None:
        (staging / "telemetry_reconciliation.json").write_text(
            json.dumps(telemetry_reconciliation, indent=2, sort_keys=True), encoding="utf-8"
        )
    with (staging / "task_results.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for payload in attempts:
            stream.write(json.dumps(_public_payload(payload), sort_keys=True) + "\n")
    (staging / "methodology.md").write_text(
        "# Methodology\n\n"
        "This Adaptive Workflow benchmark uses the same frozen task prompts and deterministic "
        "EvalPlus base/Plus tests for all conditions. Base and Plus outcomes come from the same "
        "completion. Model-weighted token values are cost proxies, not FLOPs or hardware compute. "
        "Physical efficiency evidence is CPU, RAM, and time measured during the run. "
        + (
            "A checksum-bound post-run reconciliation restores one measured Ollama token "
            "counter pair while leaving raw records and verification outcomes unchanged.\n"
            if telemetry_reconciliation is not None
            else "\n"
        ),
        encoding="utf-8",
    )
    (staging / "README.md").write_text(
        "# Publishable Adaptive Workflow Benchmark Results\n\n"
        "This folder was generated through an allowlisted sanitization step. Review every file "
        "and the applicable benchmark licenses before public release. Nothing in this folder is "
        "automatically uploaded, published, or committed. This is not an EHMN benchmark. "
        + (
            "See telemetry_reconciliation.json for the allowlisted post-run token-telemetry "
            "audit record.\n"
            if telemetry_reconciliation is not None
            else "\n"
        ),
        encoding="utf-8",
    )


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from .models import (
        AttemptRecord,
        AttemptStatus,
        BenchmarkCondition,
        BenchmarkTier,
        ResourceMetrics,
        VerificationOutcome,
    )

    reconciled = bool(payload.get("token_metrics_reconciled", False))
    record_payload = {
        key: value for key, value in payload.items() if key != "token_metrics_reconciled"
    }
    record = AttemptRecord(
        **{
            **record_payload,
            "condition": BenchmarkCondition(payload["condition"]),
            "selected_tier": BenchmarkTier(payload["selected_tier"]),
            "status": AttemptStatus(payload["status"]),
            "route": tuple(payload.get("route", ())),
            "escalation_path": tuple(payload.get("escalation_path", ())),
            "verification": VerificationOutcome(**payload["verification"]),
            "resources": ResourceMetrics(
                **{
                    **payload["resources"],
                    "resource_limit_events": tuple(
                        payload["resources"].get("resource_limit_events", ())
                    ),
                }
            ),
        }
    )
    public = public_task_result(record)
    public["token_metrics_reconciled"] = reconciled
    return public


def _scan_staging(root: Path) -> list[str]:
    matches: list[str] = []
    home = str(Path.home()).lower()
    patterns = (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|password|cookie)\s*[:=]\s*\S+"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
        re.compile(r"(?i)authorization:\s*(?:bearer|basic)\s+\S+"),
        re.compile(r"(?i)[A-Z]:\\Users\\[^\\\s]+"),
        re.compile(r"/home/[^/\s]+"),
    )
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() in PROHIBITED_SUFFIXES:
            matches.append(f"prohibited suffix: {relative}")
            continue
        if path.name not in ALLOWED_FILENAMES and path.parent.name != "licenses":
            matches.append(f"file is not allowlisted: {relative}")
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            matches.append(f"file type is not allowlisted: {relative}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        if home and home in lowered:
            matches.append(f"local home path: {relative}")
        for pattern in patterns:
            if pattern.search(text):
                matches.append(f"sensitive pattern in {relative}: {pattern.pattern}")
    return matches


def _next_versioned_directory(root: Path, experiment_id: str) -> Path:
    version = 1
    while (root / f"{experiment_id}-v{version}").exists():
        version += 1
    return root / f"{experiment_id}-v{version}"


def _blocked(experiment_directory: Path, experiment_id: str, reason: str) -> Path:
    path = experiment_directory / "publishable_export_blocked.json"
    path.write_text(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "status": "publishable_export_blocked",
                "reason": reason[:2000],
                "recorded_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path
