# cloudcircuit

Lightweight, deterministic safeguards you can embed into cloud spend enforcement:

- Budget usage checks (`check_budget`)
- Spend spike detection (`check_anomaly_spike`)
- Simple circuit-breaker decisioning (`evaluate_circuit_breaker`)

This package focuses on the core logic only. You bring your own metrics ingestion (billing exports, CloudWatch,
BigQuery, etc.) and enforcement (alerts, policy, throttling, kill-switches).

## Install

From PyPI (once published):

```bash
python -m pip install cloudcircuit
```

For local development from this repo:

```bash
cd cloudcircuit
python -m pip install -e ".[dev]"
pytest
```

## Usage

The public APIs currently live in `cloudcircuit.safeguards`:

```python
from cloudcircuit.safeguards import (
    check_anomaly_spike,
    check_budget,
    evaluate_circuit_breaker,
)
```

All functions are deterministic and raise `ValueError` on invalid inputs (negative spend, invalid thresholds, etc.).

## Quickstart

### 1) Budget guardrail

```python
from cloudcircuit.safeguards import check_budget

result = check_budget(current_spend=920.0, budget_limit=1000.0, warning_ratio=0.9)

if result.is_breached:
    # Hard stop: disable non-essential workloads, block expensive operations, etc.
    print("BUDGET BREACHED:", result)
elif result.is_warning:
    # Soft stop: alert, reduce concurrency, apply stricter policy.
    print("BUDGET WARNING:", result)
else:
    print("OK:", result)
```

### 2) Spike detection (latest point vs baseline)

```python
from cloudcircuit.safeguards import check_anomaly_spike

# Example: daily spend totals (or hourly), latest point last.
series = [120.0, 125.0, 118.0, 260.0]

result = check_anomaly_spike(series, spike_multiplier=1.5, min_baseline=0.0)
if result.is_spike:
    print("SPEND SPIKE:", result.latest_spend, "threshold:", result.threshold)
```

### 3) Circuit-breaker decisioning

```python
from cloudcircuit.safeguards import evaluate_circuit_breaker

decision = evaluate_circuit_breaker(
    consecutive_failures=3,
    failure_threshold=3,
    cooldown_steps_remaining=0,
)

if not decision.allow_operation:
    print("BREAKER OPEN; retry after steps:", decision.retry_after_steps)
```

## Architecture

Current modules:

- `src/cloudcircuit/safeguards.py`: core dataclasses and guardrail functions:
  - `BudgetCheckResult`, `check_budget`
  - `AnomalyCheckResult`, `check_anomaly_spike`
  - `CircuitBreakerDecision`, `evaluate_circuit_breaker`
- `tests/test_safeguards.py`: contract tests for edge cases and input validation.

Design goals:

- Deterministic, side-effect free logic (easy to unit-test and reason about)
- Minimal dependencies (safe to embed in CLIs, jobs, and services)
- Typed, explicit return objects (so callers can log/audit decisions)

Non-goals (by design):

- Cloud provider integrations (metrics ingestion / policy enforcement)
- Stateful breaker implementation (persistence, jitter/backoff, distributed locks)

## Deployment Guide

Typical deployment looks like a thin integration layer around `cloudcircuit`:

1. Collect spend and operational signals.
   - Spend totals: billing exports, cost explorer, warehouse tables, or internal chargeback.
   - Failure counters: request error rates, provider API failures, budget retrieval failures.
2. Evaluate guardrails.
   - `check_budget()` for hard/soft budget thresholds.
   - `check_anomaly_spike()` to catch sudden jumps early.
   - `evaluate_circuit_breaker()` to gate high-cost operations when systems are unstable.
3. Enforce decisions.
   - Alerting: Slack/email/PagerDuty with `*_Result` fields for audit context.
   - Throttling: reduce concurrency, disable non-critical jobs, or switch to cheaper defaults.
   - Kill-switch: block expensive actions when `is_breached` is true.
4. Persist state externally when needed.
   - Store the last N spend points, consecutive failure counts, and cooldown counters in your DB/redis.
   - Run the evaluator on a schedule (cron / Airflow / Cloud Scheduler) or inline per request.

Recommended patterns:

- Treat spend series as monotonic time buckets (hourly/daily) and pass the newest point last.
- Log the full result objects (they are small and serializable) so you can explain why a safeguard tripped.
- Prefer "fail closed" for high-risk operations: if your metrics pipeline is down, open the breaker or block
  expensive actions until signals recover.

## License

MIT (see `pyproject.toml` for the current license declaration).
