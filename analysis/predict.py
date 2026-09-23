"""Inference API for the route-cascade prediction baseline.

Loads a trained JSON artifact (see :mod:`analysis.prediction_model`) and
produces *estimated* cascade probabilities — never certainties. Two entry
points:

* :func:`predict_for_shipments` — score the delayed shipments of an
  integrated dataset with the stored training history (route statistics
  stay train-only; no test leakage by construction);
* :func:`predict_single` — score one validated prediction-time record
  (route, initial-delay context) without needing the full dataset.

Route-level output (:func:`route_prediction_summary`) aggregates
shipment probabilities per route and keeps the model's estimated
probability visually separate from the historical empirical rate, which
callers join in from :func:`analysis.route_risk.route_cascade_risk`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

from analysis.prediction_features import (
    TARGET_COLUMN,
    _add_time_features,
    apply_route_history,
    assert_no_leakage_columns,
    build_delayed_shipment_table,
    build_feature_matrix,
)
from analysis.prediction_model import (
    load_model_artifact,
    predict_proba_from_params,
)

PathLike = Union[str, Path]

REQUIRED_RECORD_FIELDS = (
    "route",
    "initial_delay_duration",
    "initial_scan_type",
    "initial_warehouse",
)

PREDICTION_COLUMNS = [
    "route",
    "prediction",
    "cascade_probability",
    "model_version",
]


def validate_inference_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate one prediction-time record (clear error when unusable).

    Required: ``route`` (non-blank string). Optional with safe defaults:
    ``initial_delay_duration`` (non-negative number, default 0.0),
    ``initial_event_seq`` (integer >= 1, default 1),
    ``initial_scan_type`` / ``initial_warehouse`` (default ``"unknown"``),
    ``initial_delay_time`` (parseable timestamp, default noon UTC today —
    only used for calendar features).
    """
    if not isinstance(record, dict):
        raise ValueError("Inference record must be a mapping.")
    route = record.get("route")
    if route is None or not str(route).strip():
        raise ValueError("Inference record requires a non-blank 'route'.")
    duration = record.get("initial_delay_duration", 0.0)
    try:
        duration_value = float(duration)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"'initial_delay_duration' must be a number, got {duration!r}."
        ) from exc
    if duration_value < 0:
        raise ValueError("'initial_delay_duration' must be non-negative.")
    seq = record.get("initial_event_seq", 1)
    try:
        seq_value = int(seq)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'initial_event_seq' must be an integer, got {seq!r}.") from exc
    if seq_value < 1:
        raise ValueError("'initial_event_seq' must be >= 1.")
    timestamp = record.get("initial_delay_time")
    if timestamp is None:
        cleaned_time = pd.Timestamp.now(tz="UTC").replace(
            hour=12, minute=0, second=0, microsecond=0
        )
    else:
        cleaned_time = pd.to_datetime(timestamp, errors="coerce", utc=True)
        if pd.isna(cleaned_time):
            raise ValueError(
                f"'initial_delay_time' is not a parseable timestamp: {timestamp!r}."
            )
    return {
        "route": str(route).strip(),
        "initial_delay_duration": duration_value,
        "initial_event_seq": seq_value,
        "initial_scan_type": str(record.get("initial_scan_type", "unknown")).strip()
        or "unknown",
        "initial_warehouse": str(record.get("initial_warehouse", "unknown")).strip()
        or "unknown",
        "initial_delay_time": cleaned_time,
    }


def _shipment_frame_from_record(cleaned: dict[str, Any]) -> pd.DataFrame:
    """One-row delayed-shipment frame from a validated record."""
    return pd.DataFrame(
        [
            {
                "shipment_id": "inference_request",
                "route": cleaned["route"],
                "initial_delay_time": cleaned["initial_delay_time"],
                "initial_event_seq": cleaned["initial_event_seq"],
                "initial_delay_duration": cleaned["initial_delay_duration"],
                "initial_scan_type": cleaned["initial_scan_type"],
                "initial_warehouse": cleaned["initial_warehouse"],
                TARGET_COLUMN: 0,
            }
        ]
    )


