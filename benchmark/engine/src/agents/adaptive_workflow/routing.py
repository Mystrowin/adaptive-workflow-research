from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .config import AdaptiveWorkflowConfig
from .models import RoutingDecision, TaskFingerprint
from .statistics import RoutingStatistics


@dataclass
class AdaptiveRoute:
    """A normalized provider, logical tier, and physical model route."""

    provider: str
    logical_model_tier: str
    reasoning_level: str
    prompt_depth: int
    execution_mode: str
    explainability: dict[str, Any] | None = None
    model: str | None = None


class AdaptiveRouter:
    """Select one risk- and mode-constrained route using qualified evidence."""

    def __init__(
        self,
        config: AdaptiveWorkflowConfig | None = None,
        stats: RoutingStatistics | None = None,
    ) -> None:
        self.config = config or AdaptiveWorkflowConfig()
        self.statistics = stats or RoutingStatistics()

    def select(
        self,
        fingerprint: TaskFingerprint | None = None,
        provider_capabilities: dict[str, Any] | None = None,
        playbook_hints: list[str] | None = None,
        risk: str = "low",
    ) -> RoutingDecision:
        _ = playbook_hints
        capabilities = provider_capabilities or {}
        task_pattern = (
            fingerprint.task_category
            if fingerprint is not None and fingerprint.task_category
            else "implementation"
        )
        effective_risk = risk
        if fingerprint is not None and fingerprint.risk == "high":
            effective_risk = "high"
        mode = self.config.workflow_mode.upper()

        prompt_depth = 1
        if fingerprint is not None:
            if fingerprint.context_size and fingerprint.context_size > 120:
                prompt_depth = 3
            if effective_risk == "high" or fingerprint.ambiguity > 0.5:
                prompt_depth = 4

        preferred = str(
            capabilities.get("preferred_provider") or self.config.preferred_local_provider
        )
        fallback_provider = self._provider_for_mode(
            str(capabilities.get("cloud_provider") or self.config.preferred_cloud_provider)
        )
        provider = self._provider_for_mode(preferred)
        if task_pattern == "debugging" or effective_risk == "high" or mode == "BEST":
            provider = fallback_provider

        model_tier = "Luna"
        reasoning_level = "medium"
        execution_mode = "single_agent"
        if prompt_depth >= 3:
            model_tier = "Terra"
            reasoning_level = "high"
        if task_pattern == "debugging":
            model_tier = "Terra"
            reasoning_level = "high"
        if effective_risk == "high":
            model_tier = "Sol"
            reasoning_level = "medium"

        if mode == "FAST":
            model_tier = "Luna"
            reasoning_level = "low"
            prompt_depth = min(prompt_depth, 2)
        elif mode == "BEST":
            model_tier = "Sol"
            reasoning_level = "high"
            prompt_depth = max(prompt_depth, 3)
            if fingerprint is not None and fingerprint.parallelizability:
                execution_mode = "parallel_agent"

        if effective_risk == "high":
            provider = fallback_provider
            model_tier = "Sol"
            reasoning_level = "high" if mode == "BEST" else "medium"
            prompt_depth = max(prompt_depth, 3)

        mandatory_provider = effective_risk == "high" or mode == "BEST"
        if not mandatory_provider:
            provider_samples = self.statistics.observation_count(
                task_pattern=task_pattern, provider=provider
            )
            if provider_samples >= self.statistics.min_observations:
                provider_success = self.statistics.provider_success_rate(
                    provider, task_pattern=task_pattern
                )
                if provider_success < 0.35:
                    provider = fallback_provider if provider == "ollama" else "ollama"

            if mode == "BALANCED":
                learned_model = self.statistics.model_preference(task_pattern)
                learned_samples = self.statistics.observation_count(
                    task_pattern=task_pattern, model_tier=learned_model
                )
                if learned_samples >= self.statistics.min_observations:
                    model_tier = learned_model

            if provider_samples < self.statistics.min_observations and self._should_explore(
                task_pattern, provider, fingerprint
            ):
                exploratory = self._provider_for_mode(
                    str(capabilities.get("exploratory_provider") or fallback_provider)
                )
                if exploratory == "local":
                    exploratory = (
                        fallback_provider if provider != fallback_provider else "ollama"
                    )
                provider = exploratory
                if (
                    mode != "FAST"
                    and prompt_depth >= 3
                    and fingerprint is not None
                    and fingerprint.parallelizability
                ):
                    execution_mode = "parallel_agent"

        return RoutingDecision(
            model_tier=model_tier,
            reasoning_level=reasoning_level,
            prompt_depth=prompt_depth,
            execution_mode=execution_mode,
            rationale="adaptive-rule-router",
            confidence=0.88,
            rationale_codes=[
                "adaptive-router",
                "qualified-history",
                f"mode:{mode}",
                f"risk:{effective_risk}",
            ],
            provider=provider,
        )

    def _should_explore(
        self,
        task_pattern: str,
        provider: str,
        fingerprint: TaskFingerprint | None,
    ) -> bool:
        rate = min(1.0, max(0.0, float(self.config.exploration_rate)))
        if rate == 0.0:
            return False
        identity = fingerprint.task_id if fingerprint is not None else task_pattern
        digest = hashlib.sha256(f"{task_pattern}:{identity}".encode()).digest()
        draw = int.from_bytes(digest[:8], "big") / float(2**64)
        return draw < rate

    @staticmethod
    def _provider_for_mode(provider: str) -> str:
        return provider if provider in {"ollama", "local"} else "local"

    def explain(self, decision: RoutingDecision) -> str:
        return (
            f"provider={decision.provider} tier={decision.model_tier} "
            f"reasoning={decision.reasoning_level} "
            f"depth={decision.prompt_depth} mode={decision.execution_mode} "
            f"rationale={decision.rationale}"
        )
