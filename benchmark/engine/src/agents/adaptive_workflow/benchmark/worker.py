from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from ..statistics import RoutingStatistics
from .budget import generation_cost_proxy, total_token_cost_proxy
from .config import BenchmarkConfig
from .models import (
    AttemptRecord,
    AttemptStatus,
    BenchmarkCondition,
    BenchmarkTask,
    BenchmarkTier,
    ExperimentStatus,
    ModelSpec,
    ResourceMetrics,
    VerificationOutcome,
    classify_failure,
)
from .ollama import (
    DedicatedOllamaServer,
    OllamaLocalClient,
    build_system_prompt,
    normalize_solution,
)
from .preparation import validate_prepared_profile
from .reporting import generate_reports
from .resources import (
    ProcessTreeMonitor,
    WindowsJobLimit,
    detect_system_capacity,
    source_tree_sha256,
)
from .router import BenchmarkRoute, BenchmarkRouter
from .store import BenchmarkStore, utc_now
from .verifier import DockerEvalPlusVerifier


def run_worker(experiment_directory: Path) -> int:
    directory = experiment_directory.resolve()
    manifest_path = directory / "experiment_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_prepared_profile(manifest, allow_smoke=True)
    repository_root = Path(__file__).resolve().parents[4]
    if source_tree_sha256(repository_root) != manifest["source_tree_sha256"]:
        raise RuntimeError("Adaptive Workflow source tree changed after benchmark preparation")
    experiment_id = str(manifest["experiment_id"])
    config = BenchmarkConfig.from_dict(dict(manifest["config"]))
    if config.routing_statistics_mode == "frozen":
        if config.router_state_path is None or not config.router_state_path.is_file():
            raise RuntimeError("frozen routing mode requires a prepared router_state_path")
        expected_state_hash = manifest.get("routing", {}).get("frozen_router_state_sha256")
        if expected_state_hash:
            from .provenance import sha256_file

            if sha256_file(config.router_state_path) != expected_state_hash:
                raise RuntimeError("frozen router state changed after benchmark preparation")
    if os.environ.get("ADAPTIVE_WORKFLOW_BENCHMARK_LOCAL_ONLY") != "1":
        raise RuntimeError("detached benchmark worker requires the local-only environment guard")
    lock_path = directory / ".worker.lock"
    lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(lock_descriptor, str(os.getpid()).encode("ascii"))
    os.close(lock_descriptor)

    database_path = directory / "results.sqlite"
    capacity = detect_system_capacity(config)
    job: WindowsJobLimit | None = None
    server: DedicatedOllamaServer | None = None
    heartbeat_stop = threading.Event()
    heartbeat: threading.Thread | None = None
    final_status = ExperimentStatus.FAILED
    error: str | None = None
    try:
        if sys.platform == "win32":
            job = WindowsJobLimit(
                hard_cpu_fraction=config.hard_cpu_fraction,
                hard_memory_bytes=capacity.hard_ram_bytes,
            )
            job.assign_pid(os.getpid())
        server = DedicatedOllamaServer(config, directory / "logs" / "ollama.log")
        client = server.start()
        models = _load_and_validate_models(manifest, client, capacity.hard_ram_bytes)
        verifier = DockerEvalPlusVerifier(
            config,
            capacity,
            dataset_directory=Path(str(manifest["dataset_directory"])),
        )
        if verifier.image_digest != manifest["docker_image_digest"]:
            raise RuntimeError("pinned EvalPlus Docker image changed after preparation")
        statistics = RoutingStatistics()
        with BenchmarkStore(database_path) as store:
            recovered_raw_records = store.synchronize_raw_results(directory / "raw_results.jsonl")
            if recovered_raw_records:
                store.record_event(
                    "raw_results_recovered", {"records_appended": recovered_raw_records}
                )
            if config.routing_statistics_mode == "online":
                _load_routing_history(store.all_attempts(), statistics)
            elif config.router_state_path is not None and config.router_state_path.is_file():
                from .router_state import load_router_state

                statistics.load_rows(load_router_state(config.router_state_path))
            from .router_state import save_router_state

            router_state_path = directory / "router_state.json"
            initial_router_state_hash = save_router_state(router_state_path, statistics)
            store.record_event(
                "router_state_started",
                {
                    "mode": config.routing_statistics_mode,
                    "sha256": initial_router_state_hash,
                },
            )
            router = BenchmarkRouter(statistics)
            store.set_status(experiment_id, ExperimentStatus.RUNNING, worker_pid=os.getpid())
            _update_manifest_status(manifest_path, ExperimentStatus.RUNNING.value, started=True)
            heartbeat = threading.Thread(
                target=_heartbeat_loop,
                args=(
                    database_path,
                    experiment_id,
                    os.getpid(),
                    config.heartbeat_seconds,
                    heartbeat_stop,
                ),
                name="adaptive-benchmark-heartbeat",
                daemon=True,
            )
            heartbeat.start()
            outcome = _run_cells(
                store=store,
                experiment_id=experiment_id,
                directory=directory,
                manifest=manifest,
                config=config,
                client=client,
                verifier=verifier,
                router=router,
                statistics=statistics,
                models=models,
                capacity=capacity,
                native_job=job,
                router_state_path=directory / "router_state.json",
            )
            final_router_state_hash = save_router_state(router_state_path, statistics)
            store.record_event(
                "router_state_finished",
                {
                    "mode": config.routing_statistics_mode,
                    "sha256": final_router_state_hash,
                },
            )
            final_status = outcome
            store.set_status(experiment_id, final_status, worker_pid=os.getpid())
            _update_manifest_status(manifest_path, final_status.value, ended=True)
            refreshed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            generate_reports(store, directory, refreshed_manifest)
        return 0 if final_status in {ExperimentStatus.COMPLETED, ExperimentStatus.STOPPED} else 2
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        try:
            with BenchmarkStore(database_path) as store:
                store.set_status(
                    experiment_id,
                    ExperimentStatus.FAILED,
                    worker_pid=os.getpid(),
                    error=error,
                )
                _update_manifest_status(manifest_path, ExperimentStatus.FAILED.value, ended=True)
                generate_reports(
                    store,
                    directory,
                    json.loads(manifest_path.read_text(encoding="utf-8")),
                )
        except BaseException:
            pass
        return 2
    finally:
        heartbeat_stop.set()
        if heartbeat is not None:
            heartbeat.join(timeout=5)
        if server is not None:
            server.stop()
        if job is not None:
            job.close()
        state = {
            "experiment_id": experiment_id,
            "pid": os.getpid(),
            "status": final_status.value if error is None else ExperimentStatus.FAILED.value,
            "recorded_at": utc_now(),
            "error": error,
        }
        (directory / "worker_state.json").write_text(
            json.dumps(state, indent=2, sort_keys=True), encoding="utf-8"
        )
        lock_path.unlink(missing_ok=True)


