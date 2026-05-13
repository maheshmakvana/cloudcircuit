# cloudcircuit

CloudCircuit is a Python library for **cloud cost control**, **real-time spend anomaly detection**, **budget overrun prevention**, and **circuit-breaker style safety automation**.

If you are searching for solutions like:
- prevent unexpected cloud bills
- detect cloud spend spikes
- add budget guardrails in Python
- implement FinOps automation for developers
- stop runaway infrastructure loops

this package is built for that exact problem set.

## Why this library exists

Many teams discover cloud overspend only after invoices land. A single misconfigured loop, unbounded worker fan-out, or retry storm can create massive costs in hours.

CloudCircuit provides deterministic primitives so you can add spend safety in:
- background jobs
- CI/CD workflows
- internal developer platforms
- API middleware
- scheduled FinOps monitors

## Features

- **Budget guardrails**: warning and hard-breach checks with explicit thresholds
- **Spend anomaly detection**: latest-point spike detection against baseline
- **Burn-rate monitoring**: detect hot spend acceleration before full breach
- **Forecasting**: project period-end spend and overrun amount
- **Circuit breaker decisions**: open/close logic for high-risk operations
- **Policy engine**: combine budget + anomaly + breaker into `allow/throttle/block`
- **Alert payload builder**: provider-agnostic payloads for Slack/webhooks/ops pipelines
- **Typed API**: dataclass results with clear fields for logs and audits

## Install

```bash
python -m pip install cloudcircuit
```

## Quickstart

```python
from cloudcircuit import (
    check_anomaly_spike,
    check_budget,
    check_burn_rate,
    evaluate_circuit_breaker,
    evaluate_spend_policy,
    forecast_budget_breach,
    make_alert_payload,
)

budget = check_budget(current_spend=920.0, budget_limit=1000.0, warning_ratio=0.9)
anomaly = check_anomaly_spike([120.0, 118.0, 121.0, 250.0], spike_multiplier=1.6)
burn = check_burn_rate([120.0, 118.0, 121.0, 250.0], hot_multiplier=1.4)
breaker = evaluate_circuit_breaker(consecutive_failures=0, failure_threshold=3)
forecast = forecast_budget_breach(
    current_spend=920.0,
    budget_limit=1000.0,
    periods_elapsed=22,
    total_periods=30,
)

policy = evaluate_spend_policy(budget=budget, anomaly=anomaly, breaker=breaker)
alert = make_alert_payload(policy, service="billing-worker", environment="prod")

print(policy.action, policy.severity)
print(forecast.projected_total_spend, forecast.will_breach)
print(burn.burn_rate_ratio, burn.is_hot)
print(alert)
```

## Common developer problems solved

1. **Runaway cron or queue workers**
   - Use anomaly + burn-rate checks every interval.
   - Auto-throttle workers when policy returns `throttle`.

2. **Unexpected month-end budget breach**
   - Use forecast checks daily or hourly.
   - Trigger remediation before hard limit is hit.

3. **No standardized cost incident signal**
   - Use `make_alert_payload` for consistent, structured incident events.

4. **Need a safe default during telemetry failure**
   - Combine breaker logic with fail-closed policy in critical paths.

## API overview

- `check_budget(...) -> BudgetCheckResult`
- `check_anomaly_spike(...) -> AnomalyCheckResult`
- `check_burn_rate(...) -> BurnRateResult`
- `forecast_budget_breach(...) -> ForecastResult`
- `evaluate_circuit_breaker(...) -> CircuitBreakerDecision`
- `evaluate_spend_policy(...) -> PolicyDecision`
- `make_alert_payload(...) -> dict[str, object]`

## SEO keywords (for discoverability)

cloud cost control python, finops python library, cloud budget guardrails, spend anomaly detection, prevent cloud bill shock, cost circuit breaker, cloud billing safety, cloud overspend monitoring, infrastructure cost alerts, developer finops toolkit

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m mypy src
```

## Roadmap ideas

- rolling window and percentile-based anomaly models
- provider adapters for AWS/GCP/Azure billing streams
- async event pipeline helpers
- OpenTelemetry metric exporters
- policy DSL for org-wide spend controls

## License

MIT
