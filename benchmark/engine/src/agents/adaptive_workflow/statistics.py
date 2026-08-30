from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass
class RoutingEvidence:
    """Historical success and resource evidence for one routed execution."""

    task_pattern: str
    model_tier: str
    reasoning: str
    provider: str
    execution_mode: str
    completed: bool = False
    verified: bool = False
    latency_ms: float = 0.0
    tokens: int = 0
    cost: float | None = None
    sample_count: int = 1

    @property
    def successful(self) -> bool:
        return self.completed and self.verified

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> RoutingEvidence:
        return cls(
            task_pattern=str(row.get("task_pattern") or "implementation"),
            model_tier=str(row.get("model_tier") or "Luna"),
            reasoning=str(row.get("reasoning") or row.get("reasoning_level") or "medium"),
            provider=str(row.get("provider") or "local"),
            execution_mode=str(row.get("execution_mode") or "single_agent"),
            completed=bool(row.get("completed")),
            verified=bool(row.get("verified")),
            latency_ms=float(row.get("latency_ms") or 0.0),
            tokens=int(row.get("tokens") or 0),
            cost=(float(row["estimated_cost"]) if row.get("estimated_cost") is not None else None),
        )


@dataclass
class RecentAggregate:
    """Recent-window aggregate with exponentially weighted measurements."""

    success_rate: float = 0.0
    average_latency_ms: float = 0.0
    average_tokens: float = 0.0
    average_cost: float | None = None
    sample_count: int = 0
    ewma_factor: float = 0.5
    ewma_success_rate: float = 0.0
    ewma_latency_ms: float = 0.0
    ewma_tokens: float = 0.0
    ewma_cost: float | None = None