def _run_cells(
    *,
    store: BenchmarkStore,
    experiment_id: str,
    directory: Path,
    manifest: dict[str, Any],
    config: BenchmarkConfig,
    client: OllamaLocalClient,
    verifier: DockerEvalPlusVerifier,
    router: BenchmarkRouter,
    statistics: RoutingStatistics,
    models: dict[BenchmarkTier, ModelSpec],
    capacity,
    native_job: WindowsJobLimit | None,
    router_state_path: Path | None = None,
) -> ExperimentStatus:
    budget_by_task = {item["task_identity"]: item for item in manifest["budget"]["task_budgets"]}
    while True:
        if store.stop_requested(experiment_id):
            return ExperimentStatus("stopped")
        cell = store.next_cell()
        if cell is None:
            return ExperimentStatus("completed")
        task = BenchmarkTask(
            benchmark=str(cell["benchmark"]),
            benchmark_version=str(cell["benchmark_version"]),
            task_id=str(cell["task_id"]),
            prompt=str(cell["prompt"]),
            entry_point=str(cell["entry_point"]),
            reference_input_tokens=int(cell["reference_input_tokens"]),
            source_sha256=str(cell["source_sha256"]),
        )
        condition = BenchmarkCondition(str(cell["condition"]))
        prior = store.attempts_for_cell(task.identity(), condition.value)
        if prior and prior[-1]["verification"]["plus_passed"]:
            store.complete_cell(task.identity(), condition.value, AttemptStatus.PASSED.value)
            continue
        route = _route_for_cell(router, condition, task, prior)
        cascade = condition in {
            BenchmarkCondition.ADAPTIVE,
            BenchmarkCondition.FIXED_CASCADE,
        }
        path = (route.tier,) if not cascade else BenchmarkRouter.escalation_path(route.tier)
        attempted_tiers = [BenchmarkTier(item["selected_tier"]) for item in prior]
        remaining = [tier for tier in path if tier not in attempted_tiers]
        if not remaining:
            final = prior[-1]["status"] if prior else AttemptStatus.FAILED.value
            store.complete_cell(task.identity(), condition.value, final)
            continue
        if prior and not cascade:
            store.complete_cell(task.identity(), condition.value, prior[-1]["status"])
            continue
        if prior and prior[-1]["status"] in {
            AttemptStatus.MODEL_ERROR.value,
            AttemptStatus.VERIFIER_ERROR.value,
            AttemptStatus.RESOURCE_BLOCKED.value,
        }:
            store.complete_cell(task.identity(), condition.value, prior[-1]["status"])
            continue

        tier = remaining[0]
        model = models[tier]
        task_budget = budget_by_task[task.identity()]
        reserved = sum(float(task_budget["reservations"][item.value]) for item in attempted_tiers)
        next_reservation = float(task_budget["reservations"][tier.value])
        if reserved + next_reservation > float(task_budget["adaptive_limit"]) + 1e-9:
            record = _non_execution_record(
                experiment_id,
                task,
                condition,
                tier,
                model,
                prior,
                route,
                config.seed,
                AttemptStatus.RESOURCE_BLOCKED,
                "frozen Adaptive operational cost-proxy limit would be exceeded",
            )
            store.record_attempt(record, directory / "raw_results.jsonl")
            store.complete_cell(task.identity(), condition.value, record.status.value)
            continue
        if model.predicted_memory_bytes is None or not _model_fits_now(
            model.predicted_memory_bytes, capacity.hard_ram_bytes
        ):
            record = _non_execution_record(
                experiment_id,
                task,
                condition,
                tier,
                model,
                prior,
                route,
                config.seed,
                AttemptStatus.RESOURCE_BLOCKED,
                "predicted model memory does not fit the hard process-tree RAM ceiling",
            )
            store.record_attempt(record, directory / "raw_results.jsonl")
            store.complete_cell(task.identity(), condition.value, record.status.value)
            continue

        attempt_started = utc_now()
        baseline_ram = _current_tree_ram(os.getpid())
        monitor = ProcessTreeMonitor(os.getpid(), capacity)
        monitor.start()
        try:
            generation = client.generate(model.model, task)
            generation_resources = monitor.stop()
        except BaseException as exc:
            generation_resources = monitor.stop()
            record = _non_execution_record(
                experiment_id,
                task,
                condition,
                tier,
                model,
                prior,
                route,
                config.seed,
                AttemptStatus.MODEL_ERROR,
                str(exc),
                resources=generation_resources,
                started_at=attempt_started,
            )
            store.record_attempt(record, directory / "raw_results.jsonl")
            store.complete_cell(task.identity(), condition.value, record.status.value)
            continue

        try:
            client.unload(model.model)
            verification_native_memory = min(
                capacity.soft_ram_bytes,
                capacity.hard_ram_bytes
                - config.docker_memory_bytes
                - int(capacity.physical_ram_bytes * config.verification_overhead_ram_fraction),
            )
            if verification_native_memory <= 0:
                raise RuntimeError("Docker memory reservation leaves no native benchmark budget")
            _wait_for_memory_release(os.getpid(), verification_native_memory, timeout_seconds=30)
        except BaseException as exc:
            record = _non_execution_record(
                experiment_id,
                task,
                condition,
                tier,
                model,
                prior,
                route,
                config.seed,
                AttemptStatus.RESOURCE_BLOCKED,
                str(exc),
                resources=generation_resources,
                started_at=attempt_started,
            )
            store.record_attempt(record, directory / "raw_results.jsonl")
            store.complete_cell(task.identity(), condition.value, record.status.value)
            continue
        solution, normalization = normalize_solution(task, generation.text)
        verification_monitor = ProcessTreeMonitor(os.getpid(), capacity)
        verification_monitor.start()
        try:
            if native_job is not None:
                native_job.set_cpu_fraction(
                    config.hard_cpu_fraction
                    - config.docker_cpu_fraction
                    - config.verification_overhead_cpu_fraction
                )
                native_job.set_memory_limit(verification_native_memory)
            verification = verifier.verify(
                task,
                solution,
                identifier=(
                    f"{experiment_id}:{condition.value}:{task.identity()}:{len(prior) + 1}"
                ),
            )
            native_verification_resources = verification_monitor.stop()
        except BaseException as exc:
            native_verification_resources = verification_monitor.stop()
            record = _non_execution_record(
                experiment_id,
                task,
                condition,
                tier,
                model,
                prior,
                route,
                config.seed,
                AttemptStatus.VERIFIER_ERROR,
                str(exc),
                resources=_combine_metrics(
                    generation_resources,
                    native_verification_resources,
                    baseline_ram=baseline_ram,
                ),
                started_at=attempt_started,
            )
            store.record_attempt(record, directory / "raw_results.jsonl")
            store.complete_cell(task.identity(), condition.value, record.status.value)
            continue
        finally:
            if native_job is not None:
                native_job.set_memory_limit(capacity.hard_ram_bytes)
                native_job.set_cpu_fraction(config.hard_cpu_fraction)
        verification_resources = _sum_concurrent_metrics(
            native_verification_resources,
            verification.resources,
            capacity=capacity,
        )
        combined = _combine_metrics(
            generation_resources,
            verification_resources,
            baseline_ram=baseline_ram,
        )
        hard_violation = bool(
            {
                "cpu_hard_ceiling_observed",
                "ram_hard_ceiling_observed",
            }
            & set(combined.resource_limit_events)
        )
        if hard_violation:
            attempt_status = AttemptStatus.RESOURCE_VIOLATION
        elif verification.outcome.status == "verifier_error":
            attempt_status = AttemptStatus.VERIFIER_ERROR
        elif verification.outcome.plus_passed:
            attempt_status = AttemptStatus.PASSED
        else:
            attempt_status = AttemptStatus.FAILED
        ended = utc_now()
        record = AttemptRecord(
            experiment_id=experiment_id,
            benchmark=task.benchmark,
            benchmark_version=task.benchmark_version,
            task_id=task.task_id,
            condition=condition,
            selected_tier=tier,
            selected_model=model.model,
            route=tuple(item.value for item in path),
            attempt_number=len(prior) + 1,
            start_time=attempt_started,
            end_time=ended,
            status=attempt_status,
            verification=verification.outcome,
            resources=combined,
            input_tokens=generation.input_tokens,
            output_tokens=generation.output_tokens,
            total_tokens=generation.total_tokens,
            generation_cost_proxy=generation_cost_proxy(model, generation.output_tokens),
            total_token_cost_proxy=total_token_cost_proxy(
                model, generation.input_tokens, generation.output_tokens
            ),
            wall_time_ms=generation.wall_time_ms + verification.outcome.duration_ms,
            model_load_time_ms=generation.model_load_time_ms,
            inference_time_ms=generation.inference_time_ms,
            verification_time_ms=verification.outcome.duration_ms,
            router_confidence=route.confidence,
            router_reason=(
                route.reason if not prior else f"{route.reason};verification-failed-escalation"
            ),
            seed=config.seed,
            escalation_path=tuple(item["selected_tier"] for item in prior) + (tier.value,),
            provider_metadata={
                **generation.metadata,
                "normalization": list(normalization),
                "docker_image_digest": verification.image_digest,
            },
            generated_output=generation.text,
            generated_output_sha256=hashlib.sha256(generation.text.encode("utf-8")).hexdigest(),
            prompt_sha256=hashlib.sha256(task.prompt.encode("utf-8")).hexdigest(),
            system_prompt_sha256=hashlib.sha256(
                build_system_prompt(task).encode("utf-8")
            ).hexdigest(),
            generation_template_version="benchmark-generation-prompt-v1",
            model_digest=model.digest,
            verifier_invocation={
                "evaluator": "EvalPlus",
                "image_digest": verification.image_digest,
                "identifier": (
                    f"{experiment_id}:{condition.value}:{task.identity()}:{len(prior) + 1}"
                ),
            },
            failure_class=classify_failure(
                attempt_status.value,
                verification.outcome,
                generation.text,
            ),
        )
        store.record_attempt(record, directory / "raw_results.jsonl")
        store.record_resource_sample(
            task_identity=task.identity(),
            condition=condition.value,
            attempt_number=record.attempt_number,
            cpu_percent=combined.peak_cpu_percent,
            ram_bytes=combined.peak_ram_bytes,
            ram_percent=combined.peak_ram_percent,
            source="attempt-peak",
        )
        if condition == BenchmarkCondition.ADAPTIVE:
            logical_tier = {
                BenchmarkTier.FAST: "Luna",
                BenchmarkTier.BALANCED: "Terra",
                BenchmarkTier.BEST: "Sol",
            }[tier]
            statistics.record(
                "function_synthesis",
                logical_tier,
                "medium",
                "ollama",
                "single_agent",
                completed=True,
                verified=verification.outcome.plus_passed,
                latency_ms=record.wall_time_ms,
                tokens=record.total_tokens or 0,
                cost=record.total_token_cost_proxy,
            )
            if router_state_path is not None:
                from .router_state import save_router_state

                save_router_state(router_state_path, statistics)
        if hard_violation:
            store.complete_cell(task.identity(), condition.value, record.status.value)
            return ExperimentStatus("resource_violation")
        if attempt_status == AttemptStatus.PASSED:
            store.complete_cell(task.identity(), condition.value, record.status.value)
        elif attempt_status in {
            AttemptStatus.MODEL_ERROR,
            AttemptStatus.VERIFIER_ERROR,
            AttemptStatus.RESOURCE_BLOCKED,
        }:
            # Infrastructure failures are terminal for this task-condition cell.
            # Escalating them could turn a harness failure into a misleading pass.
            store.complete_cell(task.identity(), condition.value, record.status.value)
        elif not cascade or tier == path[-1]:
            store.complete_cell(task.identity(), condition.value, record.status.value)


