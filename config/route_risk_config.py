"""Centralized route-risk classification configuration.

Thresholds here are analytical triage parameters, NOT learned business
risk: they decide when an observed historical cascade rate earns a HIGH /
MEDIUM label so reviewers can sort routes. Callers override them via
:func:`resolve_risk_config`; the underlying empirical metrics are always
reported alongside any label.
"""

from __future__ import annotations

from typing import Any, Optional

DEFAULT_ROUTE_RISK_CONFIG: dict[str, Any] = {
    # HIGH when cascade_rate (%) is at or above this level.
    "high_cascade_rate": 40.0,
    # MEDIUM when cascade_rate (%) is at or above this level, or when
    # cascade_recurrence (0..1 share of delay periods with a cascade)
    # is at or above "medium_recurrence".
    "medium_cascade_rate": 20.0,
    "medium_recurrence": 0.5,
    # Reliability guards: routes below these counts are INSUFFICIENT_DATA
    # instead of LOW, so tiny samples are never labeled safe.
    "min_delayed_shipments": 5,
    "min_periods": 2,
}


def resolve_risk_config(overrides: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Merge caller overrides onto defaults and validate the result.

    Raises:
        ValueError: On unknown keys, non-numeric thresholds, rates outside
            0..100, recurrence outside 0..1, medium above high, or guards
            below 1.
    """
    config = dict(DEFAULT_ROUTE_RISK_CONFIG)
    overrides = overrides or {}
    unknown = sorted(set(overrides) - set(config))
    if unknown:
        raise ValueError(f"Unknown route-risk config keys: {unknown}.")
    config.update(overrides)
    for key in ("high_cascade_rate", "medium_cascade_rate"):
        value = config[key]
        if (
            value is None
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 100
        ):
            raise ValueError(f"Config '{key}' must be a number in 0..100.")
    recurrence = config["medium_recurrence"]
    if (
        recurrence is None
        or isinstance(recurrence, bool)
        or not isinstance(recurrence, (int, float))
        or not 0 <= recurrence <= 1
    ):
        raise ValueError("Config 'medium_recurrence' must be a number in 0..1.")
    if config["medium_cascade_rate"] > config["high_cascade_rate"]:
        raise ValueError("Config 'medium_cascade_rate' must be <= 'high_cascade_rate'.")
    for key in ("min_delayed_shipments", "min_periods"):
        value = config[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"Config '{key}' must be an integer >= 1.")
    return config
