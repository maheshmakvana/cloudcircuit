import pytest

from cloudcircuit.safeguards import (
    check_anomaly_robust,
    check_anomaly_spike,
    check_budget,
    check_burn_rate,
    evaluate_circuit_breaker,
    evaluate_spend_policy,
    forecast_budget_breach,
    make_alert_payload,
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


def test_anomaly_robust_mad_detects_spike_with_zero_mad() -> None:
    result = check_anomaly_robust([10.0, 10.0, 10.0, 25.0], method="mad", z_threshold=3.5)
    assert result.baseline_mean == 10.0
    assert result.threshold == 10.0
    assert result.is_spike is True


def test_anomaly_robust_mad_not_spike_on_stable_series() -> None:
    result = check_anomaly_robust([10.0, 10.0, 10.0, 10.0], method="mad")
    assert result.baseline_mean == 10.0
    assert result.threshold == 10.0
    assert result.is_spike is False


def test_anomaly_robust_mad_detects_spike_with_nonzero_mad() -> None:
    result = check_anomaly_robust([10.0, 10.0, 11.0, 10.0, 12.0, 11.0, 50.0], method="mad")
    assert result.baseline_mean == 10.5
    assert 0.0 < result.threshold < 50.0
    assert result.is_spike is True


def test_anomaly_robust_percentile_detects_spike() -> None:
    result = check_anomaly_robust(
        [10.0, 10.0, 10.0, 10.0, 50.0],
        method="percentile",
        percentile=0.95,
    )
    assert result.baseline_mean == 10.0
    assert result.threshold == 10.0
    assert result.is_spike is True


def test_anomaly_robust_percentile_not_spike() -> None:
    result = check_anomaly_robust(
        [10.0, 12.0, 11.0, 13.0, 12.8],
        method="percentile",
        percentile=0.95,
    )
    assert result.is_spike is False


def test_anomaly_robust_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        check_anomaly_robust([1.0], method="mad")
    with pytest.raises(ValueError):
        check_anomaly_robust([1.0, -1.0], method="mad")
    with pytest.raises(ValueError):
        check_anomaly_robust([1.0, 2.0], method="unknown")  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        check_anomaly_robust([1.0, 2.0], method="mad", z_threshold=0.0)
    with pytest.raises(ValueError):
        check_anomaly_robust([1.0, 2.0], method="mad", min_mad=-0.1)
    with pytest.raises(ValueError):
        check_anomaly_robust([1.0, 2.0], method="mad", min_baseline=-0.1)

    with pytest.raises(ValueError):
        check_anomaly_robust([1.0, 2.0], method="percentile", percentile=1.0)


def test_anomaly_robust_min_baseline_floor() -> None:
    mad = check_anomaly_robust([0.0, 0.0, 0.0, 0.4], method="mad", min_baseline=0.5)
    assert mad.threshold == 0.5
    assert mad.is_spike is False

    pct = check_anomaly_robust(
        [0.0, 0.0, 0.0, 0.4],
        method="percentile",
        percentile=0.95,
        min_baseline=0.5,
    )
    assert pct.threshold == 0.5
    assert pct.is_spike is False


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


def test_burn_rate_detects_hot_run() -> None:
    result = check_burn_rate([10.0, 10.0, 20.0], hot_multiplier=1.5)
    assert result.average_spend == 10.0
    assert result.burn_rate_ratio == 2.0
    assert result.is_hot is True


def test_burn_rate_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        check_burn_rate([5.0], hot_multiplier=1.5)
    with pytest.raises(ValueError):
        check_burn_rate([5.0, -1.0], hot_multiplier=1.5)
    with pytest.raises(ValueError):
        check_burn_rate([5.0, 6.0], hot_multiplier=1.0)


def test_forecast_budget_breach() -> None:
    result = forecast_budget_breach(
        current_spend=500.0,
        budget_limit=800.0,
        periods_elapsed=10,
        total_periods=20,
    )
    assert result.projected_total_spend == 1000.0
    assert result.projected_overrun == 200.0
    assert result.will_breach is True


def test_forecast_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        forecast_budget_breach(-1.0, 100.0, 1, 10)
    with pytest.raises(ValueError):
        forecast_budget_breach(1.0, 0.0, 1, 10)
    with pytest.raises(ValueError):
        forecast_budget_breach(1.0, 100.0, 0, 10)
    with pytest.raises(ValueError):
        forecast_budget_breach(1.0, 100.0, 11, 10)


def test_evaluate_policy_block_throttle_allow() -> None:
    budget_ok = check_budget(10.0, 100.0, 0.8)
    budget_warn = check_budget(85.0, 100.0, 0.8)
    anomaly_ok = check_anomaly_spike([10.0, 10.0, 10.0, 11.0], 1.5)
    anomaly_spike = check_anomaly_spike([10.0, 10.0, 10.0, 20.0], 1.5)
    breaker_closed = evaluate_circuit_breaker(0, 3, 0)
    breaker_open = evaluate_circuit_breaker(3, 3, 0)

    allow = evaluate_spend_policy(budget_ok, anomaly_ok, breaker_closed)
    throttle = evaluate_spend_policy(budget_warn, anomaly_ok, breaker_closed)
    block = evaluate_spend_policy(budget_ok, anomaly_spike, breaker_open)

    assert allow.action == "allow"
    assert throttle.action == "throttle"
    assert block.action == "block"


def test_make_alert_payload() -> None:
    budget = check_budget(95.0, 100.0, 0.9)
    anomaly = check_anomaly_spike([20.0, 20.0, 20.0, 35.0], 1.5)
    breaker = evaluate_circuit_breaker(0, 3, 0)
    policy = evaluate_spend_policy(budget, anomaly, breaker)

    payload = make_alert_payload(policy, service="billing-worker", environment="prod")
    assert payload["service"] == "billing-worker"
    assert payload["environment"] == "prod"
    assert payload["action"] == "throttle"
    assert payload["severity"] == "warning"

    with pytest.raises(ValueError):
        make_alert_payload(policy, service="", environment="prod")