def _route_for_cell(
    router: BenchmarkRouter,
    condition: BenchmarkCondition,
    task: BenchmarkTask,
    prior: list[dict[str, Any]],
) -> BenchmarkRoute:
    if prior:
        return BenchmarkRoute(
            tier=BenchmarkTier(prior[0]["selected_tier"]),
            confidence=float(prior[0]["router_confidence"]),
            reason=str(prior[0]["router_reason"]).split(";verification-failed-escalation", 1)[0],
        )
    return router.initial_route(condition, task)


def _non_execution_record(
    experiment_id: str,
    task: BenchmarkTask,
    condition: BenchmarkCondition,
    tier: BenchmarkTier,
    model: ModelSpec,
    prior: list[dict[str, Any]],
    route: BenchmarkRoute,
    seed: int,
    status: AttemptStatus,
    error: str,
    *,
    resources: ResourceMetrics | None = None,
    started_at: str | None = None,
) -> AttemptRecord:
    timestamp = started_at or utc_now()
    path: tuple[BenchmarkTier, ...] = (tier,)
    if condition in {BenchmarkCondition.ADAPTIVE, BenchmarkCondition.FIXED_CASCADE}:
        path = BenchmarkRouter.escalation_path(route.tier)
    return AttemptRecord(
        experiment_id=experiment_id,
        benchmark=task.benchmark,
        benchmark_version=task.benchmark_version,
        task_id=task.task_id,
        condition=condition,
        selected_tier=tier,
        selected_model=model.model,
        route=tuple(item.value for item in path),
        attempt_number=len(prior) + 1,
        start_time=timestamp,
        end_time=utc_now(),
        status=status,
        verification=VerificationOutcome(
            status="not_run",
            base_status="not_run",
            plus_status="not_run",
            base_passed=False,
            plus_passed=False,
            duration_ms=0,
            error=error,
        ),
        resources=resources or ResourceMetrics(),
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        generation_cost_proxy=None,
        total_token_cost_proxy=None,
        wall_time_ms=0,
        model_load_time_ms=None,
        inference_time_ms=None,
        verification_time_ms=0,
        router_confidence=route.confidence,
        router_reason=route.reason,
        seed=seed,
        error=error,
        escalation_path=tuple(item["selected_tier"] for item in prior) + (tier.value,),
        prompt_sha256=hashlib.sha256(task.prompt.encode("utf-8")).hexdigest(),
        system_prompt_sha256=hashlib.sha256(build_system_prompt(task).encode("utf-8")).hexdigest(),
        generation_template_version="benchmark-generation-prompt-v1",
        model_digest=model.digest,
        failure_class=classify_failure(status.value),
    )