class RoutingStatistics:
    """Facts-based routing statistics with lifetime, recent, and EWMA views."""

    def __init__(
        self,
        decay: float = 0.5,
        min_observations: int = 2,
        recent_window: int = 8,
    ) -> None:
        if not 0.0 < decay <= 1.0:
            raise ValueError("decay must be greater than 0 and at most 1")
        if min_observations < 1:
            raise ValueError("min_observations must be at least 1")
        if recent_window < 1:
            raise ValueError("recent_window must be at least 1")
        self.decay = decay
        self.min_observations = min_observations
        self.recent_window = recent_window
        self._rows: list[RoutingEvidence] = []

    @property
    def sample_count(self) -> int:
        return len(self._rows)

    def observation_count(self, **dimensions: Any) -> int:
        return len(self._matching(dimensions))

    def load_rows(self, rows: Iterable[Mapping[str, Any]]) -> None:
        self._rows.extend(RoutingEvidence.from_mapping(row) for row in rows)

    def record(
        self,
        task_pattern: str,
        model_tier: str,
        reasoning: str,
        provider: str,
        execution_mode: str,
        *,
        completed: bool = False,
        verified: bool = False,
        latency_ms: float = 0.0,
        tokens: int = 0,
        cost: float | None = None,
    ) -> None:
        self._rows.append(
            RoutingEvidence(
                task_pattern=task_pattern,
                model_tier=model_tier,
                reasoning=reasoning,
                provider=provider,
                execution_mode=execution_mode,
                completed=completed,
                verified=verified,
                latency_ms=latency_ms,
                tokens=tokens,
                cost=cost,
            )
        )

    def _matching(self, dimension: Mapping[str, Any] | None = None) -> list[RoutingEvidence]:
        rows = list(self._rows)
        if not dimension:
            return rows
        aliases = {"reasoning_level": "reasoning", "estimated_cost": "cost"}
        for raw_name, expected in dimension.items():
            if expected is None:
                continue
            name = aliases.get(raw_name, raw_name)
            if name not in RoutingEvidence.__dataclass_fields__:
                continue
            rows = [row for row in rows if getattr(row, name) == expected]
        return rows

    @staticmethod
    def _success_rate(rows: list[RoutingEvidence]) -> float:
        if not rows:
            return 0.0
        return sum(1 for row in rows if row.successful) / len(rows)

    def recent_success_rate(
        self,
        task_pattern: str,
        model_tier: str | None = None,
        provider: str | None = None,
    ) -> float:
        rows = self._matching(
            {
                "task_pattern": task_pattern,
                "model_tier": model_tier,
                "provider": provider,
            }
        )[-self.recent_window :]
        return self._success_rate(rows)

    def lifetime_success_rate(self, task_pattern: str | None = None) -> float:
        return self._success_rate(self._matching({"task_pattern": task_pattern}))

    def _ewma(self, values: list[float]) -> float:
        if not values:
            return 0.0
        current = values[0]
        for value in values[1:]:
            current = (self.decay * value) + ((1.0 - self.decay) * current)
        return current

    def recent_aggregate(
        self, task_pattern: str | None = None, **dimensions: Any
    ) -> RecentAggregate:
        filters = dict(dimensions)
        filters["task_pattern"] = task_pattern
        recent = self._matching(filters)[-self.recent_window :]
        if not recent:
            return RecentAggregate(ewma_factor=self.decay)

        costs = [row.cost for row in recent if row.cost is not None]
        success_values = [1.0 if row.successful else 0.0 for row in recent]
        latencies = [row.latency_ms for row in recent]
        tokens = [float(row.tokens) for row in recent]
        return RecentAggregate(
            success_rate=self._success_rate(recent),
            average_latency_ms=sum(latencies) / len(recent),
            average_tokens=sum(tokens) / len(recent),
            average_cost=(sum(costs) / len(costs)) if costs else None,
            sample_count=len(recent),
            ewma_factor=self.decay,
            ewma_success_rate=self._ewma(success_values),
            ewma_latency_ms=self._ewma(latencies),
            ewma_tokens=self._ewma(tokens),
            ewma_cost=self._ewma(costs) if costs else None,
        )

    def ewma_adjusted_success(
        self,
        task_pattern: str,
        model_tier: str | None = None,
        provider: str | None = None,
    ) -> float:
        rows = self._matching(
            {
                "task_pattern": task_pattern,
                "model_tier": model_tier,
                "provider": provider,
            }
        )
        lifetime = self._success_rate(rows)
        if len(rows) < self.min_observations:
            return lifetime
        recent = rows[-self.recent_window :]
        return self._ewma([1.0 if row.successful else 0.0 for row in recent])

    def provider_success_rate(
        self,
        provider: str,
        model_tier: str | None = None,
        task_pattern: str | None = None,
    ) -> float:
        return self._success_rate(
            self._matching(
                {
                    "provider": provider,
                    "model_tier": model_tier,
                    "task_pattern": task_pattern,
                }
            )
        )

    def model_preference(self, task_pattern: str) -> str:
        matching = self._matching({"task_pattern": task_pattern})
        candidates = sorted({row.model_tier for row in matching})
        qualified: list[tuple[float, int, float, str]] = []
        for model in candidates:
            rows = [row for row in matching if row.model_tier == model]
            if len(rows) < self.min_observations:
                continue
            success = self._success_rate(rows)
            latency = sum(row.latency_ms for row in rows) / len(rows)
            qualified.append((success, len(rows), -latency, model))
        return max(qualified)[-1] if qualified else "Luna"

    def should_explore(self, task_pattern: str, confidence: float = 1.0) -> bool:
        matching = self._matching({"task_pattern": task_pattern})
        if len(matching) < self.min_observations:
            return True
        return confidence < 0.55

    def aggregate(self, dimension: dict[str, Any] | None = None) -> dict[str, Any]:
        rows = self._matching(dimension)
        recent = rows[-self.recent_window :]
        if not rows:
            return {
                "sample_count": 0,
                "success_rate": 0.0,
                "latency_ms": 0.0,
                "tokens": 0.0,
                "estimated_cost": None,
                "recent_sample_count": 0,
                "recent_success_rate": 0.0,
                "ewma_success_rate": 0.0,
                "ewma_factor": self.decay,
                "minimum_samples_met": False,
            }

        costs = [row.cost for row in rows if row.cost is not None]
        return {
            "sample_count": len(rows),
            "success_rate": self._success_rate(rows),
            "latency_ms": sum(row.latency_ms for row in rows) / len(rows),
            "tokens": sum(row.tokens for row in rows) / len(rows),
            "estimated_cost": (sum(costs) / len(costs)) if costs else None,
            "recent_sample_count": len(recent),
            "recent_success_rate": self._success_rate(recent),
            "ewma_success_rate": self._ewma([1.0 if row.successful else 0.0 for row in recent]),
            "ewma_factor": self.decay,
            "minimum_samples_met": len(rows) >= self.min_observations,
        }

    def explain(self) -> str:
        recent = self.recent_aggregate()
        return (
            f"Historical sample count={len(self._rows)} "
            f"recent={recent.sample_count} ewma={self.decay} "
            f"minimum={self.min_observations}"
        )
