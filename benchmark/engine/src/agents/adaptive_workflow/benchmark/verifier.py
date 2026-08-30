from __future__ import annotations

import gzip
import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import BenchmarkConfig
from .models import BenchmarkTask, ResourceMetrics, VerificationOutcome
from .resources import SystemCapacity

RESULT_PREFIX = "ADAPTIVE_BENCHMARK_RESULT="


@dataclass(frozen=True)
class DockerVerification:
    outcome: VerificationOutcome
    resources: ResourceMetrics
    image_digest: str


class DockerEvalPlusVerifier:
    """Run one generated solution in a fail-closed local Docker container."""

    def __init__(
        self,
        config: BenchmarkConfig,
        capacity: SystemCapacity,
        *,
        dataset_directory: Path,
    ) -> None:
        self.config = config
        self.capacity = capacity
        self.dataset_directory = dataset_directory.resolve()
        self.adapter_path = Path(__file__).with_name("evalplus_adapter.py").resolve()
        self._problems = {
            "humaneval": _load_problem_file(self.dataset_directory / "HumanEvalPlus.jsonl.gz"),
            "mbpp": _load_problem_file(self.dataset_directory / "MbppPlus.jsonl.gz"),
        }
        self.image_digest = self.inspect_image()

    def inspect_image(self) -> str:
        completed = subprocess.run(
            [
                self.config.docker_executable,
                "image",
                "inspect",
                self.config.docker_image,
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
        if completed.returncode != 0:
            raise RuntimeError(
                f"pinned EvalPlus Docker image is unavailable: {self.config.docker_image}"
            )
        output = completed.stdout.strip()
        if not output:
            raise RuntimeError("Docker image inspection returned no digest")
        return output

    def verify(
        self,
        task: BenchmarkTask,
        solution: str,
        *,
        identifier: str,
    ) -> DockerVerification:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="adaptive-benchmark-task-") as temporary:
            workspace = Path(temporary).resolve()
            request_path = workspace / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "dataset": task.benchmark,
                        "task_id": task.task_id,
                        "dataset_hash": task.source_sha256,
                        "problem": self._problem_for(task),
                        "solution": solution,
                        "identifier": identifier,
                        "min_time_limit": 1.0,
                        "gt_time_limit_factor": 4.0,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            container_id = self._create_container(workspace)
            try:
                output, error, timed_out, samples = self._start_and_observe(container_id)
            finally:
                self._remove_container(container_id)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        resources = _metrics_from_docker_samples(samples, self.capacity)
        if timed_out:
            return DockerVerification(
                outcome=VerificationOutcome(
                    status="timeout",
                    base_status="timeout",
                    plus_status="timeout",
                    base_passed=False,
                    plus_passed=False,
                    duration_ms=elapsed_ms,
                    stdout=output[-8000:],
                    stderr=error[-8000:],
                    error="verification container exceeded its timeout",
                ),
                resources=resources,
                image_digest=self.image_digest,
            )
        try:
            payload = _extract_result(output)
            base_status = str(payload["base"]["status"])
            plus_status = str(payload["plus"]["status"])
            base_passed = base_status == "pass"
            plus_passed = base_passed and plus_status == "pass"
            outcome = VerificationOutcome(
                status="passed" if plus_passed else "failed",
                base_status=base_status,
                plus_status=plus_status,
                base_passed=base_passed,
                plus_passed=plus_passed,
                duration_ms=elapsed_ms,
                stdout=output[-8000:],
                stderr=error[-8000:],
            )
        except (KeyError, TypeError, ValueError) as exc:
            outcome = VerificationOutcome(
                status="verifier_error",
                base_status="error",
                plus_status="error",
                base_passed=False,
                plus_passed=False,
                duration_ms=elapsed_ms,
                stdout=output[-8000:],
                stderr=error[-8000:],
                error=f"invalid EvalPlus verifier output: {exc}",
            )
        return DockerVerification(outcome, resources, self.image_digest)

    def _create_container(self, workspace: Path) -> str:
        docker_cpus = max(0.01, self.capacity.logical_cpus * self.config.docker_cpu_fraction)
        command = [
            self.config.docker_executable,
            "create",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(self.config.docker_pids_limit),
            "--memory",
            str(self.config.docker_memory_bytes),
            "--memory-swap",
            str(self.config.docker_memory_bytes),
            "--cpus",
            f"{docker_cpus:.3f}",
            "--user",
            "65534:65534",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=536870912",
            "--env",
            "HOME=/tmp",
            "--env",
            "HF_HOME=/tmp/huggingface",
            "--env",
            f"EVALPLUS_MAX_MEMORY_BYTES={self.config.docker_memory_bytes // 2}",
            "--env",
            "PYTHONHASHSEED=0",
            "--mount",
            f"type=bind,source={workspace},target=/workspace",
            "--mount",
            f"type=bind,source={self.adapter_path},target=/opt/adaptive/evalplus_adapter.py,readonly",
            self.config.docker_image,
            "python",
            "/opt/adaptive/evalplus_adapter.py",
            "/workspace/request.json",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown error").strip()
            raise RuntimeError(f"failed to create verifier container: {detail[:2000]}")
        container_id = completed.stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
            raise RuntimeError("Docker returned an invalid verifier container ID")
        return container_id

    def _problem_for(self, task: BenchmarkTask) -> dict[str, Any]:
        problems = self._problems.get(task.benchmark)
        if problems is None or task.task_id not in problems:
            raise RuntimeError(f"frozen EvalPlus task is unavailable: {task.identity()}")
        return problems[task.task_id]

    def _start_and_observe(
        self, container_id: str
    ) -> tuple[str, str, bool, list[dict[str, float]]]:
        process = subprocess.Popen(
            [self.config.docker_executable, "start", "--attach", container_id],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        deadline = time.monotonic() + self.config.verification_timeout_seconds
        samples: list[dict[str, float]] = []
        timed_out = False
        while process.poll() is None:
            sample = self._docker_sample(container_id)
            if sample:
                samples.append(sample)
            if time.monotonic() >= deadline:
                timed_out = True
                self._kill_container(container_id)
                break
            time.sleep(0.5)
        try:
            output, error = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            output, error = process.communicate(timeout=5)
            timed_out = True
        return output, error, timed_out, samples

    def _docker_sample(self, container_id: str) -> dict[str, float]:
        completed = subprocess.run(
            [
                self.config.docker_executable,
                "stats",
                "--no-stream",
                "--format",
                "{{json .}}",
                container_id,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return {}
        try:
            payload = json.loads(completed.stdout)
            cpu_raw = float(str(payload.get("CPUPerc", "0")).rstrip("%") or 0)
            memory_usage = str(payload.get("MemUsage", "0B / 0B")).split("/", 1)[0].strip()
            ram_bytes = float(_parse_docker_bytes(memory_usage))
            if cpu_raw < 0 or cpu_raw > self.capacity.logical_cpus * 100.0 + 0.5:
                return {
                    "invalid_cpu_percent": cpu_raw,
                    "ram_bytes": ram_bytes,
                }
            return {
                "cpu_percent": cpu_raw / self.capacity.logical_cpus,
                "ram_bytes": ram_bytes,
            }
        except (ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _kill_container(self, container_id: str) -> None:
        subprocess.run(
            [self.config.docker_executable, "kill", container_id],
            capture_output=True,
            timeout=15,
            check=False,
        )

    def _remove_container(self, container_id: str) -> None:
        subprocess.run(
            [self.config.docker_executable, "rm", "--force", container_id],
            capture_output=True,
            timeout=30,
            check=False,
        )


def _extract_result(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        if line.startswith(RESULT_PREFIX):
            payload = json.loads(line.removeprefix(RESULT_PREFIX))
            if not isinstance(payload, dict):
                break
            return payload
    raise ValueError("result marker was not present")


def _metrics_from_docker_samples(
    samples: list[dict[str, float]], capacity: SystemCapacity
) -> ResourceMetrics:
    if not samples:
        return ResourceMetrics(resource_limit_events=("docker_metrics_unavailable",))
    cpus = [sample["cpu_percent"] for sample in samples if "cpu_percent" in sample]
    rams = [int(sample["ram_bytes"]) for sample in samples]
    peak_ram = max(rams)
    events: list[str] = []
    if len(cpus) != len(samples):
        events.append("docker_cpu_metrics_invalid")
    peak_cpu = max(cpus) if cpus else None
    if peak_cpu is not None:
        if peak_cpu > capacity.soft_cpu_percent:
            events.append("cpu_soft_target_exceeded")
        if peak_cpu > capacity.hard_cpu_percent + 0.5:
            events.append("cpu_hard_ceiling_observed")
    if peak_ram > capacity.soft_ram_bytes:
        events.append("ram_soft_target_exceeded")
    if peak_ram > capacity.hard_ram_bytes:
        events.append("ram_hard_ceiling_observed")
    return ResourceMetrics(
        average_cpu_percent=sum(cpus) / len(cpus) if cpus else None,
        peak_cpu_percent=peak_cpu,
        average_ram_bytes=int(sum(rams) / len(rams)),
        peak_ram_bytes=peak_ram,
        peak_ram_percent=peak_ram / capacity.physical_ram_bytes * 100.0,
        cpu_time_seconds=(
            sum(cpu / 100.0 * capacity.logical_cpus * 0.5 for cpu in cpus) if cpus else None
        ),
        resource_limit_events=tuple(events),
    )


def _parse_docker_bytes(value: str) -> int:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?i?B)\s*", value)
    if match is None:
        raise ValueError(f"invalid Docker byte value: {value}")
    number = float(match.group(1))
    unit = match.group(2)
    factors = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
    }
    return int(number * factors[unit])


def _load_problem_file(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise RuntimeError(f"frozen EvalPlus data is unavailable: {path.name}")
    problems: dict[str, dict[str, Any]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                problem = json.loads(line)
                task_id = str(problem["task_id"])
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise RuntimeError(f"invalid EvalPlus data at {path.name}:{line_number}") from exc
            if task_id in problems:
                raise RuntimeError(f"duplicate EvalPlus task in {path.name}: {task_id}")
            problems[task_id] = problem
    return problems