def _load_and_validate_models(
    manifest: dict[str, Any],
    client: OllamaLocalClient,
    hard_ram_bytes: int,
) -> dict[BenchmarkTier, ModelSpec]:
    expected = {
        BenchmarkTier(item["tier"]): ModelSpec(
            **{
                **item,
                "tier": BenchmarkTier(item["tier"]),
            }
        )
        for item in manifest["models"]
    }
    actual: dict[BenchmarkTier, ModelSpec] = {}
    for tier, frozen in expected.items():
        current = client.model_spec(tier, frozen.model)
        if current.digest != frozen.digest:
            raise RuntimeError(f"local model digest changed after preparation: {frozen.model}")
        if (
            current.predicted_memory_bytes is None
            or current.predicted_memory_bytes > hard_ram_bytes
        ):
            raise RuntimeError(f"local model is resource_blocked: {frozen.model}")
        actual[tier] = current
    return actual


def _load_routing_history(attempts: list[dict[str, Any]], statistics: RoutingStatistics) -> None:
    logical = {"FAST": "Luna", "BALANCED": "Terra", "BEST": "Sol"}
    for attempt in attempts:
        if attempt["condition"] != BenchmarkCondition.ADAPTIVE.value:
            continue
        statistics.record(
            "function_synthesis",
            logical[attempt["selected_tier"]],
            "medium",
            "ollama",
            "single_agent",
            completed=True,
            verified=bool(attempt["verification"]["plus_passed"]),
            latency_ms=float(attempt["wall_time_ms"]),
            tokens=int(attempt.get("total_tokens") or 0),
            cost=attempt.get("total_token_cost_proxy"),
        )


