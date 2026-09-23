"""Prediction-time feature engineering for the route-cascade baseline.

Prediction task (one precise target):

* Population: one row per *delayed* shipment, i.e. shipments with at least
  one observed delayed event. Shipments without any delay cannot cascade
  by definition and are out of scope (counts are reported, never hidden).
* Prediction point: the moment the *initial* delay is observed.
* Target: ``cascade_flag`` in {0, 1} — 1 exactly when the shipment is a
  cascade candidate under the existing definition in
  :mod:`analysis.cascade_analysis` (initial delayed event followed by at
  least one later delayed event). No new cascade definition is invented;
  the rule parameters (``min_delay_duration``, ``max_downstream_gap``)
  are passed through and echoed in every output.

Leakage discipline (features knowable at the prediction point only):

* USED: route of the initial event, initial delay duration, position of
  the initial event in the journey so far (``initial_event_seq``),
  scan type / warehouse observed at the initial event, calendar features
  of the initial-delay timestamp, and route history computed on TRAINING
  data only (empirical cascade rate + delayed volume per route).
* NEVER USED: delay reasons / ``reported_at`` (delay reports are written
  after the journey ends), any ``transfer_*`` column (transfer records
  resolve around or after hub events — ambiguous timing, excluded),
  downstream/final durations, total event counts, ``cascade_depth``,
  ``stages``, or any other field computed from events after the initial
  delay. :func:`assert_no_leakage_columns` enforces this on outputs.

All functions are read-only and deterministic; the input frame is never
mutated. No machine learning happens here — this module only prepares
the leakage-free modelling table that :mod:`analysis.prediction_model`
consumes.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from analysis._schema import (
    DEFAULT_DELAYED_STATUS_VALUES,
    SCAN_TYPE_CANDIDATES,
    STATUS_CANDIDATES,
    find_column,
    find_delay_duration_column,
    find_route_column,
    find_shipment_column,
    find_warehouse_columns,
)
from analysis.cascade_analysis import (
    DEFAULT_DELIVERY_STATUS_VALUES,
    detect_cascade_candidates,
    reconstruct_shipment_journey,
)
from config.prediction_config import (
    resolve_prediction_config,
)

TARGET_COLUMN = "cascade_flag"

TARGET_DEFINITION = (
    "cascade_flag = 1 when the shipment journey contains an initial "
    "delayed event followed by at least one later delayed (downstream) "
    "event under analysis.cascade_analysis.detect_cascade_candidates "
    "(same definition, same rule parameters); else 0. A single delay is "
    "never a cascade."
)

UNKNOWN = "unknown"

#: Numeric features in fixed order (standardized by the model layer).
NUMERIC_FEATURES = [
    "initial_delay_duration",
    "initial_event_seq",
    "initial_hour",
    "initial_dow",
    "is_weekend",
    "route_hist_cascade_rate",
    "route_hist_delayed",
]

#: Train-only historical features explicitly allowed (empirical rates from
#: the training period — prediction-time information by construction).
ALLOWED_HISTORICAL_FEATURES = frozenset(
    {"route_hist_cascade_rate", "route_hist_delayed"}
)

#: Substrings that must never appear in a feature column (leakage guard).
FORBIDDEN_FEATURE_PATTERNS = (
    "downstream",
    "final_",
    "reported_at",
    "transfer_",
    "delay_reason",
    "delay_id",
    "stages",
    "cascade_depth",
    "cascade_flag",
    "cascade_probability",
    "cascade_shipments",
    "cascade_stage",
)


def _label(value: Any) -> str:
    """Bucket label with the cascade module's unknown convention."""
    if value is None:
        return UNKNOWN
    try:
        if pd.isna(value):
            return UNKNOWN
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text != "" else UNKNOWN


def assert_no_leakage_columns(columns: list[str]) -> None:
    """Raise ValueError if a feature name suggests post-outcome information."""
    lowered = [
        str(c).lower()
        for c in columns
        if str(c).lower() not in ALLOWED_HISTORICAL_FEATURES
    ]
    bad = sorted(
        {c for c in lowered for pat in FORBIDDEN_FEATURE_PATTERNS if pat in c}
    )
    if bad:
        raise ValueError(
            "Leakage guard: feature columns suggest post-outcome information: "
            f"{bad}."
        )