def predict_single(
    record: dict[str, Any], artifact: dict[str, Any]
) -> dict[str, Any]:
    """Score one validated record; returns route/prediction/probability.

    Output wording: ``cascade_probability`` is the model's *predicted
    probability of cascade* (estimated, not certain).
    """
    cleaned = validate_inference_record(record)
    frame = _shipment_frame_from_record(cleaned)
    enriched = apply_route_history(
        _add_time_features(frame), artifact["history"]
    )
    matrix, _, _ = build_feature_matrix(
        enriched,
        artifact["history"],
        duration_median=float(artifact["fitted"]["duration_median"]),
        vocabularies={k: list(v) for k, v in artifact["fitted"]["vocabularies"].items()},
    )
    # build_feature_matrix orders columns from its own fitted vocabularies;
    # realign to the trained column order (missing → 0, extras dropped).
    matrix = matrix.reindex(columns=list(artifact["feature_names"]), fill_value=0)
    assert_no_leakage_columns(list(matrix.columns))
    probability = float(
        predict_proba_from_params(
            matrix,
            list(artifact["coefficients"]),
            float(artifact["intercept"]),
            dict(artifact["scaler"]),
            list(artifact["feature_names"]),
        )[0]
    )
    threshold = float(artifact["config"]["decision_threshold"])
    return {
        "route": cleaned["route"],
        "prediction": int(probability >= threshold),
        "cascade_probability": min(max(probability, 0.0), 1.0),
        "model_version": str(artifact["model_version"]),
    }


def predict_for_shipments(
    dataset: pd.DataFrame,
    artifact: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score every delayed shipment in an integrated dataset.

    Returns ``(predictions, info)`` with one row per delayed shipment:
    ``shipment_id``, ``route``, ``initial_delay_time``,
    ``cascade_probability`` (predicted probability of cascade),
    ``prediction`` (thresholded class), ``model_version``. Shipments
    without delays are out of scope and counted in ``info``.
    """
    shipments, table_info = build_delayed_shipment_table(dataset)
    if shipments.empty:
        empty = pd.DataFrame(
            columns=[
                "shipment_id", "route", "initial_delay_time",
                "cascade_probability", "prediction", "model_version",
            ]
        )
        return empty, {
            "delayed_shipments": 0,
            "scored_shipments": 0,
            "model_version": str(artifact["model_version"]),
        }
    enriched = apply_route_history(
        _add_time_features(shipments), artifact["history"]
    )
    matrix, _, _ = build_feature_matrix(
        enriched,
        artifact["history"],
        duration_median=float(artifact["fitted"]["duration_median"]),
        vocabularies={k: list(v) for k, v in artifact["fitted"]["vocabularies"].items()},
    )
    matrix = matrix.reindex(columns=list(artifact["feature_names"]), fill_value=0)
    probabilities = predict_proba_from_params(
        matrix,
        list(artifact["coefficients"]),
        float(artifact["intercept"]),
        dict(artifact["scaler"]),
        list(artifact["feature_names"]),
    )
    threshold = float(artifact["config"]["decision_threshold"])
    predictions = pd.DataFrame(
        {
            "shipment_id": shipments["shipment_id"].astype(str).to_numpy(),
            "route": shipments["route"].astype(str).to_numpy(),
            "initial_delay_time": pd.to_datetime(
                shipments["initial_delay_time"], errors="coerce", utc=True
            ),
            "cascade_probability": _clip01(probabilities),
            "prediction": (probabilities >= threshold).astype(int),
            "model_version": str(artifact["model_version"]),
        }
    )
    info = {
        "delayed_shipments": int(len(shipments)),
        "scored_shipments": int(len(predictions)),
        "shipments_checked": table_info["shipments_checked"],
        "model_version": str(artifact["model_version"]),
        "threshold": threshold,
    }
    return predictions, info


def _clip01(values: Any) -> Any:
    """Clip probabilities into [0, 1] (sigmoid already guarantees this)."""
    return np.clip(np.asarray(values, dtype=float), 0.0, 1.0)


def route_prediction_summary(predictions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate shipment probabilities to route grain (read-only).

    Columns: ``route``, ``predicted_shipments``,
    ``mean_cascade_probability`` (average predicted probability of cascade
    across scored delayed shipments on the route),
    ``share_predicted_cascade`` (fraction with ``prediction == 1``).
    These are model estimates, not observed outcomes — join historical
    empirical rates separately and label each column accordingly.
    """
    if predictions.empty:
        return pd.DataFrame(
            columns=[
                "route", "predicted_shipments", "mean_cascade_probability",
                "share_predicted_cascade",
            ]
        )
    rows = []
    for route, group in predictions.groupby("route", sort=True):
        rows.append(
            {
                "route": str(route),
                "predicted_shipments": int(len(group)),
                "mean_cascade_probability": float(
                    group["cascade_probability"].mean()
                ),
                "share_predicted_cascade": float(
                    (group["prediction"] == 1).mean()
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["mean_cascade_probability", "route"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def load_model(path: PathLike) -> dict[str, Any]:
    """Load a validated model artifact from disk."""
    return load_model_artifact(path)


def resolve_artifact_or_none(
    models_dir: PathLike,
    dataset: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Newest artifact overall (or for one dataset); None when absent."""
    from analysis.prediction_model import discover_model_artifacts

    entries = discover_model_artifacts(models_dir)
    if dataset is not None:
        entries = [e for e in entries if e.get("dataset") == dataset]
    if not entries:
        return None
    return load_model_artifact(entries[0]["path"])