def _combine_metrics(
    generation: ResourceMetrics,
    verification: ResourceMetrics,
    *,
    baseline_ram: int,
) -> ResourceMetrics:
    averages_cpu = [
        value
        for value in (generation.average_cpu_percent, verification.average_cpu_percent)
        if value is not None
    ]
    averages_ram = [
        value
        for value in (generation.average_ram_bytes, verification.average_ram_bytes)
        if value is not None
    ]
    peaks_cpu = [
        value
        for value in (generation.peak_cpu_percent, verification.peak_cpu_percent)
        if value is not None
    ]
    peaks_ram = [
        value
        for value in (generation.peak_ram_bytes, verification.peak_ram_bytes)
        if value is not None
    ]
    peak_ram_percent = [
        value
        for value in (generation.peak_ram_percent, verification.peak_ram_percent)
        if value is not None
    ]
    model_load_memory = (
        max(0, int(generation.peak_ram_bytes) - baseline_ram)
        if generation.peak_ram_bytes is not None
        else None
    )
    return ResourceMetrics(
        average_cpu_percent=sum(averages_cpu) / len(averages_cpu) if averages_cpu else None,
        peak_cpu_percent=max(peaks_cpu) if peaks_cpu else None,
        average_ram_bytes=int(sum(averages_ram) / len(averages_ram)) if averages_ram else None,
        peak_ram_bytes=max(peaks_ram) if peaks_ram else None,
        peak_ram_percent=max(peak_ram_percent) if peak_ram_percent else None,
        model_load_memory_bytes=model_load_memory,
        cpu_time_seconds=_sum_optional_metrics(
            generation.cpu_time_seconds, verification.cpu_time_seconds
        ),
        resource_limit_events=tuple(
            sorted(set(generation.resource_limit_events) | set(verification.resource_limit_events))
        ),
    )


