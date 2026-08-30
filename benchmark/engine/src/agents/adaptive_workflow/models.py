from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaskFingerprint:
    """Task features consumed by the published routing policy."""

    task_id: str
    task_category: str
    context_size: int | None = None
    ambiguity: float = 0.0
    risk: str = "low"
    parallelizability: bool = False


@dataclass
class RoutingDecision:
    """Deterministic routing decision used by the benchmark adapter."""

    model_tier: str
    reasoning_level: str
    prompt_depth: int
    execution_mode: str
    rationale: str = "policy-driven"
    confidence: float = 0.0
    rationale_codes: list[str] = field(default_factory=list)
    provider: str = "local"