def build_delayed_shipment_table(
    dataset: pd.DataFrame,
    shipment_column: Optional[str] = None,
    timestamp_column: Optional[str] = None,
    route_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
    delayed_status_values: tuple[str, ...] = DEFAULT_DELAYED_STATUS_VALUES,
    delivery_status_values: tuple[str, ...] = DEFAULT_DELIVERY_STATUS_VALUES,
    min_delay_duration: Optional[float] = None,
    max_downstream_gap: Any = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build one row per delayed shipment with prediction-time context.

    Columns: ``shipment_id``, ``route`` (route of the first delayed event),
    ``initial_delay_time``, ``initial_event_seq`` (events observed up to and
    including the initial delay — known at the prediction point),
    ``initial_delay_duration``, ``initial_scan_type``, ``initial_warehouse``,
    and ``cascade_flag`` (target, from the shared cascade definition).

    Shipments without any delayed event are out of scope; their count is in
    ``info``. Raises ValueError when no route column exists.
    """
    if len(dataset) == 0:
        columns = [
            "shipment_id", "route", "initial_delay_time", "initial_event_seq",
            "initial_delay_duration", "initial_scan_type", "initial_warehouse",
            TARGET_COLUMN,
        ]
        info = {
            "shipments_checked": 0,
            "delayed_shipments": 0,
            "cascade_shipments": 0,
            "target": TARGET_DEFINITION,
            "note": "Empty input; no shipments checked.",
        }
        return pd.DataFrame(columns=columns), info

    resolved_route = route_column or find_route_column(dataset)
    if resolved_route is None or resolved_route not in dataset.columns:
        raise ValueError(
            "No route column found. Pass route_column explicitly or ensure "
            "'route_id' is present in the dataset."
        )
    resolved_duration = duration_column or find_delay_duration_column(dataset)
    if resolved_duration is not None and resolved_duration not in dataset.columns:
        resolved_duration = None
    resolved_scan = find_column(dataset, SCAN_TYPE_CANDIDATES)
    warehouse_columns = find_warehouse_columns(dataset)
    resolved_status = status_column or find_column(dataset, STATUS_CANDIDATES)
    if resolved_status is not None and resolved_status not in dataset.columns:
        resolved_status = None

    candidates, cascade_info = detect_cascade_candidates(
        dataset,
        shipment_column=shipment_column,
        timestamp_column=timestamp_column,
        duration_column=resolved_duration,
        route_column=resolved_route,
        status_column=resolved_status,
        flag_column=flag_column,
        delayed_status_values=delayed_status_values,
        delivery_status_values=delivery_status_values,
        min_delay_duration=min_delay_duration,
        max_downstream_gap=max_downstream_gap,
    )
    events, journey_report = reconstruct_shipment_journey(
        dataset,
        shipment_column=shipment_column,
        timestamp_column=timestamp_column,
        duration_column=resolved_duration,
        flag_column=flag_column,
        status_column=resolved_status,
        delayed_status_values=delayed_status_values,
    )

    cascade_set = set(candidates["shipment_id"].astype(str).tolist())
    delayed = events[events["_is_delayed"]].sort_values(
        ["_shipment", "_event_time"], kind="mergesort"
    )
    first = delayed.drop_duplicates(subset=["_shipment"], keep="first")

    route_source = f"src_{resolved_route}"
    scan_source = f"src_{resolved_scan}" if resolved_scan else None
    warehouse_source = f"src_{warehouse_columns[0]}" if warehouse_columns else None
    duration_source = f"src_{resolved_duration}" if resolved_duration else None

    initial_times = pd.to_datetime(first["_event_time"], errors="coerce", utc=True)
    usable = initial_times.notna()
    skipped_no_time = int((~usable).sum())
    first = first.loc[usable].reset_index(drop=True)
    initial_times = initial_times.loc[usable].reset_index(drop=True)

    durations = pd.to_numeric(
        first[duration_source], errors="coerce"
    ) if duration_source and duration_source in first.columns else None

    rows: list[dict[str, Any]] = []
    for pos, (_, row) in enumerate(first.iterrows()):
        shipment = str(row["_shipment"])
        duration: Optional[float] = None
        if durations is not None:
            value = float(durations.iloc[pos])
            duration = None if pd.isna(value) else value
        scan_value = row[scan_source] if scan_source and scan_source in row.index else None
        warehouse_value = (
            row[warehouse_source]
            if warehouse_source and warehouse_source in row.index
            else None
        )
        rows.append(
            {
                "shipment_id": shipment,
                "route": _label(row[route_source]) if route_source in row.index else UNKNOWN,
                "initial_delay_time": initial_times.iloc[pos],
                "initial_event_seq": int(row["_event_seq"]),
                "initial_delay_duration": duration,
                "initial_scan_type": _label(scan_value),
                "initial_warehouse": _label(warehouse_value),
                TARGET_COLUMN: 1 if shipment in cascade_set else 0,
            }
        )
    shipments = pd.DataFrame(
        rows,
        columns=[
            "shipment_id", "route", "initial_delay_time", "initial_event_seq",
            "initial_delay_duration", "initial_scan_type", "initial_warehouse",
            TARGET_COLUMN,
        ],
    )
    info = {
        "shipments_checked": int(cascade_info["shipments_checked"]),
        "delayed_shipments": int(len(shipments)),
        "cascade_shipments": int(len(candidates)),
        "skipped_initial_without_time": skipped_no_time,
        "target": TARGET_DEFINITION,
        "cascade_rule": cascade_info["rule"],
        "route_column": resolved_route,
        "duration_column": resolved_duration,
        "scan_column": resolved_scan,
        "warehouse_column": warehouse_columns[0] if warehouse_columns else None,
    }
    _ = journey_report
    return shipments, info


def temporal_split(
    shipments: pd.DataFrame,
    train_fraction: float = 0.7,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Chronological split of delayed shipments by initial-delay time.

    Earlier observations train; later observations validate. No shuffling:
    logistics data is temporal and a random split would let future delays
    inform the past. Deterministic (stable sort by time, then shipment).
    """
    if shipments.empty:
        info = {
            "train_rows": 0,
            "test_rows": 0,
            "train_positives": 0,
            "test_positives": 0,
            "train_period": (None, None),
            "test_period": (None, None),
            "note": "Empty input; nothing to split.",
        }
        return shipments.copy(deep=True), shipments.copy(deep=True), info
    ordered = shipments.sort_values(
        ["initial_delay_time", "shipment_id"], kind="mergesort"
    ).reset_index(drop=True)
    cut = int(len(ordered) * float(train_fraction))
    cut = max(1, min(cut, len(ordered) - 1)) if len(ordered) > 1 else len(ordered)
    train = ordered.iloc[:cut].reset_index(drop=True)
    test = ordered.iloc[cut:].reset_index(drop=True)

    def iso(series: pd.Series) -> tuple[Optional[str], Optional[str]]:
        times = pd.to_datetime(series, errors="coerce", utc=True)
        if times.empty or times.isna().all():
            return None, None
        return str(times.min().isoformat()), str(times.max().isoformat())

    info = {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_positives": int(train[TARGET_COLUMN].sum()),
        "test_positives": int(test[TARGET_COLUMN].sum()),
        "train_period": iso(train["initial_delay_time"]),
        "test_period": iso(test["initial_delay_time"]),
        "train_fraction": float(train_fraction),
        "strategy": "chronological by initial_delay_time (no shuffling)",
    }
    return train, test, info


def fit_route_history(train: pd.DataFrame) -> dict[str, Any]:
    """Empirical per-route cascade statistics from TRAINING rows only.

    Returns rates/counts plus the global fallback for routes unseen in
    training. Computing these on the full dataset before splitting would
    leak test outcomes into training features.
    """
    if train.empty:
        return {
            "route_rates": {},
            "route_counts": {},
            "global_rate": 0.0,
            "note": "Empty training frame; global fallback only.",
        }
    grouped = train.groupby("route", sort=True)
    rates = {}
    counts = {}
    for route, group in grouped:
        delayed_n = int(len(group))
        cascade_n = int(group[TARGET_COLUMN].sum())
        rates[str(route)] = cascade_n / delayed_n if delayed_n else 0.0
        counts[str(route)] = delayed_n
    total = int(len(train))
    positives = int(train[TARGET_COLUMN].sum())
    return {
        "route_rates": rates,
        "route_counts": counts,
        "global_rate": positives / total if total else 0.0,
        "note": "Fitted on training rows only; unseen routes use global_rate.",
    }


def apply_route_history(
    frame: pd.DataFrame, history: dict[str, Any]
) -> pd.DataFrame:
    """Attach train-only route statistics to a shipment frame (read-only)."""
    result = frame.copy(deep=True)
    rates = history.get("route_rates", {})
    counts = history.get("route_counts", {})
    fallback = float(history.get("global_rate", 0.0))
    result["route_hist_cascade_rate"] = result["route"].map(
        lambda r: float(rates.get(str(r), fallback))
    )
    result["route_hist_delayed"] = result["route"].map(
        lambda r: int(counts.get(str(r), 0))
    )
    return result


def _add_time_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Calendar parts of the initial-delay timestamp (known at prediction)."""
    result = frame.copy(deep=True)
    times = pd.to_datetime(result["initial_delay_time"], errors="coerce", utc=True)
    result["initial_hour"] = times.dt.hour.fillna(12).astype(int)
    result["initial_dow"] = times.dt.dayofweek.fillna(0).astype(int)
    result["is_weekend"] = (result["initial_dow"] >= 5).astype(int)
    return result


def build_feature_matrix(
    shipments: pd.DataFrame,
    history: dict[str, Any],
    duration_median: Optional[float] = None,
    vocabularies: Optional[dict[str, list[str]]] = None,
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    """Assemble the leakage-free modelling matrix (deterministic).

    One-hot vocabularies come from the caller (training vocabulary when
    fitting; the same vocabulary when transforming test/inference rows, so
    unseen categories map to an all-zero block). Missing initial durations
    are filled with the training median.
    """
    enriched = apply_route_history(_add_time_features(shipments), history)
    if duration_median is None:
        observed = pd.to_numeric(
            enriched["initial_delay_duration"], errors="coerce"
        ).dropna()
        duration_median = float(observed.median()) if not observed.empty else 0.0
    enriched["initial_delay_duration"] = pd.to_numeric(
        enriched["initial_delay_duration"], errors="coerce"
    ).fillna(float(duration_median))

    if vocabularies is None:
        vocabularies = {
            "route": sorted(enriched["route"].astype(str).unique().tolist()),
            "initial_scan_type": sorted(
                enriched["initial_scan_type"].astype(str).unique().tolist()
            ),
            "initial_warehouse": sorted(
                enriched["initial_warehouse"].astype(str).unique().tolist()
            ),
        }
    one_hot = pd.DataFrame(index=enriched.index)
    for column, prefix in (
        ("route", "route"),
        ("initial_scan_type", "scan"),
        ("initial_warehouse", "wh"),
    ):
        for level in vocabularies.get(column, []):
            one_hot[f"{prefix}={level}"] = (
                enriched[column].astype(str) == str(level)
            ).astype(int)
    numeric = enriched[[c for c in NUMERIC_FEATURES if c in enriched.columns]].copy()
    missing_numeric = [c for c in NUMERIC_FEATURES if c not in enriched.columns]
    for column in missing_numeric:
        numeric[column] = 0.0
    numeric = numeric[NUMERIC_FEATURES]
    matrix = pd.concat([numeric, one_hot], axis=1)
    feature_names = list(matrix.columns)
    assert_no_leakage_columns(feature_names)
    fitted = {
        "duration_median": float(duration_median),
        "vocabularies": {k: list(v) for k, v in vocabularies.items()},
    }
    return matrix, feature_names, fitted


def assess_prediction_readiness(
    dataset: pd.DataFrame,
    config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Decide whether the dataset supports a validated prediction baseline.

    Returns a JSON-friendly readiness report with ``available`` plus the
    explicit reason when unavailable. Thresholds come from
    :mod:`config.prediction_config` and are echoed back.
    """
    cfg = resolve_prediction_config(config)
    base: dict[str, Any] = {
        "available": False,
        "reason": "",
        "target": TARGET_DEFINITION,
        "config": {
            k: cfg[k]
            for k in (
                "min_delayed_shipments", "min_cascade_positives",
                "train_fraction", "min_train_positives",
                "min_test_positives", "min_observed_days",
            )
        },
    }
    if len(dataset) == 0:
        return {**base, "reason": "Empty input dataset."}
    try:
        shipments, table_info = build_delayed_shipment_table(dataset)
    except ValueError as exc:
        return {**base, "reason": f"Required columns unavailable: {exc}."}
    delayed_n = int(len(shipments))
    positives = int(shipments[TARGET_COLUMN].sum()) if delayed_n else 0
    negatives = delayed_n - positives
    times = pd.to_datetime(
        shipments["initial_delay_time"], errors="coerce", utc=True
    ) if delayed_n else pd.Series(dtype="datetime64[ns, UTC]")
    observed_days = int(times.dt.date.nunique()) if delayed_n else 0
    train, test, split = temporal_split(shipments, cfg["train_fraction"])
    report = {
        **base,
        "shipments_checked": table_info["shipments_checked"],
        "delayed_shipments": delayed_n,
        "cascade_shipments": positives,
        "non_cascade_delayed": negatives,
        "positive_share": (positives / delayed_n) if delayed_n else 0.0,
        "baseline_rate": (positives / delayed_n) if delayed_n else 0.0,
        "observed_days": observed_days,
        "train_rows": split["train_rows"],
        "test_rows": split["test_rows"],
        "train_positives": split["train_positives"],
        "test_positives": split["test_positives"],
        "train_period": split["train_period"],
        "test_period": split["test_period"],
        "routes": int(shipments["route"].nunique()) if delayed_n else 0,
        "class_imbalance": (
            min(positives, negatives) / delayed_n if delayed_n else 0.0
        ),
    }
    checks = [
        (
            delayed_n >= cfg["min_delayed_shipments"],
            f"Only {delayed_n} delayed shipments; minimum is "
            f"{cfg['min_delayed_shipments']}.",
        ),
        (
            positives >= cfg["min_cascade_positives"],
            f"Only {positives} cascade examples; minimum is "
            f"{cfg['min_cascade_positives']}.",
        ),
        (
            split["train_positives"] >= cfg["min_train_positives"],
            f"Only {split['train_positives']} training positives; minimum is "
            f"{cfg['min_train_positives']}.",
        ),
        (
            split["test_positives"] >= cfg["min_test_positives"],
            f"Only {split['test_positives']} test positives; minimum is "
            f"{cfg['min_test_positives']}.",
        ),
        (
            observed_days >= cfg["min_observed_days"],
            f"Initial delays span {observed_days} day(s); minimum is "
            f"{cfg['min_observed_days']} for a chronological split.",
        ),
    ]
    failed = [reason for ok, reason in checks if not ok]
    if failed:
        report["reason"] = (
            "Insufficient validated training data: " + " ".join(failed)
        )
        return report
    _ = (train, test)
    report["available"] = True
    report["reason"] = "Dataset meets the minimum validation requirements."
    return report


def build_prediction_dataset(
    dataset: pd.DataFrame,
    config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble train/test matrices after a passing readiness assessment.

    Raises:
        ValueError: When the dataset does not meet the minimum validation
            requirements (use :func:`assess_prediction_readiness` first for
            the explicit reason instead of an exception).
    """
    cfg = resolve_prediction_config(config)
    readiness = assess_prediction_readiness(dataset, cfg)
    if not readiness["available"]:
        raise ValueError(readiness["reason"])
    shipments, table_info = build_delayed_shipment_table(dataset)
    train, test, split = temporal_split(shipments, cfg["train_fraction"])
    history = fit_route_history(train)
    X_train, feature_names, fitted = build_feature_matrix(train, history)
    X_test, _, _ = build_feature_matrix(
        test,
        history,
        duration_median=fitted["duration_median"],
        vocabularies=fitted["vocabularies"],
    )
    y_train = train[TARGET_COLUMN].astype(int)
    y_test = test[TARGET_COLUMN].astype(int)
    return {
        "train_shipments": train,
        "test_shipments": test,
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "feature_names": feature_names,
        "fitted": fitted,
        "history": history,
        "split": split,
        "readiness": readiness,
        "table_info": table_info,
        "config": cfg,
    }
