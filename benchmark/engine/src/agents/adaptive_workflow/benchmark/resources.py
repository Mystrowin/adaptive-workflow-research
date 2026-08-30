from __future__ import annotations

import ctypes
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from .config import BenchmarkConfig
from .models import ResourceMetrics


@dataclass(frozen=True)
class SystemCapacity:
    logical_cpus: int
    physical_ram_bytes: int
    soft_cpu_percent: float
    hard_cpu_percent: float
    soft_cpu_equivalent: float
    hard_cpu_equivalent: float
    soft_ram_bytes: int
    hard_ram_bytes: int


def detect_system_capacity(config: BenchmarkConfig) -> SystemCapacity:
    logical_cpus = max(1, os.cpu_count() or 1)
    physical_ram = _physical_ram_bytes()
    return SystemCapacity(
        logical_cpus=logical_cpus,
        physical_ram_bytes=physical_ram,
        soft_cpu_percent=config.soft_cpu_fraction * 100.0,
        hard_cpu_percent=config.hard_cpu_fraction * 100.0,
        soft_cpu_equivalent=logical_cpus * config.soft_cpu_fraction,
        hard_cpu_equivalent=logical_cpus * config.hard_cpu_fraction,
        soft_ram_bytes=int(physical_ram * config.soft_ram_fraction),
        hard_ram_bytes=int(physical_ram * config.hard_ram_fraction),
    )


def prerequisite_errors(config: BenchmarkConfig) -> list[str]:
    errors: list[str] = []
    if shutil.which(config.ollama_executable) is None:
        errors.append("Ollama is required. Install it separately, then ensure `ollama` is on PATH.")
    if shutil.which(config.docker_executable) is None:
        errors.append(
            "Docker Desktop is required for isolated Windows verification. Install and start "
            "Docker Desktop separately; benchmark preparation never installs it automatically."
        )
    else:
        completed = subprocess.run(
            [config.docker_executable, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            errors.append("Docker is installed but its local engine is unavailable or not running.")
    if importlib.util.find_spec("psutil") is None:
        errors.append(
            "The benchmark optional dependency `psutil` is missing; install the project with "
            "its `benchmark` extra."
        )
    if sys.platform == "win32" and importlib.util.find_spec("win32job") is None:
        errors.append(
            "The benchmark optional dependency `pywin32` is missing; install the project with "
            "its `benchmark` extra."
        )
    return errors


class WindowsJobLimit:
    """Own a Windows Job Object with hard CPU-rate and aggregate memory caps."""

    def __init__(self, *, hard_cpu_fraction: float, hard_memory_bytes: int) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows Job Objects are available only on Windows")
        import win32job  # type: ignore[import-untyped]

        self._win32job = win32job
        self._handle = win32job.CreateJobObject(None, "")
        self.set_memory_limit(hard_memory_bytes)
        self.set_cpu_fraction(hard_cpu_fraction)

    def set_memory_limit(self, memory_bytes: int) -> None:
        if memory_bytes <= 0:
            raise ValueError("Job Object memory limit must be positive")
        extended = self._win32job.QueryInformationJobObject(
            self._handle, self._win32job.JobObjectExtendedLimitInformation
        )
        basic = extended["BasicLimitInformation"]
        basic["LimitFlags"] |= self._win32job.JOB_OBJECT_LIMIT_JOB_MEMORY
        extended["JobMemoryLimit"] = int(memory_bytes)
        self._win32job.SetInformationJobObject(
            self._handle,
            self._win32job.JobObjectExtendedLimitInformation,
            extended,
        )

    def set_cpu_fraction(self, cpu_fraction: float) -> None:
        if not 0 < cpu_fraction <= 1:
            raise ValueError("Job Object CPU fraction must be in (0, 1]")

        class CpuRateControl(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, Any]]] = [
                ("ControlFlags", ctypes.c_uint32),
                ("CpuRate", ctypes.c_uint32),
            ]

        information = CpuRateControl(
            0x1 | 0x4,  # ENABLE | HARD_CAP
            int(round(cpu_fraction * 10_000)),
        )
        succeeded = ctypes.windll.kernel32.SetInformationJobObject(
            int(self._handle),
            15,  # JobObjectCpuRateControlInformation
            ctypes.byref(information),
            ctypes.sizeof(information),
        )
        if not succeeded:
            raise ctypes.WinError()

    def assign_pid(self, pid: int) -> None:
        import win32api  # type: ignore[import-untyped]
        import win32con  # type: ignore[import-untyped]

        process = win32api.OpenProcess(
            win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE,
            False,
            pid,
        )
        try:
            self._win32job.AssignProcessToJobObject(self._handle, process)
        finally:
            process.Close()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.Close()
            self._handle = None


@dataclass(frozen=True)
class _Sample:
    cpu_percent: float | None
    ram_bytes: int
    ram_percent: float


