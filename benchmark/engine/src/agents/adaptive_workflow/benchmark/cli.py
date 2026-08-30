from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from .audit import write_audit_artifacts
from .config import BenchmarkConfig
from .exporter import export_publishable
from .lifecycle import (
    experiment_status,
    launch_detached,
    list_experiments,
    request_stop,
    resolve_experiment_directory,
)
from .preparation import PrerequisiteError, prepare_benchmark
from .reconciliation import create_log_token_reconciliation
from .reporting import generate_reports
from .store import BenchmarkStore
from .worker import run_worker


def add_benchmark_parser(subparsers: Any) -> argparse.ArgumentParser:
    parser = cast(
        argparse.ArgumentParser,
        subparsers.add_parser("benchmark", help="Run the local-only Adaptive Workflow benchmark."),
    )
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--publishable-root", type=Path)
    commands = parser.add_subparsers(dest="benchmark_command", required=True)

    commands.add_parser("prepare", help="Freeze local models, datasets, licenses, and budgets.")
    run = commands.add_parser("run", help="Create and launch a benchmark experiment.")
    run.add_argument("--detached", action="store_true", required=True)

    status = commands.add_parser("status", help="Read benchmark progress without modifying it.")
    status.add_argument("experiment_id", nargs="?")

    results = commands.add_parser("results", help="Read deterministic saved results.")
    results.add_argument("experiment_id")

    audit = commands.add_parser(
        "audit", help="Run a read-only scientific-validity audit of a completed experiment."
    )
    audit.add_argument("experiment_id")
    audit.add_argument("--output-dir", type=Path)

    reconcile = commands.add_parser(
        "reconcile-telemetry",
        help="Rebuild derived reports from checksum-bound local runtime telemetry.",
    )
    reconcile.add_argument("experiment_id")
    reconcile.add_argument("--benchmark", required=True)
    reconcile.add_argument("--task-id", required=True)
    reconcile.add_argument("--condition", required=True)
    reconcile.add_argument("--attempt-number", required=True, type=int)
    reconcile.add_argument("--input-tokens", required=True, type=int)
    reconcile.add_argument("--output-tokens", required=True, type=int)
    reconcile.add_argument("--source-log", default="logs/ollama.log")
    reconcile.add_argument("--evidence-start-line", required=True, type=int)
    reconcile.add_argument("--evidence-end-line", required=True, type=int)

    stop = commands.add_parser("stop", help="Request a graceful checkpointed stop.")
    stop.add_argument("experiment_id")

    resume = commands.add_parser("resume", help="Resume an incomplete experiment detached.")
    resume.add_argument("experiment_id")

    export = commands.add_parser(
        "export-publishable", help="Create a sanitized, versioned publishable result bundle."
    )
    export.add_argument("--experiment", required=True, dest="experiment_id")

    return parser


