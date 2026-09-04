from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import VerificationOutcome, classify_failure
from .reconciliation import apply_telemetry_reconciliation
from .store import BenchmarkStore, utc_now


def generate_reports(
    store: BenchmarkStore,
    experiment_directory: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    raw_attempts = store.all_attempts()
    raw_available = _token_metrics_available(raw_attempts)
    attempts, telemetry_reconciliation = apply_telemetry_reconciliation(
        raw_attempts, manifest, experiment_directory
    )
    summary = calculate_summary(
        attempts,
        manifest,
        store.resource_extrema(),
        telemetry_reconciliation=telemetry_reconciliation,
        raw_token_metrics_available_attempts=raw_available,
        raw_token_metrics_total_attempts=len(raw_attempts),
    )
    (experiment_directory / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    _write_summary_csv(experiment_directory / "summary.csv", summary)
    (experiment_directory / "REPORT.md").write_text(render_report(summary), encoding="utf-8")
    return summary


def calculate_summary(
    attempts: list[dict[str, Any]],
    manifest: dict[str, Any],
    resource_extrema: dict[str, Any] | None = None,
    *,
    telemetry_reconciliation: dict[str, Any] | None = None,
    raw_token_metrics_available_attempts: int | None = None,
    raw_token_metrics_total_attempts: int | None = None,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        key = (attempt["condition"], attempt["benchmark"], attempt["task_id"])
        grouped[key].append(attempt)

    aggregate_rows: list[dict[str, Any]] = []
    conditions = sorted({key[0] for key in grouped})
    benchmarks = sorted({key[1] for key in grouped})
    for condition in conditions:
        for benchmark in [*benchmarks, "overall"]:
            cells = [
                cell_attempts
                for (cell_condition, cell_benchmark, _), cell_attempts in grouped.items()
                if cell_condition == condition
                and (benchmark == "overall" or cell_benchmark == benchmark)
            ]
            if cells:
                aggregate_rows.append(_aggregate_cells(condition, benchmark, cells))

    budget = manifest.get("budget") or {}
    curves = {
        condition: {
            "total_token_cost_proxy": _budget_curve(
                [item for item in attempts if item["condition"] == condition],
                tuple(float(value) for value in budget.get("total_token_cutoffs", ())),
                "total_token_cost_proxy",
            ),
            "generation_cost_proxy": _budget_curve(
                [item for item in attempts if item["condition"] == condition],
                tuple(float(value) for value in budget.get("generation_cutoffs", ())),
                "generation_cost_proxy",
            ),
        }
        for condition in conditions
    }
    adaptive_cells = {
        (benchmark, task_id): cell
        for (condition, benchmark, task_id), cell in grouped.items()
        if condition == "adaptive"
    }
    adaptive_passes = [
        cell for cell in adaptive_cells.values() if cell[-1]["verification"]["plus_passed"]
    ]
    avoided = [
        cell
        for cell in adaptive_passes
        if all(attempt["selected_tier"] != "BEST" for attempt in cell)
    ]
    derived_available = _token_metrics_available(attempts)
    token_metrics_complete = bool(attempts) and derived_available == len(attempts)
    raw_available = (
        derived_available
        if raw_token_metrics_available_attempts is None
        else raw_token_metrics_available_attempts
    )
    raw_total = (
        len(attempts)
        if raw_token_metrics_total_attempts is None
        else raw_token_metrics_total_attempts
    )
    resource_metrics_complete = bool(attempts) and all(
        not {
            "docker_metrics_unavailable",
            "docker_cpu_metrics_invalid",
            "native_cpu_metrics_invalid",
        }
        & set(attempt.get("resources", {}).get("resource_limit_events", ()))
        for attempt in attempts
    )
    failure_classes: dict[str, int] = defaultdict(int)
    for attempt in attempts:
        recorded = attempt.get("failure_class")
        if not recorded:
            recorded = classify_failure(
                str(attempt["status"]),
                VerificationOutcome(**attempt["verification"]),
                "unavailable",
            )
        failure_classes[str(recorded)] += 1
    return {
        "generated_at": utc_now(),
        "experiment_id": manifest.get("experiment_id"),
        "status": manifest.get("status"),
        "unique_tasks": len({(key[1], key[2]) for key in grouped}),
        "task_condition_cells": len(grouped),
        "attempts": len(attempts),
        "token_metrics_complete": token_metrics_complete,
        "derived_token_metrics_complete": token_metrics_complete,
        "derived_token_metrics_available_attempts": derived_available,
        "raw_token_metrics_complete": bool(raw_total) and raw_available == raw_total,
        "raw_token_metrics_available_attempts": raw_available,
        "raw_token_metrics_total_attempts": raw_total,
        "failure_class_counts": dict(sorted(failure_classes.items())),
        "resource_metrics_complete": resource_metrics_complete,
        "telemetry_reconciliation": telemetry_reconciliation,
        "cost_proxy_notice": (
            "Model-size-weighted token values are token cost proxies, not measured FLOPs, "
            "hardware compute, energy, API usage, credits, or dollar cost."
        ),
        "metric_labels": {
            "generation_cost_proxy": "model-size-weighted output-token proxy",
            "total_token_cost_proxy": "model-size-weighted total-token proxy",
            "cpu_time_seconds": "sample-integrated CPU-seconds estimate",
            "wall_time_ms": "summed generation-and-verification wall time",
            "peak_ram_bytes": "measured peak RAM",
        },
        "aggregates": aggregate_rows,
        "budget_curves": curves,
        "strong_model_avoidance_rate": (
            len(avoided) / len(adaptive_passes) if adaptive_passes else None
        ),
        "strong_model_avoidance_interpretation": (
            "Tier-use composition among Adaptive EvalPlus Plus test passes; "
            "not an efficiency metric."
        ),
        "experiment_resource_extrema": resource_extrema or {},
        "resource_violation": any(
            "hard_ceiling_observed"
            in " ".join(attempt.get("resources", {}).get("resource_limit_events", ()))
            for attempt in attempts
        ),
        "automatic_efficiency_claim": None,
    }


def _aggregate_cells(
    condition: str,
    benchmark: str,
    cells: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    first = [cell[0] for cell in cells]
    final = [cell[-1] for cell in cells]
    all_attempts = [attempt for cell in cells for attempt in cell]
    final_plus_passes = sum(bool(item["verification"]["plus_passed"]) for item in final)
    final_base_passes = sum(bool(item["verification"]["base_passed"]) for item in final)
    input_tokens = [
        item["input_tokens"] for item in all_attempts if item.get("input_tokens") is not None
    ]
    output_tokens = [
        item["output_tokens"] for item in all_attempts if item.get("output_tokens") is not None
    ]
    total_tokens = [
        item["total_tokens"] for item in all_attempts if item.get("total_tokens") is not None
    ]
    wall_times = [sum(int(item["wall_time_ms"]) for item in cell) for cell in cells]
    model_load_times = [
        int(item["model_load_time_ms"])
        for item in all_attempts
        if item.get("model_load_time_ms") is not None
    ]
    inference_times = [
        int(item["inference_time_ms"])
        for item in all_attempts
        if item.get("inference_time_ms") is not None
    ]
    verification_times = [int(item["verification_time_ms"]) for item in all_attempts]
    average_cpus = [
        float(item["resources"]["average_cpu_percent"])
        for item in all_attempts
        if item.get("resources", {}).get("average_cpu_percent") is not None
    ]
    peak_cpus = [
        float(item["resources"]["peak_cpu_percent"])
        for item in all_attempts
        if item.get("resources", {}).get("peak_cpu_percent") is not None
    ]
    average_rams = [
        int(item["resources"]["average_ram_bytes"])
        for item in all_attempts
        if item.get("resources", {}).get("average_ram_bytes") is not None
    ]
    peak_rams = [
        int(item["resources"]["peak_ram_bytes"])
        for item in all_attempts
        if item.get("resources", {}).get("peak_ram_bytes") is not None
    ]
    cpu_times = [
        float(item["resources"]["cpu_time_seconds"])
        for item in all_attempts
        if item.get("resources", {}).get("cpu_time_seconds") is not None
    ]
    tier_counts = {
        tier: sum(item["selected_tier"] == tier for item in all_attempts)
        for tier in ("FAST", "BALANCED", "BEST")
    }
    return {
        "condition": condition,
        "benchmark": benchmark,
        "n": len(cells),
        "passes_base": final_base_passes,
        "passes_plus": final_plus_passes,
        "failures_plus": len(cells) - final_plus_passes,
        "base_pass_rate": final_base_passes / len(cells),
        "plus_pass_rate": final_plus_passes / len(cells),
        "first_attempt_plus_pass_rate": sum(
            bool(item["verification"]["plus_passed"]) for item in first
        )
        / len(cells),
        "final_pass_rate_after_local_escalation": final_plus_passes / len(cells),
        "mean_task_time_ms": statistics.fmean(wall_times),
        "median_task_time_ms": statistics.median(wall_times),
        "total_task_wall_time_ms": sum(wall_times),
        "total_model_load_time_ms": (
            sum(model_load_times) if len(model_load_times) == len(all_attempts) else None
        ),
        "total_inference_time_ms": (
            sum(inference_times) if len(inference_times) == len(all_attempts) else None
        ),
        "total_verification_time_ms": sum(verification_times),
        "input_tokens": sum(input_tokens) if len(input_tokens) == len(all_attempts) else None,
        "output_tokens": sum(output_tokens) if len(output_tokens) == len(all_attempts) else None,
        "total_tokens": sum(total_tokens) if len(total_tokens) == len(all_attempts) else None,
        "mean_total_tokens": statistics.fmean(total_tokens) if total_tokens else None,
        "median_total_tokens": statistics.median(total_tokens) if total_tokens else None,
        "mean_cpu_percent": statistics.fmean(average_cpus) if average_cpus else None,
        "median_cpu_percent": statistics.median(average_cpus) if average_cpus else None,
        "peak_cpu_percent": max(peak_cpus) if peak_cpus else None,
        "mean_ram_bytes": statistics.fmean(average_rams) if average_rams else None,
        "median_ram_bytes": statistics.median(average_rams) if average_rams else None,
        "peak_ram_bytes": max(peak_rams) if peak_rams else None,
        "cpu_time_seconds": sum(cpu_times) if cpu_times else None,
        "escalation_count": sum(max(0, len(cell) - 1) for cell in cells),
        "model_invocations": tier_counts,
        "total_generation_cost_proxy": _sum_optional(
            item.get("generation_cost_proxy") for item in all_attempts
        ),
        "total_token_cost_proxy": _sum_optional(
            item.get("total_token_cost_proxy") for item in all_attempts
        ),
        "successful_tasks_per_hour": (
            final_plus_passes / (sum(wall_times) / 3_600_000) if sum(wall_times) > 0 else None
        ),
        "successful_tasks_per_1m_output_tokens": (
            final_plus_passes * 1_000_000 / sum(output_tokens)
            if output_tokens and len(output_tokens) == len(all_attempts) and sum(output_tokens) > 0
            else None
        ),
        "successful_tasks_per_1m_total_token_cost_proxy_units": _success_per_proxy(
            final_plus_passes,
            (item.get("total_token_cost_proxy") for item in all_attempts),
        ),
    }


def _budget_curve(
    attempts: list[dict[str, Any]],
    cutoffs: tuple[float, ...],
    cost_field: str,
) -> dict[str, Any]:
    if not cutoffs:
        return {"available": False, "reason": "cutoffs_missing", "points": []}
    if any(attempt.get(cost_field) is None for attempt in attempts):
        return {"available": False, "reason": "token_metrics_unavailable", "points": []}
    cumulative = 0.0
    passed: set[tuple[str, str]] = set()
    points: list[dict[str, Any]] = []
    attempt_index = 0
    for cutoff in cutoffs:
        while attempt_index < len(attempts):
            attempt = attempts[attempt_index]
            next_cost = float(attempt[cost_field])
            if cumulative + next_cost > cutoff + 1e-9:
                break
            cumulative += next_cost
            if attempt["verification"]["plus_passed"]:
                passed.add((attempt["benchmark"], attempt["task_id"]))
            attempt_index += 1
        point = {"cutoff": cutoff, "verified_plus_passes": len(passed)}
        if attempt_index == len(attempts) and cumulative < cutoff:
            point["condition_exhausted_before_cutoff"] = True
        points.append(point)
    return {"available": True, "reason": None, "points": points}


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Adaptive Workflow Local Routing Benchmark",
        "",
        f"Experiment: `{summary.get('experiment_id')}`",
        "",
        "This report evaluates Adaptive Workflow. It is not an EHMN benchmark.",
        "Base and Plus scores use the same generated completions and are not independent samples.",
        "For Adaptive, the finite EvalPlus Plus result is both the acceptance/escalation oracle and "
        "the reported endpoint; this does not evaluate an independent verifier.",
        "Adaptive may retain an earlier-tier pass and fall back to BEST, while Strong-only receives "
        "one BEST attempt. Operational final pass rates are therefore architecturally asymmetric.",
        "Model-size-weighted token values are token cost proxies, not measured FLOPs, "
        "hardware compute, energy, API usage, credits, or dollar cost.",
        "No efficiency advantage is claimed automatically; interpret budget curves together with "
        "sample-integrated CPU, RAM, and summed generation-and-verification time.",
        "",
        "## Results",
        "",
        "| Condition | Benchmark | n | Base pass rate | Plus pass rate | Escalations |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["aggregates"]:
        lines.append(
            f"| {row['condition']} | {row['benchmark']} | {row['n']} | "
            f"{row['base_pass_rate']:.4f} | {row['plus_pass_rate']:.4f} | "
            f"{row['escalation_count']} |"
        )
    telemetry_reconciliation = summary.get("telemetry_reconciliation")
    if telemetry_reconciliation:
        lines.extend(
            [
                "",
                "## Post-run telemetry reconciliation",
                "",
                f"{telemetry_reconciliation['records_applied']} attempt had token counters "
                "recovered from the checksum-bound benchmark-owned Ollama log. The raw SQLite "
                "and JSONL measurements remain unchanged; only derived token totals and cost "
                "proxies use the reconciled counters. The original attempt status and "
                "verification outcome were not changed.",
                "",
                f"Raw token coverage: {summary['raw_token_metrics_available_attempts']}/"
                f"{summary['raw_token_metrics_total_attempts']} attempts. Reconciled derived "
                f"coverage: {summary['derived_token_metrics_available_attempts']}/"
                f"{summary['attempts']} attempts. Summed generation-and-verification wall time, "
                "model-load time, inference time, "
                "generated code, and correctness were not reconstructed for the affected attempt.",
            ]
        )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "The saved paired task-level data supports later statistical analysis. This "
            "deterministic "
            "report does not fabricate significance tests. A negative or null result is retained.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_summary_csv(path: Path, summary: dict[str, Any]) -> None:
    rows = summary["aggregates"]
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    flattened: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        copy["fast_invocations"] = row["model_invocations"]["FAST"]
        copy["balanced_invocations"] = row["model_invocations"]["BALANCED"]
        copy["best_invocations"] = row["model_invocations"]["BEST"]
        del copy["model_invocations"]
        flattened.append(copy)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flattened[0]))
        writer.writeheader()
        writer.writerows(flattened)


def _token_metrics_available(attempts: list[dict[str, Any]]) -> int:
    return sum(
        attempt.get("input_tokens") is not None
        and attempt.get("output_tokens") is not None
        and attempt.get("total_tokens") is not None
        for attempt in attempts
    )


def _sum_optional(values) -> float | None:
    collected = list(values)
    if not all(value is not None for value in collected):
        return None
    return sum(float(value) for value in collected)


def _success_per_proxy(passes: int, values) -> float | None:
    total = _sum_optional(values)
    return passes * 1_000_000 / total if total is not None and total > 0 else None
