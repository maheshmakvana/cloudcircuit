"""Core cloud spend safeguard logic."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, floor
from typing import Literal


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


Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True, slots=True)
class BurnRateResult:
    latest_spend: float
    average_spend: float
    burn_rate_ratio: float
    is_hot: bool


@dataclass(frozen=True, slots=True)
class ForecastResult:
    current_spend: float
    budget_limit: float
    periods_elapsed: int
    total_periods: int
    projected_total_spend: float
    projected_overrun: float
    will_breach: bool


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: Literal["allow", "throttle", "block"]
    reason: str
    severity: Severity
    budget: BudgetCheckResult
    anomaly: AnomalyCheckResult
    breaker: CircuitBreakerDecision


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


def _median(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("values must be non-empty")
    sorted_values = sorted(float(value) for value in values)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def _quantile(values: Sequence[float], p: float) -> float:
    if not values:
        raise ValueError("values must be non-empty")
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0, 1)")
    sorted_values = sorted(float(value) for value in values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = p * (len(sorted_values) - 1)
    lo = int(floor(rank))
    hi = int(ceil(rank))
    if lo == hi:
        return sorted_values[lo]
    weight = rank - lo
    return sorted_values[lo] + weight * (sorted_values[hi] - sorted_values[lo])


def check_anomaly_robust(
    spend_series: Sequence[float],
    *,
    method: Literal["mad", "percentile"] = "mad",
    z_threshold: float = 3.5,
    min_mad: float = 0.0,
    percentile: float = 0.95,
    min_baseline: float = 0.0,
) -> AnomalyCheckResult:
    """
    Robust spend spike detection using MAD or percentile thresholding.

    - MAD method uses median + z * (MAD / 0.6745) as a robust z-score threshold.
    - Percentile method uses a historical percentile as the spike threshold.

    Baseline is computed from all values except the latest.
    """
    if len(spend_series) < 2:
        raise ValueError("spend_series must contain at least 2 points")
    if any(value < 0 for value in spend_series):
        raise ValueError("spend_series values must be >= 0")
    if min_baseline < 0:
        raise ValueError("min_baseline must be >= 0")

    if method == "mad":
        if z_threshold <= 0:
            raise ValueError("z_threshold must be > 0")
        if min_mad < 0:
            raise ValueError("min_mad must be >= 0")
    elif method == "percentile":
        if not (0.0 < percentile < 1.0):
            raise ValueError("percentile must be in (0, 1)")
    else:
        raise ValueError("method must be 'mad' or 'percentile'")

    latest_spend = float(spend_series[-1])
    history = spend_series[:-1]

    if method == "mad":
        baseline_location = _median(history)
        abs_deviations = [abs(float(value) - baseline_location) for value in history]
        mad = max(_median(abs_deviations), float(min_mad))
        effective_location = max(baseline_location, float(min_baseline))
        robust_sigma = mad / 0.6745 if mad > 0 else 0.0
        threshold = effective_location + (float(z_threshold) * robust_sigma)
    else:
        baseline_location = _quantile(history, float(percentile))
        threshold = max(baseline_location, float(min_baseline))

    is_spike = latest_spend > threshold
    return AnomalyCheckResult(
        latest_spend=latest_spend,
        baseline_mean=float(baseline_location),
        threshold=float(threshold),
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


def check_burn_rate(
    spend_series: Sequence[float],
    hot_multiplier: float = 1.4,
) -> BurnRateResult:
    """Compare latest spend bucket to the historical average."""
    if len(spend_series) < 2:
        raise ValueError("spend_series must contain at least 2 points")
    if hot_multiplier <= 1.0:
        raise ValueError("hot_multiplier must be > 1.0")
    if any(value < 0 for value in spend_series):
        raise ValueError("spend_series values must be >= 0")

    latest_spend = float(spend_series[-1])
    average_spend = sum(spend_series[:-1]) / (len(spend_series) - 1)
    if average_spend == 0:
        burn_rate_ratio = float("inf") if latest_spend > 0 else 1.0
    else:
        burn_rate_ratio = latest_spend / average_spend
    is_hot = burn_rate_ratio >= hot_multiplier
    return BurnRateResult(
        latest_spend=latest_spend,
        average_spend=average_spend,
        burn_rate_ratio=burn_rate_ratio,
        is_hot=is_hot,
    )


def forecast_budget_breach(
    current_spend: float,
    budget_limit: float,
    periods_elapsed: int,
    total_periods: int,
) -> ForecastResult:
    """Forecast total spend at period end using a simple linear projection."""
    if current_spend < 0:
        raise ValueError("current_spend must be >= 0")
    if budget_limit <= 0:
        raise ValueError("budget_limit must be > 0")
    if periods_elapsed <= 0:
        raise ValueError("periods_elapsed must be > 0")
    if total_periods <= 0:
        raise ValueError("total_periods must be > 0")
    if periods_elapsed > total_periods:
        raise ValueError("periods_elapsed must be <= total_periods")

    projected_total_spend = (current_spend / periods_elapsed) * total_periods
    projected_overrun = max(0.0, projected_total_spend - budget_limit)
    return ForecastResult(
        current_spend=current_spend,
        budget_limit=budget_limit,
        periods_elapsed=periods_elapsed,
        total_periods=total_periods,
        projected_total_spend=projected_total_spend,
        projected_overrun=projected_overrun,
        will_breach=projected_total_spend >= budget_limit,
    )


def evaluate_spend_policy(
    budget: BudgetCheckResult,
    anomaly: AnomalyCheckResult,
    breaker: CircuitBreakerDecision,
) -> PolicyDecision:
    """Combine budget, anomaly, and breaker state into one actionable decision."""
    if budget.is_breached or breaker.is_open:
        reason = "Budget breached or circuit breaker open"
        return PolicyDecision("block", reason, "critical", budget, anomaly, breaker)
    if budget.is_warning or anomaly.is_spike:
        reason = "Budget warning or spend spike detected"
        return PolicyDecision("throttle", reason, "warning", budget, anomaly, breaker)
    return PolicyDecision("allow", "All safeguards healthy", "info", budget, anomaly, breaker)


def make_alert_payload(
    policy: PolicyDecision,
    service: str,
    environment: str,
) -> dict[str, object]:
    """Build a provider-agnostic alert payload for logs, Slack, or webhooks."""
    if not service:
        raise ValueError("service must be non-empty")
    if not environment:
        raise ValueError("environment must be non-empty")
    return {
        "service": service,
        "environment": environment,
        "action": policy.action,
        "severity": policy.severity,
        "reason": policy.reason,
        "budget": {
            "current_spend": policy.budget.current_spend,
            "budget_limit": policy.budget.budget_limit,
            "usage_ratio": policy.budget.usage_ratio,
            "remaining_budget": policy.budget.remaining_budget,
        },
        "anomaly": {
            "latest_spend": policy.anomaly.latest_spend,
            "baseline_mean": policy.anomaly.baseline_mean,
            "threshold": policy.anomaly.threshold,
            "is_spike": policy.anomaly.is_spike,
        },
        "breaker": {
            "is_open": policy.breaker.is_open,
            "allow_operation": policy.breaker.allow_operation,
            "retry_after_steps": policy.breaker.retry_after_steps,
        },
    }
