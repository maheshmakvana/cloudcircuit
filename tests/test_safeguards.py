import pytest

from cloudcircuit.safeguards import (
    check_anomaly_spike,
    check_budget,
    evaluate_circuit_breaker,
)


def test_budget_ok_without_warning() -> None:
    result = check_budget(current_spend=40.0, budget_limit=100.0, warning_ratio=0.8)
    assert result.usage_ratio == 0.4
    assert result.remaining_budget == 60.0
    assert result.is_warning is False
    assert result.is_breached is False


def test_budget_warning_and_breach() -> None:
    result = check_budget(current_spend=100.0, budget_limit=100.0, warning_ratio=0.8)
    assert result.is_warning is True
    assert result.is_breached is True
    assert result.remaining_budget == 0.0


@pytest.mark.parametrize(
    ("current_spend", "budget_limit", "warning_ratio"),
    [(-1.0, 100.0, 0.9), (10.0, 0.0, 0.9), (10.0, 100.0, 0.0)],
)
def test_budget_invalid_inputs(
    current_spend: float, budget_limit: float, warning_ratio: float
) -> None:
    with pytest.raises(ValueError):
        check_budget(current_spend, budget_limit, warning_ratio)


def test_anomaly_spike_detected() -> None:
    result = check_anomaly_spike([10.0, 10.0, 10.0, 20.0], spike_multiplier=1.5)
    assert result.baseline_mean == 10.0
    assert result.threshold == 15.0
    assert result.is_spike is True


def test_anomaly_not_spike_with_min_baseline() -> None:
    result = check_anomaly_spike([0.0, 0.0, 0.0, 0.4], spike_multiplier=2.0, min_baseline=0.5)
    assert result.baseline_mean == 0.0
    assert result.threshold == 1.0
    assert result.is_spike is False


def test_anomaly_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        check_anomaly_spike([1.0], spike_multiplier=1.5)
    with pytest.raises(ValueError):
        check_anomaly_spike([1.0, 2.0], spike_multiplier=1.0)
    with pytest.raises(ValueError):
        check_anomaly_spike([1.0, -1.0], spike_multiplier=2.0)


def test_circuit_breaker_allows_operation_below_threshold() -> None:
    decision = evaluate_circuit_breaker(consecutive_failures=2, failure_threshold=3)
    assert decision.is_open is False
    assert decision.allow_operation is True
    assert decision.retry_after_steps == 0


def test_circuit_breaker_opens_at_threshold() -> None:
    decision = evaluate_circuit_breaker(consecutive_failures=3, failure_threshold=3)
    assert decision.is_open is True
    assert decision.allow_operation is False


def test_circuit_breaker_stays_open_during_cooldown() -> None:
    decision = evaluate_circuit_breaker(
        consecutive_failures=0, failure_threshold=3, cooldown_steps_remaining=2
    )
    assert decision.is_open is True
    assert decision.allow_operation is False
    assert decision.retry_after_steps == 2


def test_circuit_breaker_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        evaluate_circuit_breaker(consecutive_failures=-1)
    with pytest.raises(ValueError):
        evaluate_circuit_breaker(consecutive_failures=0, failure_threshold=0)
    with pytest.raises(ValueError):
        evaluate_circuit_breaker(consecutive_failures=0, cooldown_steps_remaining=-1)