def run_benchmark_command(args: argparse.Namespace, *, repository_root: Path) -> int:
    config = _config_from_args(args)
    command = args.benchmark_command
    try:
        if command == "prepare":
            profile = prepare_benchmark(config, repository_root=repository_root)
            _print_json(
                {
                    "status": "prepared",
                    "prepared_profile": str(config.prepared_profile_path),
                    "tasks": len(profile["task_ids"]),
                    "models": profile["models"],
                    "budget": profile["budget"],
                }
            )
            return 0
        if command == "run":
            launched = launch_detached(config, repository_root=repository_root)
            _print_json(_launch_envelope(config, launched))
            return 0
        if command == "resume":
            launched = launch_detached(
                config,
                repository_root=repository_root,
                experiment_id=args.experiment_id,
            )
            _print_json(_launch_envelope(config, launched))
            return 0
        if command == "status":
            if args.experiment_id:
                _print_json(experiment_status(config, args.experiment_id))
            else:
                _print_json({"experiments": list_experiments(config)})
            return 0
        if command == "stop":
            _print_json(request_stop(config, args.experiment_id))
            return 0
        if command == "results":
            directory = resolve_experiment_directory(config, args.experiment_id)
            summary_path = directory / "summary.json"
            if summary_path.is_file():
                _print_json(json.loads(summary_path.read_text(encoding="utf-8")))
            else:
                with BenchmarkStore(directory / "results.sqlite", read_only=True) as store:
                    _print_json({"status": store.status(), "summary": None})
            return 0
        if command == "audit":
            directory = resolve_experiment_directory(config, args.experiment_id)
            json_path, markdown_path, audit_result = write_audit_artifacts(
                directory, output_directory=args.output_dir
            )
            _print_json(
                {
                    "status": "audited",
                    "experiment_id": args.experiment_id,
                    "audit_json": str(json_path),
                    "audit_markdown": str(markdown_path),
                    "historical_records_modified": False,
                    "tasks": audit_result["integrity"]["tasks"],
                    "attempts": audit_result["integrity"]["attempts_raw"],
                }
            )
            return 0
        if command == "reconcile-telemetry":
            directory = resolve_experiment_directory(config, args.experiment_id)
            manifest = json.loads(
                (directory / "experiment_manifest.json").read_text(encoding="utf-8")
            )
            with BenchmarkStore(directory / "results.sqlite", read_only=True) as store:
                status = store.status()
                if status["status"] != "completed":
                    raise RuntimeError("telemetry reconciliation requires a completed experiment")
                reconciliation_path = create_log_token_reconciliation(
                    experiment_directory=directory,
                    manifest=manifest,
                    attempts=store.all_attempts(),
                    benchmark=args.benchmark,
                    task_id=args.task_id,
                    condition=args.condition,
                    attempt_number=args.attempt_number,
                    input_tokens=args.input_tokens,
                    output_tokens=args.output_tokens,
                    source_log=args.source_log,
                    evidence_start_line=args.evidence_start_line,
                    evidence_end_line=args.evidence_end_line,
                )
                summary = generate_reports(store, directory, manifest)
            _print_json(
                {
                    "status": "telemetry_reconciled",
                    "experiment_id": args.experiment_id,
                    "reconciliation_file": reconciliation_path.name,
                    "raw_measurements_unchanged": True,
                    "token_metrics_complete": summary["token_metrics_complete"],
                }
            )
            return 0
        if command == "export-publishable":
            directory = resolve_experiment_directory(config, args.experiment_id)
            exported = export_publishable(
                experiment_id=args.experiment_id,
                experiment_directory=directory,
                publishable_root=config.publishable_root,
            )
            _print_json({"status": "passed", "publishable_directory": str(exported)})
            return 0
        if command == "_worker":
            return run_worker(args.experiment_directory)
    except PrerequisiteError as exc:
        _print_json(
            {
                "status": "prerequisite_missing",
                "errors": exc.errors,
                "system_software_was_installed": False,
            }
        )
        return 2
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 2
    raise RuntimeError(f"unknown benchmark command: {command}")


def _config_from_args(args: argparse.Namespace) -> BenchmarkConfig:
    values: dict[str, Any] = {}
    private_root = getattr(args, "private_root", None)
    publishable_root = getattr(args, "publishable_root", None)
    if private_root is not None:
        values["private_root"] = private_root
    if publishable_root is not None:
        values["publishable_root"] = publishable_root
    return BenchmarkConfig(**values)


def _launch_envelope(config: BenchmarkConfig, launched: dict[str, Any]) -> dict[str, Any]:
    experiment_id = launched["experiment_id"]
    prefix = "python -m agents.adaptive_workflow benchmark"
    return {
        **launched,
        "status_command": f"{prefix} status {experiment_id}",
        "stop_command": f"{prefix} stop {experiment_id}",
        "resume_command": f"{prefix} resume {experiment_id}",
        "export_command": f"{prefix} export-publishable --experiment {experiment_id}",
        "codex_monitoring_required": False,
        "publishable_root": str(config.publishable_root),
    }


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "_worker":
        worker_parser = argparse.ArgumentParser(add_help=False)
        worker_parser.add_argument("_worker")
        worker_parser.add_argument("--experiment-directory", required=True, type=Path)
        worker_args = worker_parser.parse_args(raw)
        return run_worker(worker_args.experiment_directory)
    parser = argparse.ArgumentParser(prog="python -m agents.adaptive_workflow.benchmark.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_benchmark_parser(subparsers)
    if raw and raw[0] != "benchmark":
        raw.insert(0, "benchmark")
    args = parser.parse_args(raw)
    return run_benchmark_command(args, repository_root=Path.cwd().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
