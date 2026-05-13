"""CloudCircuit package."""

from cloudcircuit.safeguards import (
    AnomalyCheckResult,
    BudgetCheckResult,
    BurnRateResult,
    CircuitBreakerDecision,
    ForecastResult,
    PolicyDecision,
    check_anomaly_robust,
    check_anomaly_spike,
    check_budget,
    check_burn_rate,
    evaluate_circuit_breaker,
    evaluate_spend_policy,
    forecast_budget_breach,
    make_alert_payload,
)

__version__ = "0.3.0"
__all__ = [
    "__version__",
    "AnomalyCheckResult",
    "BudgetCheckResult",
    "BurnRateResult",
    "CircuitBreakerDecision",
    "ForecastResult",
    "PolicyDecision",
    "check_anomaly_robust",
    "check_anomaly_spike",
    "check_budget",
    "check_burn_rate",
    "evaluate_circuit_breaker",
    "evaluate_spend_policy",
    "forecast_budget_breach",
    "make_alert_payload",
]