def _sum_concurrent_metrics(
    native: ResourceMetrics,
    container: ResourceMetrics,
    *,
    capacity,
) -> ResourceMetrics:
    average_cpu = _sum_present(native.average_cpu_percent, container.average_cpu_percent)
    peak_cpu = _sum_present(native.peak_cpu_percent, container.peak_cpu_percent)
    average_ram = _sum_present(native.average_ram_bytes, container.average_ram_bytes)
    peak_ram = _sum_present(native.peak_ram_bytes, container.peak_ram_bytes)
    cpu_time = _sum_present(native.cpu_time_seconds, container.cpu_time_seconds)
    events = set(native.resource_limit_events) | set(container.resource_limit_events)
    if peak_cpu is not None and peak_cpu > capacity.hard_cpu_percent + 0.5:
        events.add("cpu_hard_ceiling_observed")
    if peak_ram is not None and peak_ram > capacity.hard_ram_bytes:
        events.add("ram_hard_ceiling_observed")
    return ResourceMetrics(
        average_cpu_percent=average_cpu,
        peak_cpu_percent=peak_cpu,
        average_ram_bytes=int(average_ram) if average_ram is not None else None,
        peak_ram_bytes=int(peak_ram) if peak_ram is not None else None,
        peak_ram_percent=(
            peak_ram / capacity.physical_ram_bytes * 100.0 if peak_ram is not None else None
        ),
        cpu_time_seconds=float(cpu_time) if cpu_time is not None else None,
        resource_limit_events=tuple(sorted(events)),
    )


