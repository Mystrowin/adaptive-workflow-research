from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from .models import BenchmarkCondition, BenchmarkTier

DEFAULT_SEED = 20260824
DEFAULT_OLLAMA_MODELS = cast(
    dict[BenchmarkTier, str],
    {
        BenchmarkTier.FAST: "qwen2.5-coder:1.5b",
        BenchmarkTier.BALANCED: "qwen2.5-coder:3b",
        BenchmarkTier.BEST: "qwen2.5-coder:7b",
    },
)


def _documents_directory() -> Path:
    override = os.environ.get("ADAPTIVE_WORKFLOW_BENCHMARK_DOCUMENTS")
    return Path(override).expanduser() if override else Path.home() / "Documents"


@dataclass
class BenchmarkConfig:
    private_root: Path = field(
        default_factory=lambda: _documents_directory() / "adaptive_workflow_benchmark_private"
    )
    publishable_root: Path = field(
        default_factory=lambda: _documents_directory() / "adaptive_workflow_publishable_results"
    )
    ollama_url: str = "http://127.0.0.1:11435"
    ollama_executable: str = "ollama"
    docker_executable: str = "docker"
    docker_image: str = "ganler/evalplus:v0.3.1"
    seed: int = DEFAULT_SEED
    max_output_tokens: int = 1024
    context_window: int = 8192
    generation_timeout_seconds: int = 600
    verification_timeout_seconds: int = 120
    heartbeat_seconds: int = 10
    soft_cpu_fraction: float = 0.45
    hard_cpu_fraction: float = 0.50
    soft_ram_fraction: float = 0.45
    hard_ram_fraction: float = 0.50
    docker_cpu_fraction: float = 0.20
    verification_overhead_cpu_fraction: float = 0.05
    verification_overhead_ram_fraction: float = 0.05
    docker_memory_bytes: int = 2 * 1024**3
    docker_pids_limit: int = 64
    max_model_download_bytes: int = 30 * 1024**3
    models: dict[str, str] = field(
        default_factory=lambda: {tier.value: model for tier, model in DEFAULT_OLLAMA_MODELS.items()}
    )
    conditions: tuple[str, ...] = (
        BenchmarkCondition.SMALL_ONLY.value,
        BenchmarkCondition.STRONG_ONLY.value,
        BenchmarkCondition.ADAPTIVE.value,
    )
    routing_statistics_mode: str = "online"
    router_state_path: Path | None = None

    def __post_init__(self) -> None:
        self.private_root = Path(self.private_root).expanduser().resolve()
        self.publishable_root = Path(self.publishable_root).expanduser().resolve()
        if self.router_state_path is not None:
            self.router_state_path = Path(self.router_state_path).expanduser().resolve()
        self.validate()

    @property
    def prepared_directory(self) -> Path:
        return self.private_root / "prepared"

    @property
    def prepared_profile_path(self) -> Path:
        return self.prepared_directory / "prepared_profile.json"

    def experiment_directory(self, experiment_id: str) -> Path:
        return self.private_root / "experiments" / experiment_id

    def validate(self) -> None:
        parsed = urlparse(self.ollama_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("benchmark Ollama URL must be loopback-only HTTP")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("benchmark Ollama URL must not contain credentials or parameters")
        if not 0 < self.soft_cpu_fraction <= self.hard_cpu_fraction <= 0.50:
            raise ValueError("CPU limits must satisfy 0 < soft <= hard <= 0.50")
        if not 0 < self.soft_ram_fraction <= self.hard_ram_fraction <= 0.50:
            raise ValueError("RAM limits must satisfy 0 < soft <= hard <= 0.50")
        if not 0 < self.docker_cpu_fraction < self.hard_cpu_fraction:
            raise ValueError(
                "Docker CPU fraction must leave native capacity below the hard ceiling"
            )
        if (
            self.docker_cpu_fraction + self.verification_overhead_cpu_fraction
            >= self.hard_cpu_fraction
        ):
            raise ValueError("verification CPU reservations must leave native process capacity")
        if not 0 < self.verification_overhead_ram_fraction < self.hard_ram_fraction:
            raise ValueError("verification RAM overhead reserve must fit the hard RAM ceiling")
        if self.max_output_tokens <= 0 or self.context_window <= self.max_output_tokens:
            raise ValueError("context window must be greater than max output tokens")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        required_tiers = {tier.value for tier in BenchmarkTier}
        if set(self.models) != required_tiers:
            raise ValueError("models must define FAST, BALANCED, and BEST exactly")
        if len(set(self.models.values())) != 3:
            raise ValueError("benchmark model tiers must be distinct")
        if any("cloud" in model.casefold() for model in self.models.values()):
            raise ValueError("benchmark model tiers must not reference Ollama cloud models")
        supported_conditions = {condition.value for condition in BenchmarkCondition}
        if not self.conditions or not set(self.conditions) <= supported_conditions:
            raise ValueError("conditions must contain only supported benchmark conditions")
        if len(set(self.conditions)) != len(self.conditions):
            raise ValueError("conditions must not contain duplicates")
        if self.routing_statistics_mode not in {"online", "frozen"}:
            raise ValueError("routing_statistics_mode must be online or frozen")
        if self.private_root == self.publishable_root:
            raise ValueError("private and publishable roots must be separate")
        if self.private_root in self.publishable_root.parents:
            raise ValueError("publishable root must not be inside the private root")

    def as_dict(self) -> dict[str, Any]:
        values = asdict(self)
        values["private_root"] = str(self.private_root)
        values["publishable_root"] = str(self.publishable_root)
        values["conditions"] = list(self.conditions)
        return values

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> BenchmarkConfig:
        known = set(cls.__dataclass_fields__)
        unexpected = sorted(set(values) - known)
        if unexpected:
            raise ValueError(f"unknown benchmark configuration fields: {', '.join(unexpected)}")
        return cls(**values)

    @classmethod
    def from_json(cls, path: Path) -> BenchmarkConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
