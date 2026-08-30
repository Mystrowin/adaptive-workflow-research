from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import re
import subprocess
import sys
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .budget import budget_preflight_warnings, freeze_budget
from .config import BenchmarkConfig
from .models import BenchmarkCondition, BenchmarkTask, BenchmarkTier, ModelSpec
from .ollama import DedicatedOllamaServer, OllamaLocalClient, build_generation_prompt
from .provenance import (
    download_sources,
    frozen_sources_from_json,
    load_primary_tasks,
    sha256_file,
)
from .resources import (
    WindowsJobLimit,
    detect_system_capacity,
    prerequisite_errors,
    source_tree_sha256,
)
from .router_state import load_router_state
from .store import BenchmarkStore


class PrerequisiteError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(f"- {error}" for error in errors))


def prepare_benchmark(config: BenchmarkConfig, *, repository_root: Path) -> dict[str, Any]:
    errors = prerequisite_errors(config)
    if errors:
        raise PrerequisiteError(errors)
    capacity = detect_system_capacity(config)
    frozen_router_state_sha256: str | None = None
    if config.routing_statistics_mode == "frozen":
        if config.router_state_path is None or not config.router_state_path.is_file():
            raise PrerequisiteError(
                ["frozen routing mode requires an existing checksum-validated router_state_path."]
            )
        frozen_router_state_sha256 = sha256_file(config.router_state_path)
        load_router_state(config.router_state_path)
    verification_ram_reserve = int(
        capacity.physical_ram_bytes * config.verification_overhead_ram_fraction
    )
    if config.docker_memory_bytes + verification_ram_reserve >= capacity.hard_ram_bytes:
        raise PrerequisiteError(
            ["Docker verifier memory reservation must be below the 50% physical RAM ceiling."]
        )
    prepared = config.prepared_directory
    cache = prepared / "cache"
    prepared.mkdir(parents=True, exist_ok=True)
    sources = download_sources(cache)
    docker_digest = ensure_docker_image(config)

    job: WindowsJobLimit | None = None
    if sys.platform == "win32":
        job = WindowsJobLimit(
            hard_cpu_fraction=config.hard_cpu_fraction,
            hard_memory_bytes=capacity.hard_ram_bytes,
        )
    server = DedicatedOllamaServer(config, prepared / "prepare-ollama.log", job=job)
    try:
        client = server.start()
        present = {str(item.get("name") or item.get("model") or "") for item in client.tags()}
        for model in config.models.values():
            if model not in present and f"{model}:latest" not in present:
                server.pull(model)
                present = {
                    str(item.get("name") or item.get("model") or "") for item in client.tags()
                }
        model_specs = tuple(
            client.model_spec(BenchmarkTier(tier), model) for tier, model in config.models.items()
        )
        _validate_model_specs(model_specs, config, capacity.hard_ram_bytes)
        ollama_version = client.version()

        initial_tasks = load_primary_tasks(sources)
        shuffled = list(initial_tasks)
        random.Random(config.seed).shuffle(shuffled)
        fast_spec = next(model for model in model_specs if model.tier == BenchmarkTier.FAST)
        reference_cache = prepared / "reference_token_counts.json"
        cache_key = _reference_count_cache_key(tuple(shuffled), fast_spec, config)
        reference_counts = _load_reference_count_cache(
            reference_cache, cache_key=cache_key, tasks=tuple(shuffled)
        )
        if reference_counts is None:
            reference_counts = _recover_reference_counts(
                prepared,
                tasks=tuple(shuffled),
                fast_model=fast_spec,
                config=config,
                client=client,
            )
        if reference_counts is None:
            reference_counts = {}
            total_tasks = len(shuffled)
            for index, task in enumerate(shuffled, start=1):
                reference_counts[task.identity()] = client.count_prompt_tokens(
                    fast_spec.model, task
                )
                if index == 1 or index % 25 == 0 or index == total_tasks:
                    print(
                        f"[benchmark prepare] reference prompts {index}/{total_tasks}",
                        file=sys.stderr,
                        flush=True,
                    )
        else:
            print(
                f"[benchmark prepare] reused {len(reference_counts)} validated reference counts",
                file=sys.stderr,
                flush=True,
            )
        _write_reference_count_cache(reference_cache, cache_key, reference_counts)
        tasks = tuple(
            replace(task, reference_input_tokens=reference_counts[task.identity()])
            for task in shuffled
        )
    finally:
        server.stop()
        if job is not None:
            job.close()

    budget = freeze_budget(tasks, model_specs, max_output_tokens=config.max_output_tokens)
    budget_warnings = budget_preflight_warnings(budget)
    task_file = prepared / "frozen_tasks.jsonl"
    with task_file.open("w", encoding="utf-8", newline="\n") as stream:
        for task in tasks:
            stream.write(json.dumps(asdict(task), sort_keys=True) + "\n")
    schedule = build_balanced_schedule(
        tasks,
        seed=config.seed,
        conditions=tuple(BenchmarkCondition(item) for item in config.conditions),
    )
    prepared_at = datetime.now(UTC).isoformat()
    profile: dict[str, Any] = {
        "profile_version": 1,
        "profile_kind": "primary",
        "prepared_at": prepared_at,
        "adaptive_workflow_version": "0.19.4",
        "source_tree_sha256": source_tree_sha256(repository_root),
        "repository_git_commit": None,
        "config": config.as_dict(),
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "cpu": platform.processor() or platform.machine(),
        "physical_ram_bytes": capacity.physical_ram_bytes,
        "system_capacity": asdict(capacity),
        "ollama_version": ollama_version,
        "docker_image": config.docker_image,
        "docker_image_digest": docker_digest,
        "models": [asdict(model) for model in model_specs],
        "sampling": {
            "temperature": 0,
            "top_p": 1,
            "seed": config.seed,
            "num_predict": config.max_output_tokens,
            "num_ctx": config.context_window,
            "num_thread": 1,
        },
        "benchmarks": [
            {"name": source.benchmark, "version": source.version, "license": source.license}
            for source in sources
        ],
        "task_ids": [task.identity() for task in tasks],
        "seed": config.seed,
        "resource_limits": {
            "soft_cpu_percent": capacity.soft_cpu_percent,
            "hard_cpu_percent": capacity.hard_cpu_percent,
            "soft_cpu_equivalent_for_readability": capacity.soft_cpu_equivalent,
            "hard_cpu_equivalent_for_readability": capacity.hard_cpu_equivalent,
            "soft_ram_bytes": capacity.soft_ram_bytes,
            "hard_ram_bytes": capacity.hard_ram_bytes,
            "docker_cpu_fraction_of_total": config.docker_cpu_fraction,
            "verification_overhead_cpu_fraction": (config.verification_overhead_cpu_fraction),
            "verification_overhead_ram_bytes": verification_ram_reserve,
            "docker_memory_bytes": config.docker_memory_bytes,
            "docker_pids_limit": config.docker_pids_limit,
        },
        "routing": {
            "conditions": list(config.conditions),
            "adaptive_path": [tier.value for tier in BenchmarkTier],
            "one_attempt_per_tier": True,
            "same_tier_retries": 0,
            "statistics_mode": config.routing_statistics_mode,
            "router_state_persisted": True,
            "frozen_router_state_sha256": frozen_router_state_sha256,
        },
        "verification": {
            "evaluator": "EvalPlus",
            "evaluator_version": "v0.3.1",
            "base_and_plus_same_completion": True,
            "container_network": "none",
            "timeout_seconds": config.verification_timeout_seconds,
        },
        "budget": asdict(budget),
        "budget_preflight": {
            "warnings": budget_warnings,
            "calibration_used": False,
            "note": (
                "Future held-out studies should supply a separate calibration workload "
                "before freezing cutoffs."
            ),
        },
        "frozen_tasks_file": str(task_file),
        "frozen_tasks_sha256": sha256_file(task_file),
        "benchmark_sources_file": str(cache / "benchmark_sources.json"),
        "benchmark_sources_sha256": sha256_file(cache / "benchmark_sources.json"),
        "dataset_directory": str(cache / "datasets"),
        "schedule": [
            {"task_identity": task_identity, "condition": condition.value}
            for task_identity, condition in schedule
        ],
        "exclusions": [],
    }
    print("[benchmark prepare] starting isolated two-task smoke test", file=sys.stderr, flush=True)
    profile["smoke_validation"] = _run_local_smoke(
        profile=profile,
        tasks=tasks,
        models=model_specs,
        config=config,
        repository_root=repository_root,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    profile_directory = prepared / "profiles" / f"{timestamp}-{profile['source_tree_sha256'][:12]}"
    profile_directory.mkdir(parents=True, exist_ok=False)
    versioned_path = profile_directory / "prepared_profile.json"
    encoded = json.dumps(profile, indent=2, sort_keys=True, default=str)
    versioned_path.write_text(encoded, encoding="utf-8")
    config.prepared_profile_path.write_text(encoded, encoding="utf-8")
    return profile


def build_balanced_schedule(
    tasks: tuple[BenchmarkTask, ...],
    *,
    seed: int,
    block_size: int = 16,
    conditions: tuple[BenchmarkCondition, ...] | None = None,
) -> tuple[tuple[str, BenchmarkCondition], ...]:
    selected_conditions = list(
        conditions
        or (
            BenchmarkCondition.SMALL_ONLY,
            BenchmarkCondition.STRONG_ONLY,
            BenchmarkCondition.ADAPTIVE,
        )
    )
    if not selected_conditions:
        raise ValueError("at least one benchmark condition is required")
    randomizer = random.Random(seed ^ 0xA4D4_97B3)
    schedule: list[tuple[str, BenchmarkCondition]] = []
    for offset in range(0, len(tasks), block_size):
        block = tasks[offset : offset + block_size]
        order = selected_conditions.copy()
        randomizer.shuffle(order)
        for condition in order:
            schedule.extend((task.identity(), condition) for task in block)
    expected = len(tasks) * len(selected_conditions)
    if len(schedule) != expected or len(set(schedule)) != expected:
        raise RuntimeError("balanced schedule did not produce unique task-condition cells")
    for condition in selected_conditions:
        observed = [
            identity for identity, item_condition in schedule if item_condition == condition
        ]
        if observed != [task.identity() for task in tasks]:
            raise RuntimeError("condition task order diverged from the frozen task order")
    return tuple(schedule)


def load_prepared_profile(config: BenchmarkConfig) -> dict[str, Any]:
    if not config.prepared_profile_path.is_file():
        raise FileNotFoundError(
            f"prepared profile not found: {config.prepared_profile_path}; run benchmark prepare"
        )
    profile = cast(
        dict[str, Any],
        json.loads(config.prepared_profile_path.read_text(encoding="utf-8")),
    )
    validate_prepared_profile(profile)
    return profile


def validate_prepared_profile(profile: dict[str, Any], *, allow_smoke: bool = False) -> None:
    if int(profile.get("profile_version", 0)) != 1:
        raise RuntimeError("unsupported prepared profile version")
    task_file = Path(str(profile["frozen_tasks_file"]))
    sources_file = Path(str(profile["benchmark_sources_file"]))
    if sha256_file(task_file) != profile["frozen_tasks_sha256"]:
        raise RuntimeError("frozen task file hash mismatch")
    if sha256_file(sources_file) != profile["benchmark_sources_sha256"]:
        raise RuntimeError("benchmark source manifest hash mismatch")
    profile_kind = profile.get("profile_kind", "primary")
    if profile_kind not in {"primary", "smoke"}:
        raise RuntimeError("prepared profile kind is invalid")
    if profile_kind == "smoke" and not allow_smoke:
        raise RuntimeError("a smoke profile cannot launch a primary experiment")
    expected_tasks = 2 if profile_kind == "smoke" else 542
    task_ids = profile.get("task_ids") or []
    if len(task_ids) != expected_tasks or len(set(task_ids)) != expected_tasks:
        raise RuntimeError(
            f"prepared profile must contain {expected_tasks} unique {profile_kind} tasks"
        )
    budget = profile.get("budget") or {}
    if len(budget.get("task_budgets") or ()) != expected_tasks:
        raise RuntimeError("prepared profile is missing frozen per-task budgets")
    for name in (
        "total_token_baseline_b0",
        "generation_baseline_g0",
        "total_token_cutoffs",
        "generation_cutoffs",
    ):
        if not budget.get(name):
            raise RuntimeError(f"prepared profile is missing numeric budget field {name}")
    frozen_sources_from_json(sources_file)
    if profile_kind == "primary":
        smoke = profile.get("smoke_validation") or {}
        if smoke.get("status") != "passed" or int(smoke.get("tasks", 0)) != 2:
            raise RuntimeError("prepared profile is missing a successful two-task local smoke run")


def load_frozen_tasks(profile: dict[str, Any]) -> tuple[BenchmarkTask, ...]:
    tasks: list[BenchmarkTask] = []
    with Path(str(profile["frozen_tasks_file"])).open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                tasks.append(BenchmarkTask(**json.loads(line)))
    if [task.identity() for task in tasks] != profile["task_ids"]:
        raise RuntimeError("frozen task order does not match the prepared profile")
    return tuple(tasks)


def _reference_count_cache_key(
    tasks: tuple[BenchmarkTask, ...],
    fast_model: ModelSpec,
    config: BenchmarkConfig,
) -> str:
    payload = {
        "version": 1,
        "model": fast_model.model,
        "model_digest": fast_model.digest,
        "context_window": config.context_window,
        "prompts": [
            {
                "identity": task.identity(),
                "sha256": hashlib.sha256(build_generation_prompt(task).encode("utf-8")).hexdigest(),
            }
            for task in tasks
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_reference_count_cache(
    path: Path,
    *,
    cache_key: str,
    tasks: tuple[BenchmarkTask, ...],
) -> dict[str, int] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        counts = payload["counts"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    expected = {task.identity() for task in tasks}
    if payload.get("cache_key") != cache_key or set(counts) != expected:
        return None
    if not all(isinstance(value, int) and value >= 0 for value in counts.values()):
        return None
    return {str(identity): int(value) for identity, value in counts.items()}


def _write_reference_count_cache(path: Path, cache_key: str, counts: dict[str, int]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {"version": 1, "cache_key": cache_key, "counts": counts},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _recover_reference_counts(
    prepared: Path,
    *,
    tasks: tuple[BenchmarkTask, ...],
    fast_model: ModelSpec,
    config: BenchmarkConfig,
    client: OllamaLocalClient,
) -> dict[str, int] | None:
    """Recover a completed pre-cache count pass from a failed smoke experiment."""

    frozen_path = prepared / "frozen_tasks.jsonl"
    smoke_root = prepared / "smoke"
    if not frozen_path.is_file() or not smoke_root.is_dir():
        return None
    expected_models = (fast_model.model, fast_model.digest)
    compatible_manifest = False
    for manifest_path in sorted(
        smoke_root.glob("*/experiment_manifest.json"),
        key=lambda item: item.stat().st_mtime_ns,
        reverse=True,
    ):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            frozen_fast = next(
                model for model in manifest["models"] if model["tier"] == BenchmarkTier.FAST.value
            )
            compatible_manifest = (
                frozen_fast["model"],
                frozen_fast["digest"],
            ) == expected_models and int(manifest["sampling"]["num_ctx"]) == config.context_window
        except (OSError, json.JSONDecodeError, KeyError, StopIteration, TypeError, ValueError):
            compatible_manifest = False
        if compatible_manifest:
            break
    if not compatible_manifest:
        return None
    try:
        frozen = tuple(
            BenchmarkTask(**json.loads(line))
            for line in frozen_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if len(frozen) != len(tasks):
        return None
    for current, previous in zip(tasks, frozen, strict=True):
        if replace(current, reference_input_tokens=previous.reference_input_tokens) != previous:
            return None
    counts = {task.identity(): task.reference_input_tokens for task in frozen}
    probes = (tasks[0], tasks[-1])
    if any(
        client.count_prompt_tokens(fast_model.model, task) != counts[task.identity()]
        for task in probes
    ):
        return None
    return counts


def ensure_docker_image(config: BenchmarkConfig) -> str:
    inspected = _inspect_docker_image(config)
    if inspected is not None:
        return inspected
    completed = subprocess.run(
        [config.docker_executable, "pull", config.docker_image],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=7200,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"failed to pull pinned EvalPlus image: {detail[:2000]}")
    inspected = _inspect_docker_image(config)
    if inspected is None:
        raise RuntimeError("Docker image pull completed but no local image digest was found")
    return inspected


def _inspect_docker_image(config: BenchmarkConfig) -> str | None:
    completed = subprocess.run(
        [
            config.docker_executable,
            "image",
            "inspect",
            config.docker_image,
            "--format",
            "{{json .RepoDigests}}|{{.Id}}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _validate_model_specs(
    models: tuple[ModelSpec, ...],
    config: BenchmarkConfig,
    hard_ram_bytes: int,
) -> None:
    if {model.tier for model in models} != set(BenchmarkTier):
        raise RuntimeError("three benchmark model tiers were not resolved")
    if len({model.digest for model in models}) != 3:
        raise RuntimeError("benchmark tiers resolved to fewer than three distinct model digests")
    total_download = sum(model.size_bytes or 0 for model in models)
    if total_download > config.max_model_download_bytes:
        raise RuntimeError("selected local model artifacts exceed the 30 GiB download limit")
    for model in models:
        predicted = model.predicted_memory_bytes
        if predicted is None:
            raise RuntimeError(f"model {model.model} lacks a memory-size estimate")
        if predicted > hard_ram_bytes:
            raise RuntimeError(
                f"model {model.model} is resource_blocked: predicted memory exceeds hard RAM cap"
            )


def new_experiment_id(seed: int) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"awb-{timestamp}-s{seed}-{uuid.uuid4().hex[:8]}"


def _run_local_smoke(
    *,
    profile: dict[str, Any],
    tasks: tuple[BenchmarkTask, ...],
    models: tuple[ModelSpec, ...],
    config: BenchmarkConfig,
    repository_root: Path,
) -> dict[str, Any]:
    selected = (
        next(task for task in tasks if task.benchmark == "humaneval"),
        next(task for task in tasks if task.benchmark == "mbpp"),
    )
    smoke_id = f"smoke-{uuid.uuid4().hex[:12]}"
    directory = config.prepared_directory / "smoke" / smoke_id
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "logs").mkdir()
    (directory / "task_workspaces").mkdir()
    smoke_tasks = directory / "frozen_tasks.jsonl"
    with smoke_tasks.open("w", encoding="utf-8", newline="\n") as stream:
        for task in selected:
            stream.write(json.dumps(asdict(task), sort_keys=True) + "\n")
    smoke_budget = freeze_budget(selected, models, max_output_tokens=config.max_output_tokens)
    schedule = build_balanced_schedule(selected, seed=config.seed, block_size=2)
    manifest = {
        **profile,
        "profile_kind": "smoke",
        "experiment_id": smoke_id,
        "status": "prepared",
        "created_at": datetime.now(UTC).isoformat(),
        "started_at": None,
        "ended_at": None,
        "task_ids": [task.identity() for task in selected],
        "budget": asdict(smoke_budget),
        "schedule": [
            {"task_identity": identity, "condition": condition.value}
            for identity, condition in schedule
        ],
        "frozen_tasks_file": str(smoke_tasks),
        "frozen_tasks_sha256": sha256_file(smoke_tasks),
        "private_raw_results_directory": str(directory),
        "publishable_results_directory": None,
    }
    manifest_path = directory / "experiment_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (directory / "benchmark_sources.json").write_bytes(
        Path(str(profile["benchmark_sources_file"])).read_bytes()
    )
    (directory / "raw_results.jsonl").touch(exist_ok=False)
    with BenchmarkStore(directory / "results.sqlite") as store:
        store.create_experiment(
            experiment_id=smoke_id,
            manifest_path=manifest_path,
            private_directory=directory,
            publishable_directory=directory / "not-publishable",
            tasks=selected,
            schedule=schedule,
        )
    command = [
        sys.executable,
        "-m",
        "agents.adaptive_workflow.benchmark.cli",
        "_worker",
        "--experiment-directory",
        str(directory),
    ]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
    completed = subprocess.run(
        command,
        cwd=repository_root,
        env=_local_only_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=7200,
        check=False,
        creationflags=creationflags,
    )
    with BenchmarkStore(directory / "results.sqlite", read_only=True) as store:
        status = store.status()
        attempts = store.all_attempts()
    if completed.returncode != 0 or status["status"] != "completed":
        last_attempt = attempts[-1] if attempts else {}
        verification = last_attempt.get("verification") or {}
        resources = last_attempt.get("resources") or {}
        detail = (
            completed.stderr
            or completed.stdout
            or status.get("error")
            or verification.get("error")
            or "; ".join(resources.get("resource_limit_events") or ())
            or f"worker ended with status {status['status']}"
        )
        raise RuntimeError(f"two-task local smoke validation failed: {str(detail)[:2000]}")
    return {
        "status": "passed",
        "tasks": 2,
        "task_condition_cells": 6,
        "experiment_id": smoke_id,
        "completed_at": datetime.now(UTC).isoformat(),
    }


def _local_only_environment() -> dict[str, str]:
    prohibited = re.compile(
        r"(?i)(?:OPENAI|CODEX|ANTHROPIC|GOOGLE_API|AZURE|AWS_|TOKEN|SECRET|PASSWORD|COOKIE)"
    )
    environment = {
        key: value for key, value in os.environ.items() if prohibited.search(key) is None
    }
    environment.update(
        {
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "ADAPTIVE_WORKFLOW_BENCHMARK_LOCAL_ONLY": "1",
            "OLLAMA_NO_CLOUD": "1",
        }
    )
    return environment