def _sum_present(first: float | int | None, second: float | int | None) -> float | int | None:
    if first is None or second is None:
        return None
    return first + second


def _sum_optional_metrics(first: float | None, second: float | None) -> float | None:
    values = [value for value in (first, second) if value is not None]
    return sum(values) if values else None


def _current_tree_ram(root_pid: int) -> int:
    import psutil  # type: ignore[import-untyped]

    try:
        root = psutil.Process(root_pid)
        return sum(process.memory_info().rss for process in [root, *root.children(recursive=True)])
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0


def _model_fits_now(predicted_bytes: int, hard_limit: int) -> bool:
    return _current_tree_ram(os.getpid()) + predicted_bytes <= hard_limit


def _wait_for_memory_release(root_pid: int, target_bytes: int, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _current_tree_ram(root_pid) <= target_bytes:
            return
        time.sleep(0.25)
    raise RuntimeError("model memory did not return below the soft target after unload")


def _heartbeat_loop(
    database_path: Path,
    experiment_id: str,
    pid: int,
    seconds: int,
    stop: threading.Event,
) -> None:
    with BenchmarkStore(database_path) as store:
        while not stop.wait(seconds):
            try:
                store.heartbeat(experiment_id, pid)
            except BaseException:
                return


def _update_manifest_status(
    manifest_path: Path,
    status: str,
    *,
    started: bool = False,
    ended: bool = False,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = status
    now = utc_now()
    if started and not manifest.get("started_at"):
        manifest["started_at"] = now
    if ended:
        manifest["ended_at"] = now
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(manifest_path)
