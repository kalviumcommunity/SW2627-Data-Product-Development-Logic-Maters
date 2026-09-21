"""Centralized alert configuration.

All alert thresholds live here - never scattered across modules. Every
value is a configurable demonstration/business-rule parameter: the
project has no production processed data yet, so these thresholds were
NOT learned from real observations. Callers (and operators) override
them via :func:`resolve_config`; setting a threshold to None disables
that alert type entirely.
"""

from __future__ import annotations

from typing import Any, Optional

DEFAULT_ALERT_CONFIG: dict[str, Any] = {
    # Delay-rate alerts: entity delay_rate (%) at or above the threshold.
    "delay_rate_threshold": 30.0,
    # Escalates to CRITICAL at or above this rate.
    "critical_delay_rate": 50.0,
    # Minimum shipments behind a rate before it can alert (reliability
    # guard so tiny samples do not page anyone).
    "min_shipments_for_rate_alert": 5,
    # Duration alerts: worst per-shipment delay_duration at/above threshold
    # (same unit as the delay_duration column).
    "delay_duration_threshold": 60.0,
    # Escalates to CRITICAL at or above this duration.
    "critical_delay_duration": 120.0,
    # Cascade alerts: any cascade candidate from analysis/cascade_analysis
    # alerts (no new cascade definition here). Depth >= this value is
    # CRITICAL, depth 1 is WARNING.
    "critical_cascade_depth": 2,
    # Near-miss watch list: metric at or above ratio * threshold earns an
    # INFO alert (None disables INFO alerts).
    "near_miss_ratio": 0.8,
    # Optional bounds for cascade detection reuse (None = defaults).
    "cascade_min_delay_duration": None,
    "cascade_max_downstream_gap": None,
}

_SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


def resolve_config(overrides: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Merge caller overrides onto defaults and validate the result.

    Raises:
        ValueError: On unknown keys, negative thresholds, or a critical
            level set below its corresponding warning threshold.
    """
    config = dict(DEFAULT_ALERT_CONFIG)
    overrides = overrides or {}
    unknown = sorted(set(overrides) - set(config))
    if unknown:
        raise ValueError(f"Unknown alert config keys: {unknown}.")
    config.update(overrides)
    for key in (
        "delay_rate_threshold",
        "critical_delay_rate",
        "delay_duration_threshold",
        "critical_delay_duration",
    ):
        value = config[key]
        if value is not None and (not isinstance(value, (int, float)) or value < 0):
            raise ValueError(f"Config '{key}' must be a non-negative number or None.")
    min_ship = config["min_shipments_for_rate_alert"]
    if not isinstance(min_ship, int) or isinstance(min_ship, bool) or min_ship < 1:
        raise ValueError("Config 'min_shipments_for_rate_alert' must be an integer >= 1.")
    if (
        config["delay_rate_threshold"] is not None
        and config["critical_delay_rate"] is not None
        and config["critical_delay_rate"] < config["delay_rate_threshold"]
    ):
        raise ValueError("Config 'critical_delay_rate' must be >= 'delay_rate_threshold'.")
    if (
        config["delay_duration_threshold"] is not None
        and config["critical_delay_duration"] is not None
        and config["critical_delay_duration"] < config["delay_duration_threshold"]
    ):
        raise ValueError(
            "Config 'critical_delay_duration' must be >= 'delay_duration_threshold'."
        )
    ratio = config["near_miss_ratio"]
    if ratio is not None and (
        not isinstance(ratio, (int, float)) or not 0 < ratio < 1
    ):
        raise ValueError("Config 'near_miss_ratio' must be in (0, 1) or None.")
    depth = config["critical_cascade_depth"]
    if not isinstance(depth, int) or isinstance(depth, bool) or depth < 1:
        raise ValueError("Config 'critical_cascade_depth' must be an integer >= 1.")
    return config


def severity_rank(severity: str) -> int:
    """Sort key for severities (unknown values sort below INFO)."""
    return _SEVERITY_ORDER.get(severity, -1)