class ProcessTreeMonitor:
    """Observe a native process tree; hard enforcement is provided by the Job Object."""

    def __init__(
        self,
        root_pid: int,
        capacity: SystemCapacity,
        *,
        interval_seconds: float = 0.5,
    ) -> None:
        import psutil  # type: ignore[import-untyped]

        self._psutil = psutil
        self.root_pid = root_pid
        self.capacity = capacity
        self.interval_seconds = interval_seconds
        self._samples: list[_Sample] = []
        self._events: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("process monitor already started")
        self._thread = threading.Thread(
            target=self._run,
            name="adaptive-benchmark-resource-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> ResourceMetrics:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.interval_seconds * 4))
        return self.metrics()

    def _run(self) -> None:
        # psutil's cpu_percent(None) state belongs to a Process *object*, not a
        # PID. Retain objects by PID and creation time; rebuilding wrappers every
        # sample turns their first reading into a bogus lifetime percentage.
        known: dict[tuple[int, float], Any] = {}
        while not self._stop.is_set():
            try:
                root = self._psutil.Process(self.root_pid)
                processes = [root, *root.children(recursive=True)]
                cpu_sum = 0.0
                observed_cpu = False
                ram_sum = 0
                live_keys: set[tuple[int, float]] = set()
                for candidate in processes:
                    try:
                        key = (candidate.pid, float(candidate.create_time()))
                        live_keys.add(key)
                        process = known.get(key)
                        if process is None:
                            process = candidate
                            known[key] = process
                            process.cpu_percent(None)
                            cpu = 0.0
                        else:
                            cpu = max(0.0, float(process.cpu_percent(None)))
                        # No process tree on this machine can exceed total system
                        # capacity. Treat an impossible sample as telemetry loss,
                        # never as proof of a cap violation.
                        if cpu > self.capacity.logical_cpus * 100.0 + 0.5:
                            self._events.add("native_cpu_metrics_invalid")
                        else:
                            cpu_sum += cpu
                            observed_cpu = True
                        ram_sum += max(0, int(process.memory_info().rss))
                    except (self._psutil.NoSuchProcess, self._psutil.AccessDenied):
                        continue
                known = {key: known[key] for key in live_keys if key in known}
                normalized_cpu = cpu_sum / self.capacity.logical_cpus if observed_cpu else None
                ram_percent = ram_sum / self.capacity.physical_ram_bytes * 100.0
                self._samples.append(_Sample(normalized_cpu, ram_sum, ram_percent))
                if normalized_cpu is not None and normalized_cpu > self.capacity.soft_cpu_percent:
                    self._events.add("cpu_soft_target_exceeded")
                if (
                    normalized_cpu is not None
                    and normalized_cpu > self.capacity.hard_cpu_percent + 0.5
                ):
                    self._events.add("cpu_hard_ceiling_observed")
                if ram_sum > self.capacity.soft_ram_bytes:
                    self._events.add("ram_soft_target_exceeded")
                if ram_sum > self.capacity.hard_ram_bytes:
                    self._events.add("ram_hard_ceiling_observed")
            except (self._psutil.NoSuchProcess, self._psutil.AccessDenied):
                pass
            self._stop.wait(self.interval_seconds)

    def metrics(self) -> ResourceMetrics:
        if not self._samples:
            return ResourceMetrics(resource_limit_events=tuple(sorted(self._events)))
        cpus = [sample.cpu_percent for sample in self._samples if sample.cpu_percent is not None]
        return ResourceMetrics(
            average_cpu_percent=sum(cpus) / len(cpus) if cpus else None,
            peak_cpu_percent=max(cpus) if cpus else None,
            average_ram_bytes=int(
                sum(sample.ram_bytes for sample in self._samples) / len(self._samples)
            ),
            peak_ram_bytes=max(sample.ram_bytes for sample in self._samples),
            peak_ram_percent=max(sample.ram_percent for sample in self._samples),
            cpu_time_seconds=(
                sum(
                    cpu / 100.0 * self.capacity.logical_cpus * self.interval_seconds for cpu in cpus
                )
                if cpus
                else None
            ),
            resource_limit_events=tuple(sorted(self._events)),
        )

    @property
    def hard_violation_observed(self) -> bool:
        return bool({"cpu_hard_ceiling_observed", "ram_hard_ceiling_observed"} & self._events)


def _physical_ram_bytes() -> int:
    if sys.platform == "win32":
        from ctypes import wintypes

        class MemoryStatus(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, Any]]] = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("GlobalMemoryStatusEx failed")
        return int(status.ullTotalPhys)
    page_size = os.sysconf("SC_PAGE_SIZE")
    pages = os.sysconf("SC_PHYS_PAGES")
    return int(page_size * pages)


def source_tree_sha256(root: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    included = [root / "src" / "agents" / "adaptive_workflow", root / "pyproject.toml"]
    files: list[Path] = []
    for entry in included:
        if entry.is_file():
            files.append(entry)
        elif entry.is_dir():
            files.extend(path for path in entry.rglob("*") if path.is_file())
    for path in sorted(files, key=lambda candidate: candidate.as_posix()):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()
