from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from .provenance import sha256_file
from .store import utc_now

RECONCILIATION_FILENAME = "telemetry_reconciliation.json"


def create_log_token_reconciliation(
    *,
    experiment_directory: Path,
    manifest: dict[str, Any],
    attempts: list[dict[str, Any]],
    benchmark: str,
    task_id: str,
    condition: str,
    attempt_number: int,
    input_tokens: int,
    output_tokens: int,
    source_log: str,
    evidence_start_line: int,
    evidence_end_line: int,
) -> Path:
    """Record measured Ollama log counters without changing authoritative raw attempts."""

    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("reconciled token counters must be non-negative")
    if attempt_number < 1:
        raise ValueError("reconciled attempt number must be at least one")
    target = _find_attempt(
        attempts,
        benchmark=benchmark,
        task_id=task_id,
        condition=condition,
        attempt_number=attempt_number,
    )
    if any(target.get(field) is not None for field in _TOKEN_FIELDS):
        raise ValueError("telemetry reconciliation may only fill missing token fields")
    source_path = _resolve_private_source(experiment_directory, source_log)
    source_sha256 = sha256_file(source_path)
    raw_results_path = experiment_directory / "raw_results.jsonl"
    if not raw_results_path.is_file():
        raise FileNotFoundError("raw results are unavailable for reconciliation binding")
    raw_results_sha256 = sha256_file(raw_results_path)
    _validate_log_evidence(
        source_path,
        start_line=evidence_start_line,
        end_line=evidence_end_line,
        selected_model=str(target["selected_model"]),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    destination = experiment_directory / RECONCILIATION_FILENAME
    existing_document = (
        json.loads(destination.read_text(encoding="utf-8")) if destination.is_file() else None
    )
    document = {
        "schema_version": 1,
        "experiment_id": manifest.get("experiment_id"),
        "created_at": (
            existing_document.get("created_at")
            if isinstance(existing_document, dict) and existing_document.get("created_at")
            else utc_now()
        ),
        "raw_measurements_unchanged": True,
        "raw_results_sha256": raw_results_sha256,
        "source": {
            "kind": "benchmark_owned_ollama_log",
            "relative_path": source_log.replace("\\", "/"),
            "sha256": source_sha256,
            "evidence_start_line": evidence_start_line,
            "evidence_end_line": evidence_end_line,
        },
        "entries": [
            {
                "benchmark": benchmark,
                "task_id": task_id,
                "condition": condition,
                "attempt_number": attempt_number,
                "selected_tier": target["selected_tier"],
                "selected_model": target["selected_model"],
                "original_status": target["status"],
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "evidence_method": "llama_server_timing_counters",
            }
        ],
    }
    serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        if json.loads(existing) != document:
            raise FileExistsError("a different telemetry reconciliation already exists")
        return destination
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
    return destination


def apply_telemetry_reconciliation(
    attempts: list[dict[str, Any]],
    manifest: dict[str, Any],
    experiment_directory: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return a reconciled derived view while preserving SQLite and raw JSONL unchanged."""

    path = experiment_directory / RECONCILIATION_FILENAME
    if not path.is_file():
        return attempts, None
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError("unsupported telemetry reconciliation schema")
    if document.get("experiment_id") != manifest.get("experiment_id"):
        raise ValueError("telemetry reconciliation experiment ID mismatch")
    if document.get("raw_measurements_unchanged") is not True:
        raise ValueError("telemetry reconciliation must preserve raw measurements")
    raw_results_path = experiment_directory / "raw_results.jsonl"
    if not raw_results_path.is_file() or sha256_file(raw_results_path) != document.get(
        "raw_results_sha256"
    ):
        raise ValueError("telemetry reconciliation raw-results checksum mismatch")
    source = document.get("source")
    if not isinstance(source, dict) or source.get("kind") != "benchmark_owned_ollama_log":
        raise ValueError("telemetry reconciliation source is not an Ollama log")
    source_path = _resolve_private_source(experiment_directory, str(source.get("relative_path")))
    if sha256_file(source_path) != source.get("sha256"):
        raise ValueError("telemetry reconciliation source log checksum mismatch")

    reconciled = copy.deepcopy(attempts)
    public_entries: list[dict[str, Any]] = []
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("telemetry reconciliation has no entries")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("telemetry reconciliation entry is not an object")
        input_tokens = _required_nonnegative_int(entry, "input_tokens")
        output_tokens = _required_nonnegative_int(entry, "output_tokens")
        target = _find_attempt(
            reconciled,
            benchmark=str(entry.get("benchmark")),
            task_id=str(entry.get("task_id")),
            condition=str(entry.get("condition")),
            attempt_number=_required_positive_int(entry, "attempt_number"),
        )
        if any(target.get(field) is not None for field in _TOKEN_FIELDS):
            raise ValueError("telemetry reconciliation would overwrite recorded token fields")
        if target.get("selected_tier") != entry.get("selected_tier"):
            raise ValueError("telemetry reconciliation tier mismatch")
        if target.get("selected_model") != entry.get("selected_model"):
            raise ValueError("telemetry reconciliation model mismatch")
        if target.get("status") != entry.get("original_status"):
            raise ValueError("telemetry reconciliation status mismatch")
        _validate_log_evidence(
            source_path,
            start_line=_required_nonnegative_int(source, "evidence_start_line"),
            end_line=_required_nonnegative_int(source, "evidence_end_line"),
            selected_model=str(target["selected_model"]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        parameter_billions = _parameter_billions(
            manifest,
            str(target["selected_tier"]),
            str(target["selected_model"]),
        )
        total_tokens = input_tokens + output_tokens
        generation_proxy = parameter_billions * output_tokens
        total_proxy = parameter_billions * total_tokens
        target.update(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "generation_cost_proxy": generation_proxy,
                "total_token_cost_proxy": total_proxy,
                "token_metrics_reconciled": True,
            }
        )
        public_entries.append(
            {
                "benchmark": target["benchmark"],
                "task_id": target["task_id"],
                "condition": target["condition"],
                "attempt_number": target["attempt_number"],
                "selected_tier": target["selected_tier"],
                "selected_model": target["selected_model"],
                "original_status": target["status"],
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "generation_cost_proxy": generation_proxy,
                "total_token_cost_proxy": total_proxy,
                "token_metrics_reconciled": True,
                "evidence_method": entry.get("evidence_method"),
            }
        )
    audit = {
        "status": "applied",
        "schema_version": 1,
        "records_applied": len(public_entries),
        "raw_measurements_unchanged": True,
        "raw_results_sha256": document["raw_results_sha256"],
        "reconciliation_sha256": sha256_file(path),
        "source_kind": source["kind"],
        "source_sha256": source["sha256"],
        "evidence_start_line": source["evidence_start_line"],
        "evidence_end_line": source["evidence_end_line"],
        "entries": public_entries,
        "unreconciled_fields": [
            "status",
            "verification",
            "wall_time_ms",
            "model_load_time_ms",
            "inference_time_ms",
        ],
    }
    return reconciled, audit


_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "generation_cost_proxy",
    "total_token_cost_proxy",
)


def _find_attempt(
    attempts: list[dict[str, Any]],
    *,
    benchmark: str,
    task_id: str,
    condition: str,
    attempt_number: int,
) -> dict[str, Any]:
    matches = [
        attempt
        for attempt in attempts
        if attempt.get("benchmark") == benchmark
        and attempt.get("task_id") == task_id
        and attempt.get("condition") == condition
        and attempt.get("attempt_number") == attempt_number
    ]
    if len(matches) != 1:
        raise ValueError(f"telemetry reconciliation target count was {len(matches)}, expected one")
    return matches[0]


def _resolve_private_source(experiment_directory: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("telemetry reconciliation source must be experiment-relative")
    root = experiment_directory.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise FileNotFoundError("telemetry reconciliation source is unavailable")
    return candidate


def _validate_log_evidence(
    path: Path,
    *,
    start_line: int,
    end_line: int,
    selected_model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    if start_line < 1 or end_line < start_line:
        raise ValueError("invalid telemetry evidence line range")
    if end_line - start_line + 1 > 64:
        raise ValueError("telemetry evidence line range is too broad")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if end_line > len(lines):
        raise ValueError("telemetry evidence line range exceeds the source log")
    evidence = "\n".join(lines[start_line - 1 : end_line])
    if selected_model not in evidence:
        raise ValueError("telemetry evidence does not identify the selected model")
    if re.search(rf"tokens:\s*text\s*=\s*{input_tokens}\b", evidence) is None:
        raise ValueError("telemetry evidence does not contain the input-token counter")
    if re.search(rf"eval time\s*=.*?/\s*{output_tokens}\s+tokens\b", evidence) is None:
        raise ValueError("telemetry evidence does not contain the output-token counter")
    total_tokens = input_tokens + output_tokens
    if re.search(rf"total time\s*=.*?/\s*{total_tokens}\s+tokens\b", evidence) is None:
        raise ValueError("telemetry evidence does not contain the total-token counter")
    if (
        re.search(
            r"\[GIN\].*\|\s*200\s*\|.*POST\s+\"/api/generate\"",
            evidence,
        )
        is None
    ):
        raise ValueError("telemetry evidence does not contain a successful generation response")


def _parameter_billions(manifest: dict[str, Any], tier: str, selected_model: str) -> float:
    matches = [
        model
        for model in manifest.get("models", ())
        if model.get("tier") == tier and (model.get("model") or model.get("name")) == selected_model
    ]
    if len(matches) != 1:
        raise ValueError("frozen model metadata does not contain exactly one tier/model match")
    value = matches[0].get("parameter_billions")
    if not isinstance(value, int | float) or value <= 0:
        raise ValueError("frozen model parameter value is invalid")
    return float(value)


def _required_nonnegative_int(mapping: dict[str, Any], field: str) -> int:
    value = mapping.get(field)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"telemetry reconciliation {field} must be a non-negative integer")
    return value


def _required_positive_int(mapping: dict[str, Any], field: str) -> int:
    value = _required_nonnegative_int(mapping, field)
    if value < 1:
        raise ValueError(f"telemetry reconciliation {field} must be at least one")
    return value
