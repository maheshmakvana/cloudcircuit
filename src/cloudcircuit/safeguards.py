"""Core cloud spend safeguard logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class BudgetCheckResult:
    current_spend: float
    budget_limit: float
    usage_ratio: float
    remaining_budget: float
    is_warning: bool
    is_breached: bool


@dataclass(frozen=True, slots=True)
class AnomalyCheckResult:
    latest_spend: float
    baseline_mean: float
    threshold: float
    is_spike: bool


@dataclass(frozen=True, slots=True)
class CircuitBreakerDecision:
    is_open: bool
    allow_operation: bool
    retry_after_steps: int


def check_budget(
    current_spend: float,
    budget_limit: float,
    warning_ratio: float = 0.9,
) -> BudgetCheckResult:
    """Evaluate budget usage against warning and breach thresholds."""
    if budget_limit <= 0:
        raise ValueError("budget_limit must be > 0")
    if not (0 < warning_ratio <= 1):
        raise ValueError("warning_ratio must be in (0, 1]")
    if current_spend < 0:
        raise ValueError("current_spend must be >= 0")

    usage_ratio = current_spend / budget_limit
    remaining_budget = budget_limit - current_spend
    is_warning = usage_ratio >= warning_ratio
    is_breached = current_spend >= budget_limit
    return BudgetCheckResult(
        current_spend=current_spend,
        budget_limit=budget_limit,
        usage_ratio=usage_ratio,
        remaining_budget=remaining_budget,
        is_warning=is_warning,
        is_breached=is_breached,
    )


def check_anomaly_spike(
    spend_series: Sequence[float],
    spike_multiplier: float = 1.5,
    min_baseline: float = 0.0,
) -> AnomalyCheckResult:
    """
    Detect whether the latest spend point is an anomalous spike.

    Baseline is computed from all values except the latest.
    """
    if len(spend_series) < 2:
        raise ValueError("spend_series must contain at least 2 points")
    if spike_multiplier <= 1.0:
        raise ValueError("spike_multiplier must be > 1.0")
    if min_baseline < 0:
        raise ValueError("min_baseline must be >= 0")
    if any(value < 0 for value in spend_series):
        raise ValueError("spend_series values must be >= 0")

    latest_spend = float(spend_series[-1])
    history = spend_series[:-1]
    baseline_mean = sum(history) / len(history)
    effective_baseline = max(baseline_mean, min_baseline)
    threshold = effective_baseline * spike_multiplier
    is_spike = latest_spend > threshold
    return AnomalyCheckResult(
        latest_spend=latest_spend,
        baseline_mean=baseline_mean,
        threshold=threshold,
        is_spike=is_spike,
    )


def evaluate_circuit_breaker(
    consecutive_failures: int,
    failure_threshold: int = 3,
    cooldown_steps_remaining: int = 0,
) -> CircuitBreakerDecision:
    """Return deterministic breaker state from failure and cooldown counters."""
    if consecutive_failures < 0:
        raise ValueError("consecutive_failures must be >= 0")
    if failure_threshold <= 0:
        raise ValueError("failure_threshold must be > 0")
    if cooldown_steps_remaining < 0:
        raise ValueError("cooldown_steps_remaining must be >= 0")

    threshold_reached = consecutive_failures >= failure_threshold
    is_open = threshold_reached or cooldown_steps_remaining > 0
    allow_operation = not is_open
    retry_after_steps = cooldown_steps_remaining if is_open else 0
    return CircuitBreakerDecision(
        is_open=is_open,
        allow_operation=allow_operation,
        retry_after_steps=retry_after_steps,
    )
