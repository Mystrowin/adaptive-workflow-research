from __future__ import annotations

from collections.abc import Iterable

from .models import BenchmarkTask, BenchmarkTier, FrozenBudget, FrozenTaskBudget, ModelSpec

COST_PROXY_UNIT = "billion_parameter_token_units"


def generation_cost_proxy(model: ModelSpec, output_tokens: int | None) -> float | None:
    if output_tokens is None:
        return None
    return model.parameter_billions * output_tokens


def total_token_cost_proxy(
    model: ModelSpec,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    return model.parameter_billions * (input_tokens + output_tokens)


def freeze_budget(
    tasks: Iterable[BenchmarkTask],
    models: Iterable[ModelSpec],
    *,
    max_output_tokens: int,
) -> FrozenBudget:
    task_list = tuple(tasks)
    model_by_tier = {model.tier: model for model in models}
    if set(model_by_tier) != set(BenchmarkTier):
        raise ValueError("budget requires FAST, BALANCED, and BEST model specifications")
    for model in model_by_tier.values():
        model.validate()

    best_weight = model_by_tier[BenchmarkTier.BEST].parameter_billions
    total_b0 = 0.0
    generation_g0 = 0.0
    frozen_tasks: list[FrozenTaskBudget] = []
    for task in task_list:
        if task.reference_input_tokens < 0:
            raise ValueError(f"negative reference token count for {task.identity()}")
        token_allowance = task.reference_input_tokens + max_output_tokens
        reservations = {
            tier.value: model_by_tier[tier].parameter_billions * token_allowance
            for tier in BenchmarkTier
        }
        adaptive_limit = sum(reservations.values())
        total_b0 += best_weight * token_allowance
        generation_g0 += best_weight * max_output_tokens
        frozen_tasks.append(
            FrozenTaskBudget(
                task_identity=task.identity(),
                reference_input_tokens=task.reference_input_tokens,
                max_output_tokens=max_output_tokens,
                reservations=reservations,
                adaptive_limit=adaptive_limit,
            )
        )
    if not frozen_tasks:
        raise ValueError("budget requires at least one task")
    fractions = (0.25, 0.50, 0.75, 1.0)
    return FrozenBudget(
        unit=COST_PROXY_UNIT,
        max_output_tokens=max_output_tokens,
        task_budgets=tuple(frozen_tasks),
        total_token_baseline_b0=total_b0,
        generation_baseline_g0=generation_g0,
        total_token_cutoffs=tuple(total_b0 * fraction for fraction in fractions),
        generation_cutoffs=tuple(generation_g0 * fraction for fraction in fractions),
    )


def budget_preflight_warnings(
    budget: FrozenBudget,
    *,
    calibration_total_proxy: float | None = None,
    calibration_generation_proxy: float | None = None,
) -> list[str]:
    """Return conservative warnings before a held-out run is launched.

    The frozen B0 cutoffs are intentionally not changed here.  A calibration
    workload, when supplied, is the only permissible basis for deciding
    whether those cutoffs will intersect realistic expenditure.  Without one,
    preparation must warn rather than silently treating reservations as
    expected usage.
    """

    warnings: list[str] = []
    if calibration_total_proxy is None or calibration_generation_proxy is None:
        warnings.append(
            "no calibration workload was supplied; frozen budget cutoffs may be nondiscriminating"
        )
        return warnings
    if calibration_total_proxy < budget.total_token_cutoffs[0]:
        warnings.append(
            "calibration total-token expenditure is below the first frozen cutoff; "
            "select realistic checkpoints before held-out evaluation"
        )
    if calibration_generation_proxy < budget.generation_cutoffs[0]:
        warnings.append(
            "calibration generation expenditure is below the first frozen cutoff; "
            "select realistic checkpoints before held-out evaluation"
        )
    return warnings
