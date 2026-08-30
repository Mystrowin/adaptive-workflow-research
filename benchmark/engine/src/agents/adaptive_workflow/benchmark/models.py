from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BenchmarkTier(StrEnum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    BEST = "BEST"


class BenchmarkCondition(StrEnum):
    SMALL_ONLY = "small_only"
    BALANCED_ONLY = "balanced_only"
    STRONG_ONLY = "strong_only"
    FIXED_CASCADE = "fixed_cascade"
    ADAPTIVE = "adaptive"


class ExperimentStatus(StrEnum):
    PREPARED = "prepared"
    STARTING = "starting"
    RUNNING = "running"
    STOP_REQUESTED = "stop_requested"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    RESOURCE_VIOLATION = "resource_violation"


class AttemptStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    MODEL_ERROR = "model_error"
    VERIFIER_ERROR = "verifier_error"
    RESOURCE_BLOCKED = "resource_blocked"
    RESOURCE_VIOLATION = "resource_violation"


def classify_failure(
    status: str,
    verification: VerificationOutcome | None = None,
    generated_output: str | None = None,
) -> str:
    """Normalize terminal outcomes for future reports without changing old status values."""

    if status == AttemptStatus.PASSED.value:
        return "verified_pass"
    if status == AttemptStatus.MODEL_ERROR.value:
        return "generation_runtime_failure"
    if status == AttemptStatus.RESOURCE_BLOCKED.value:
        return "resource_blocked"
    if status == AttemptStatus.RESOURCE_VIOLATION.value:
        return "resource_violation"
    if status == AttemptStatus.VERIFIER_ERROR.value:
        return "verifier_infrastructure_failure"
    if verification is not None:
        if verification.status == "timeout":
            return "timeout"
        if verification.status == "verifier_error":
            return "verifier_infrastructure_failure"
        if not (generated_output or "").strip():
            return "malformed_output"
        if verification.status == "failed":
            if verification.base_passed and not verification.plus_passed:
                return "test_failure"
            return "model_incorrect"
    return "unknown"


@dataclass(frozen=True)
class ModelSpec:
    tier: BenchmarkTier
    provider: str
    model: str
    parameter_billions: float
    digest: str
    quantization: str | None
    size_bytes: int | None
    predicted_memory_bytes: int | None = None

    def validate(self) -> None:
        if self.provider != "ollama":
            raise ValueError("benchmark models must use provider=ollama")
        if self.parameter_billions <= 0:
            raise ValueError("model parameter_billions must be greater than zero")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", self.digest) is None:
            raise ValueError("model digest must be a sha256 digest")


@dataclass(frozen=True)
class BenchmarkTask:
    benchmark: str
    benchmark_version: str
    task_id: str
    prompt: str
    entry_point: str
    reference_input_tokens: int
    source_sha256: str

    def identity(self) -> str:
        return f"{self.benchmark}:{self.task_id}"


@dataclass(frozen=True)
class FrozenTaskBudget:
    task_identity: str
    reference_input_tokens: int
    max_output_tokens: int
    reservations: dict[str, float]
    adaptive_limit: float


@dataclass(frozen=True)
class FrozenBudget:
    unit: str
    max_output_tokens: int
    task_budgets: tuple[FrozenTaskBudget, ...]
    total_token_baseline_b0: float
    generation_baseline_g0: float
    total_token_cutoffs: tuple[float, ...]
    generation_cutoffs: tuple[float, ...]


@dataclass(frozen=True)
class VerificationOutcome:
    status: str
    base_status: str
    plus_status: str
    base_passed: bool
    plus_passed: bool
    duration_ms: int
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


@dataclass(frozen=True)
class ResourceMetrics:
    average_cpu_percent: float | None = None
    peak_cpu_percent: float | None = None
    average_ram_bytes: int | None = None
    peak_ram_bytes: int | None = None
    peak_ram_percent: float | None = None
    model_load_memory_bytes: int | None = None
    cpu_time_seconds: float | None = None
    resource_limit_events: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttemptRecord:
    experiment_id: str
    benchmark: str
    benchmark_version: str
    task_id: str
    condition: BenchmarkCondition
    selected_tier: BenchmarkTier
    selected_model: str
    route: tuple[str, ...]
    attempt_number: int
    start_time: str
    end_time: str
    status: AttemptStatus
    verification: VerificationOutcome
    resources: ResourceMetrics
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    generation_cost_proxy: float | None
    total_token_cost_proxy: float | None
    wall_time_ms: int
    model_load_time_ms: int | None
    inference_time_ms: int | None
    verification_time_ms: int
    router_confidence: float
    router_reason: str
    seed: int
    error: str | None = None
    escalation_path: tuple[str, ...] = ()
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    generated_output: str | None = None
    generated_output_sha256: str | None = None
    prompt_sha256: str | None = None
    system_prompt_sha256: str | None = None
    generation_template_version: str | None = None
    model_digest: str | None = None
    verifier_invocation: dict[str, Any] = field(default_factory=dict)
    failure_class: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def public_task_result(attempt: AttemptRecord) -> dict[str, Any]:
    """Return the allowlisted task-level projection used by publishing."""

    return {
        "benchmark": attempt.benchmark,
        "benchmark_version": attempt.benchmark_version,
        "task_id": attempt.task_id,
        "condition": attempt.condition.value,
        "selected_tier": attempt.selected_tier.value,
        "selected_model": attempt.selected_model,
        "model_digest": attempt.model_digest,
        "attempt_number": attempt.attempt_number,
        "status": attempt.status.value,
        "base_passed": attempt.verification.base_passed,
        "plus_passed": attempt.verification.plus_passed,
        "input_tokens": attempt.input_tokens,
        "output_tokens": attempt.output_tokens,
        "total_tokens": attempt.total_tokens,
        "generation_cost_proxy": attempt.generation_cost_proxy,
        "total_token_cost_proxy": attempt.total_token_cost_proxy,
        "wall_time_ms": attempt.wall_time_ms,
        "model_load_time_ms": attempt.model_load_time_ms,
        "inference_time_ms": attempt.inference_time_ms,
        "verification_time_ms": attempt.verification_time_ms,
        "average_cpu_percent": attempt.resources.average_cpu_percent,
        "peak_cpu_percent": attempt.resources.peak_cpu_percent,
        "average_ram_bytes": attempt.resources.average_ram_bytes,
        "peak_ram_bytes": attempt.resources.peak_ram_bytes,
        "peak_ram_percent": attempt.resources.peak_ram_percent,
        "cpu_time_seconds": attempt.resources.cpu_time_seconds,
        "resource_limit_events": list(attempt.resources.resource_limit_events),
        "router_confidence": attempt.router_confidence,
        "router_reason": attempt.router_reason,
        "escalation_path": list(attempt.escalation_path),
        "seed": attempt.seed,
        "generated_output_sha256": attempt.generated_output_sha256,
        "prompt_sha256": attempt.prompt_sha256,
        "system_prompt_sha256": attempt.system_prompt_sha256,
        "generation_template_version": attempt.generation_template_version,
        "failure_class": attempt.failure_class,
    }
