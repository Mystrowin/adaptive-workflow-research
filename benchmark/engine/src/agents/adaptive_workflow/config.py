from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AdaptiveWorkflowConfig:
    """Minimal routing configuration required by the published benchmark."""

    workflow_mode: str = "BALANCED"
    preferred_local_provider: str = "ollama"
    preferred_cloud_provider: str = "ollama"
    exploration_rate: float = 0.0

    def __post_init__(self) -> None:
        self.workflow_mode = self.workflow_mode.upper()
        if self.workflow_mode not in {"FAST", "BALANCED", "BEST"}:
            raise ValueError("workflow_mode must be FAST, BALANCED, or BEST")
        if self.preferred_local_provider not in {"ollama", "local"}:
            raise ValueError("benchmark providers must be local")
        if self.preferred_cloud_provider not in {"ollama", "local"}:
            raise ValueError("benchmark fallback providers must be local")
        if not 0.0 <= self.exploration_rate <= 1.0:
            raise ValueError("exploration_rate must be between zero and one")
