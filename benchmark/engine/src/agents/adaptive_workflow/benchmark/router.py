from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from ..config import AdaptiveWorkflowConfig
from ..models import TaskFingerprint
from ..routing import AdaptiveRouter
from ..statistics import RoutingStatistics
from .models import BenchmarkCondition, BenchmarkTask, BenchmarkTier

_LOGICAL_TO_BENCHMARK = {
    "Luna": BenchmarkTier.FAST,
    "Terra": BenchmarkTier.BALANCED,
    "Sol": BenchmarkTier.BEST,
}


@dataclass(frozen=True)
class BenchmarkRoute:
    tier: BenchmarkTier
    confidence: float
    reason: str


class BenchmarkRouter:
    """Use Adaptive Workflow's router while enforcing a local-only tier result."""

    def __init__(self, statistics: RoutingStatistics | None = None) -> None:
        config = AdaptiveWorkflowConfig(
            workflow_mode="BALANCED",
            preferred_local_provider="ollama",
            preferred_cloud_provider="ollama",
            exploration_rate=0.0,
        )
        self._router = AdaptiveRouter(config=config, stats=statistics or RoutingStatistics())

    def initial_route(
        self,
        condition: BenchmarkCondition,
        task: BenchmarkTask,
    ) -> BenchmarkRoute:
        if condition == BenchmarkCondition.SMALL_ONLY:
            return BenchmarkRoute(BenchmarkTier.FAST, 1.0, "static-small-only")
        if condition == BenchmarkCondition.BALANCED_ONLY:
            return BenchmarkRoute(BenchmarkTier.BALANCED, 1.0, "static-balanced-only")
        if condition == BenchmarkCondition.STRONG_ONLY:
            return BenchmarkRoute(BenchmarkTier.BEST, 1.0, "static-strong-only")
        if condition == BenchmarkCondition.FIXED_CASCADE:
            return BenchmarkRoute(BenchmarkTier.FAST, 1.0, "static-fast-first-cascade")

        fingerprint = self._fingerprint(task)
        decision = self._router.select(
            fingerprint=fingerprint,
            provider_capabilities={
                "preferred_provider": "ollama",
                "cloud_provider": "ollama",
                "exploratory_provider": "ollama",
            },
            risk=fingerprint.risk,
        )
        tier = _LOGICAL_TO_BENCHMARK.get(decision.model_tier, BenchmarkTier.BALANCED)
        return BenchmarkRoute(
            tier=tier,
            confidence=decision.confidence,
            reason=f"{decision.rationale};provider-forced-local;{','.join(decision.rationale_codes)}",
        )

    @staticmethod
    def escalation_path(initial: BenchmarkTier) -> tuple[BenchmarkTier, ...]:
        if initial == BenchmarkTier.FAST:
            return cast(
                tuple[BenchmarkTier, ...],
                (BenchmarkTier.FAST, BenchmarkTier.BALANCED, BenchmarkTier.BEST),
            )
        if initial == BenchmarkTier.BALANCED:
            return cast(tuple[BenchmarkTier, ...], (BenchmarkTier.BALANCED, BenchmarkTier.BEST))
        return cast(tuple[BenchmarkTier, ...], (BenchmarkTier.BEST,))

    @staticmethod
    def _fingerprint(task: BenchmarkTask) -> TaskFingerprint:
        prompt = task.prompt
        lowered = prompt.lower()
        hard_markers = (
            "dynamic programming",
            "graph",
            "recursive",
            "matrix",
            "parser",
            "regular expression",
            "combinations",
        )
        has_hard_marker = any(marker in lowered for marker in hard_markers)
        risk = "high" if len(prompt) > 1600 or has_hard_marker else "low"
        ambiguity = 0.7 if len(prompt) > 900 else 0.2
        return TaskFingerprint(
            task_id=task.identity(),
            task_category="function_synthesis",
            risk=risk,
            ambiguity=ambiguity,
            context_size=max(1, len(prompt) // 8),
            parallelizability=False,
        )
