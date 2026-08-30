from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .config import BenchmarkConfig
from .models import BenchmarkCondition, ExperimentStatus
from .preparation import load_frozen_tasks, load_prepared_profile, new_experiment_id
from .store import BenchmarkStore

_EXPERIMENT_ID = re.compile(r"^awb-[0-9]{8}T[0-9]{6}Z-s[0-9]+-[0-9a-f]{8}$")


def create_experiment(config: BenchmarkConfig) -> tuple[str, Path]:
    profile = load_prepared_profile(config)
    tasks = load_frozen_tasks(profile)
    experiment_id = new_experiment_id(config.seed)
    directory = config.experiment_directory(experiment_id)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "logs").mkdir()
    (directory / "task_workspaces").mkdir()
    publishable_directory = config.publishable_root / f"{experiment_id}-v1"
    manifest = {
        **profile,
        "experiment_id": experiment_id,
        "status": ExperimentStatus.PREPARED.value,
        "created_at": datetime.now(UTC).isoformat(),
        "started_at": None,
        "ended_at": None,
        "private_raw_results_directory": str(directory),
        "publishable_results_directory": str(publishable_directory),
    }
    manifest_path = directory / "experiment_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    source_path = Path(str(profile["benchmark_sources_file"]))
    (directory / "benchmark_sources.json").write_bytes(source_path.read_bytes())
    (directory / "raw_results.jsonl").touch(exist_ok=False)
    schedule = tuple(
        (str(item["task_identity"]), BenchmarkCondition(str(item["condition"])))
        for item in profile["schedule"]
    )
    database_path = directory / "results.sqlite"
    with BenchmarkStore(database_path) as store:
        store.create_experiment(
            experiment_id=experiment_id,
            manifest_path=manifest_path,
            private_directory=directory,
            publishable_directory=publishable_directory,
            tasks=tasks,
            schedule=schedule,
        )
    _write_state_file(directory, experiment_id, None, "prepared")
    return experiment_id, directory


def launch_detached(
    config: BenchmarkConfig,
    *,
    repository_root: Path,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    if experiment_id is None:
        experiment_id, directory = create_experiment(config)
    else:
        directory = resolve_experiment_directory(config, experiment_id)
        _ensure_not_running(directory)
        with BenchmarkStore(directory / "results.sqlite") as store:
            status = store.status()
            if status["status"] == ExperimentStatus.COMPLETED.value:
                raise RuntimeError("completed experiments cannot be resumed")
            store.clear_stop_request(experiment_id)

    stdout_path = directory / "logs" / "worker.stdout.log"
    stderr_path = directory / "logs" / "worker.stderr.log"
    command = [
        sys.executable,
        "-m",
        "agents.adaptive_workflow.benchmark.cli",
        "_worker",
        "--experiment-directory",
        str(directory),
    ]
    environment = _worker_environment()
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_BREAKAWAY_FROM_JOB
        )
    with BenchmarkStore(directory / "results.sqlite") as store:
        store.set_status(experiment_id, ExperimentStatus.STARTING)
    _write_state_file(directory, experiment_id, None, "starting", command)
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        process = subprocess.Popen(
            command,
            cwd=repository_root,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env=environment,
            creationflags=creationflags,
            close_fds=True,
        )
    with BenchmarkStore(directory / "results.sqlite") as store:
        store.heartbeat(experiment_id, process.pid)
    _write_state_file(directory, experiment_id, process.pid, "starting", command)
    return {
        "experiment_id": experiment_id,
        "benchmark_pid": process.pid,
        "private_results_directory": str(directory),
        "publishable_results_directory": str(config.publishable_root / f"{experiment_id}-v1"),
    }


def request_stop(config: BenchmarkConfig, experiment_id: str) -> dict[str, Any]:
    directory = resolve_experiment_directory(config, experiment_id)
    with BenchmarkStore(directory / "results.sqlite") as store:
        store.request_stop(experiment_id)
        return store.status()


def experiment_status(config: BenchmarkConfig, experiment_id: str) -> dict[str, Any]:
    directory = resolve_experiment_directory(config, experiment_id)
    with BenchmarkStore(directory / "results.sqlite", read_only=True) as store:
        return store.status()


def list_experiments(config: BenchmarkConfig) -> list[dict[str, Any]]:
    root = config.private_root / "experiments"
    if not root.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for directory in sorted(root.iterdir(), reverse=True):
        database = directory / "results.sqlite"
        if not database.is_file() or not _EXPERIMENT_ID.fullmatch(directory.name):
            continue
        try:
            with BenchmarkStore(database, read_only=True) as store:
                results.append(store.status())
        except (OSError, RuntimeError):
            continue
    return results


def resolve_experiment_directory(config: BenchmarkConfig, experiment_id: str) -> Path:
    if _EXPERIMENT_ID.fullmatch(experiment_id) is None:
        raise ValueError("invalid benchmark experiment ID")
    directory = config.experiment_directory(experiment_id).resolve()
    root = (config.private_root / "experiments").resolve()
    if root not in directory.parents or not directory.is_dir():
        raise FileNotFoundError(f"benchmark experiment not found: {experiment_id}")
    return directory


def _ensure_not_running(directory: Path) -> None:
    state_path = directory / "worker_state.json"
    if not state_path.is_file():
        return
    state = json.loads(state_path.read_text(encoding="utf-8"))
    pid = state.get("pid")
    if isinstance(pid, int) and _worker_pid_matches(pid, directory):
        raise RuntimeError(f"benchmark worker is already running with PID {pid}")
    stale_lock = directory / ".worker.lock"
    if stale_lock.exists():
        stale_lock.unlink()


def _pid_exists(pid: int) -> bool:
    try:
        import psutil  # type: ignore[import-untyped]

        return cast(bool, psutil.pid_exists(pid))
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _worker_pid_matches(pid: int, directory: Path) -> bool:
    if not _pid_exists(pid):
        return False
    try:
        import psutil

        command = " ".join(psutil.Process(pid).cmdline()).casefold()
        return (
            "agents.adaptive_workflow.benchmark.cli" in command
            and str(directory.resolve()).casefold() in command
        )
    except (ImportError, OSError):
        return True
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return True


def _worker_environment() -> dict[str, str]:
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


def _write_state_file(
    directory: Path,
    experiment_id: str,
    pid: int | None,
    status: str,
    command: list[str] | None = None,
) -> None:
    command_hash = None
    if command is not None:
        command_hash = hashlib.sha256("\0".join(command).encode("utf-8")).hexdigest()
    (directory / "worker_state.json").write_text(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "pid": pid,
                "status": status,
                "recorded_at": datetime.now(UTC).isoformat(),
                "command_sha256": command_hash,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
