"""Centralized configuration for the route-cascade prediction baseline.

All values are analytical parameters with documented justification, not
learned business thresholds. Callers override them via
:func:`resolve_prediction_config`; every training run records the
resolved config inside its model artifact so results stay reproducible.

The minimum-data guards below follow two rules of thumb:

* events-per-variable (EPV): a logistic model with ~10 features needs on
  the order of 100 positive examples for stable coefficients, hence
  ``min_cascade_positives``;
* split stability: each of the train/test periods needs enough positives
  for its metrics (precision/recall/AUC) to be defined and non-degenerate,
  hence ``min_train_positives`` / ``min_test_positives``.
"""

from __future__ import annotations

from typing import Any, Optional

DEFAULT_PREDICTION_CONFIG: dict[str, Any] = {
    # Population guards (delayed-shipment grain: one row per shipment with
    # an observed initial delay).
    "min_delayed_shipments": 200,
    "min_cascade_positives": 50,
    # Chronological split: earlier ``train_fraction`` of delayed shipments
    # (by initial-delay time) trains, the later remainder validates.
    "train_fraction": 0.7,
    "min_train_positives": 10,
    "min_test_positives": 10,
    # Temporal coverage: distinct calendar dates spanned by initial delays.
    # Fewer than this means the chronological split cannot separate an
    # earlier training period from a later validation period.
    "min_observed_days": 2,
    # Model fitting (deterministic full-batch gradient descent, NumPy only).
    "learning_rate": 0.5,
    "max_iterations": 2000,
    "l2_penalty": 1.0,
    # Decision threshold applied to the estimated probability.
    "decision_threshold": 0.5,
    # Class imbalance: "balanced" reweights by inverse train frequency,
    # None keeps uniform weights. Auto-selection applies "balanced" only
    # when the train minority share falls below this level.
    "class_weight": None,
    "auto_balance_minority_share": 0.35,
    # Model identifier recorded in every artifact.
    "model_version": "route-cascade-baseline-v1",
}


def resolve_prediction_config(
    overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Merge caller overrides onto defaults and validate the result.

    Raises:
        ValueError: On unknown keys or out-of-range values.
    """
    config = dict(DEFAULT_PREDICTION_CONFIG)
    overrides = overrides or {}
    unknown = sorted(set(overrides) - set(config))
    if unknown:
        raise ValueError(f"Unknown prediction config keys: {unknown}.")
    config.update(overrides)
    for key in (
        "min_delayed_shipments",
        "min_cascade_positives",
        "min_train_positives",
        "min_test_positives",
        "min_observed_days",
        "max_iterations",
    ):
        value = config[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"Config '{key}' must be an integer >= 1.")
    train_fraction = config["train_fraction"]
    if (
        train_fraction is None
        or isinstance(train_fraction, bool)
        or not isinstance(train_fraction, (int, float))
        or not 0.0 < float(train_fraction) < 1.0
    ):
        raise ValueError("Config 'train_fraction' must be a number in (0, 1).")
    for key in ("learning_rate", "l2_penalty"):
        value = config[key]
        if (
            value is None
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or float(value) < 0
        ):
            raise ValueError(f"Config '{key}' must be a non-negative number.")
    threshold = config["decision_threshold"]
    if (
        threshold is None
        or isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not 0.0 < float(threshold) < 1.0
    ):
        raise ValueError("Config 'decision_threshold' must be a number in (0, 1).")
    if config["class_weight"] not in (None, "balanced"):
        raise ValueError("Config 'class_weight' must be None or 'balanced'.")
    minority = config["auto_balance_minority_share"]
    if (
        minority is None
        or isinstance(minority, bool)
        or not isinstance(minority, (int, float))
        or not 0.0 < float(minority) <= 0.5
    ):
        raise ValueError(
            "Config 'auto_balance_minority_share' must be a number in (0, 0.5]."
        )
    if not isinstance(config["model_version"], str) or not config["model_version"]:
        raise ValueError("Config 'model_version' must be a non-empty string.")
    return config
