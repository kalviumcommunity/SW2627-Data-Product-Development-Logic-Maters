"""Operational alert and risk detection (deterministic, read-only).

Alert categories reuse existing analytics - no duplicated business logic,
no new cascade definition, no machine learning:

* delay-rate alerts from ``route_metrics`` / ``warehouse_metrics``;
* duration alerts from the ``delay_duration`` column (worst per shipment);
* cascade alerts from ``detect_cascade_candidates`` output.

Every threshold comes from ``config/alert_config.py`` (configurable
demonstration parameters, NOT learned from production data) and is
reported on each alert. Severity rules (documented):

* WARNING: metric at or above the warning threshold;
* CRITICAL: metric at or above the critical threshold/depth;
* INFO: metric at or above ``near_miss_ratio`` * threshold (watch list).

A rate alert additionally requires ``min_shipments_for_rate_alert``
shipments behind the rate. Setting any threshold to None disables that
alert type. Missing columns or empty input yield an empty alert table
with full columns - never an exception from these generators (invalid
caller overrides still raise via config validation).

Output columns: ``alert_id, alert_type, severity, entity_type,
entity_id, metric, metric_value, threshold, message, detected_at,
evidence`` where ``evidence`` is a JSON string of supporting facts.
"""

from __future__ import annotations

import datetime as _datetime
import json
from typing import Any, Optional

import pandas as pd

from analysis._schema import (
    find_delay_duration_column,
    find_shipment_column,
)
from analysis.cascade_analysis import detect_cascade_candidates
from analysis.route_analysis import route_metrics
from analysis.warehouse_analysis import warehouse_metrics
from config.alert_config import resolve_config, severity_rank

ALERT_COLUMNS = [
    "alert_id",
    "alert_type",
    "severity",
    "entity_type",
    "entity_id",
    "metric",
    "metric_value",
    "threshold",
    "message",
    "detected_at",
    "evidence",
]

ALERT_DELAY_RATE = "delay_rate"
ALERT_DURATION = "excessive_delay"
ALERT_CASCADE = "cascade_detected"

_SEVERITY_BY_RANK = ("INFO", "WARNING", "CRITICAL")


def empty_alerts() -> pd.DataFrame:
    """Return an empty alert table with full columns."""
    return pd.DataFrame(columns=ALERT_COLUMNS)


def _assign_severity(value: float, warn_at: float, crit_at: float) -> str:
    """WARNING at/above warn_at, CRITICAL at/above crit_at (documented)."""
    if value >= crit_at:
        return "CRITICAL"
    return "WARNING"


def _near_miss(value: float, threshold: float, ratio: Optional[float]) -> bool:
    """True when value sits in [ratio*threshold, threshold)."""
    return (
        ratio is not None
        and ratio * threshold <= value < threshold
    )


def _finalize(rows: list[dict[str, Any]], detected_at: str) -> pd.DataFrame:
    """Sort deterministically, assign IDs, and order columns."""
    table = pd.DataFrame(rows, columns=[c for c in ALERT_COLUMNS if c != "alert_id"])
    if table.empty:
        return empty_alerts()
    table["_rank"] = table["severity"].map(severity_rank)
    table = table.sort_values(
        ["_rank", "alert_type", "entity_type", "entity_id"],
        ascending=[False, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    table.insert(0, "alert_id", [f"ALT-{i + 1:04d}" for i in range(len(table))])
    table["detected_at"] = detected_at
    return table.drop(columns=["_rank"])


def _now_iso() -> str:
    return _datetime.datetime.now(tz=_datetime.timezone.utc).isoformat(timespec="seconds")


def _jsonable(value: Any) -> Any:
    """Convert NaN/None to None and numpy scalars to Python floats."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _rate_alerts_from_metrics(
    metrics: pd.DataFrame,
    entity_label: str,
    entity_type: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build rate alert rows from a route/warehouse metrics table."""
    threshold = config["delay_rate_threshold"]
    rows: list[dict[str, Any]] = []
    if threshold is None or metrics.empty or "delay_rate" not in metrics.columns:
        return rows
    critical = config["critical_delay_rate"]
    min_ship = config["min_shipments_for_rate_alert"]
    ratio = config["near_miss_ratio"]
    id_column = "route" if entity_type == "route" else "warehouse"
    for _, row in metrics.iterrows():
        rate = row.get("delay_rate")
        shipments = row.get("shipments")
        if rate is None or (isinstance(rate, float) and pd.isna(rate)):
            continue
        if shipments is None or shipments < min_ship:
            continue
        rate = float(rate)
        entity_id = str(row[id_column])
        evidence = json.dumps(
            {
                "shipments": int(shipments),
                "delayed_shipments": _jsonable(row.get("delayed_shipments")),
                "avg_delay": _jsonable(row.get("avg_delay")),
                "min_shipments_for_rate_alert": min_ship,
            }
        )
        if rate >= threshold:
            severity = _assign_severity(rate, threshold, critical)
            verb = "exceeded" if severity == "WARNING" else "greatly exceeded"
            rows.append(
                {
                    "alert_type": ALERT_DELAY_RATE,
                    "severity": severity,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "metric": "delay_rate",
                    "metric_value": rate,
                    "threshold": float(threshold),
                    "message": (
                        f"{entity_label} {entity_id} has a {rate:.1f}% delay rate, "
                        f"which {verb} the configured threshold of {float(threshold):.1f}%."
                    ),
                    "evidence": evidence,
                }
            )
        elif _near_miss(rate, float(threshold), ratio):
            rows.append(
                {
                    "alert_type": ALERT_DELAY_RATE,
                    "severity": "INFO",
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "metric": "delay_rate",
                    "metric_value": rate,
                    "threshold": float(threshold),
                    "message": (
                        f"{entity_label} {entity_id} has a {rate:.1f}% delay rate, "
                        f"approaching the configured threshold of {float(threshold):.1f}%."
                    ),
                    "evidence": evidence,
                }
            )
    return rows


def generate_delay_rate_alerts(
    dataset: pd.DataFrame,
    entity: str = "route",
    config: Optional[dict[str, Any]] = None,
    detected_at: Optional[str] = None,
) -> pd.DataFrame:
    """Alert on entities whose delay rate breaches the configured threshold.

    Reuses ``route_metrics`` / ``warehouse_metrics``. Returns an empty
    alert table when the entity column is absent (no exception).
    """
    if entity not in ("route", "warehouse"):
        raise ValueError("entity must be 'route' or 'warehouse'.")
    cfg = resolve_config(config)
    try:
        metrics = route_metrics(dataset) if entity == "route" else warehouse_metrics(dataset)
    except ValueError:
        return empty_alerts()
    label = "Route" if entity == "route" else "Warehouse"
    return _finalize(
        _rate_alerts_from_metrics(metrics, label, entity, cfg), detected_at or _now_iso()
    )


def generate_route_alerts(
    dataset: pd.DataFrame,
    config: Optional[dict[str, Any]] = None,
    detected_at: Optional[str] = None,
) -> pd.DataFrame:
    """Route delay-rate alerts (factual wording; see module docstring)."""
    return generate_delay_rate_alerts(dataset, entity="route", config=config, detected_at=detected_at)


def generate_warehouse_alerts(
    dataset: pd.DataFrame,
    config: Optional[dict[str, Any]] = None,
    detected_at: Optional[str] = None,
) -> pd.DataFrame:
    """Warehouse delay-rate alerts (patterns for investigation)."""
    return generate_delay_rate_alerts(
        dataset, entity="warehouse", config=config, detected_at=detected_at
    )


def generate_delay_duration_alerts(
    dataset: pd.DataFrame,
    config: Optional[dict[str, Any]] = None,
    *,
    duration_column: Optional[str] = None,
    shipment_column: Optional[str] = None,
    detected_at: Optional[str] = None,
) -> pd.DataFrame:
    """Alert once per shipment whose worst delay meets the threshold.

    One alert per shipment (never per duplicated row): the worst observed
    duration is reported with the supporting record count as evidence.
    Empty table when no duration column exists.
    """
    cfg = resolve_config(config)
    threshold = cfg["delay_duration_threshold"]
    if threshold is None:
        return empty_alerts()
    resolved_duration = duration_column or find_delay_duration_column(dataset)
    if resolved_duration is None or resolved_duration not in dataset.columns:
        return empty_alerts()
    resolved_shipment = shipment_column or find_shipment_column(dataset)
    if resolved_shipment is not None and resolved_shipment not in dataset.columns:
        resolved_shipment = None
    durations = pd.to_numeric(dataset[resolved_duration], errors="coerce")
    frame = pd.DataFrame(
        {
            "shipment": (
                dataset[resolved_shipment].astype("string").fillna("unknown")
                if resolved_shipment
                else pd.Series([f"record-{i}" for i in dataset.index], index=dataset.index)
            ),
            "duration": durations,
        }
    ).dropna(subset=["duration"])
    frame = frame[frame["duration"] > 0]
    if frame.empty:
        return empty_alerts()
    grouped = frame.groupby("shipment", sort=True)["duration"]
    worst = grouped.max()
    counts = grouped.size()
    critical = cfg["critical_delay_duration"]
    ratio = cfg["near_miss_ratio"]
    rows: list[dict[str, Any]] = []
    for shipment_id, value in worst.items():
        value = float(value)
        evidence = json.dumps(
            {"delayed_records": int(counts.loc[shipment_id]),
             "worst_delay_duration": value}
        )
        if value >= threshold:
            severity = _assign_severity(value, float(threshold), float(critical))
            rows.append(
                {
                    "alert_type": ALERT_DURATION,
                    "severity": severity,
                    "entity_type": "shipment",
                    "entity_id": str(shipment_id),
                    "metric": "max_delay_duration",
                    "metric_value": value,
                    "threshold": float(threshold),
                    "message": (
                        f"Shipment {shipment_id} has an observed delay of {value:.1f}, "
                        f"meeting the configured duration threshold of {float(threshold):.1f}."
                    ),
                    "evidence": evidence,
                }
            )
        elif _near_miss(value, float(threshold), ratio):
            rows.append(
                {
                    "alert_type": ALERT_DURATION,
                    "severity": "INFO",
                    "entity_type": "shipment",
                    "entity_id": str(shipment_id),
                    "metric": "max_delay_duration",
                    "metric_value": value,
                    "threshold": float(threshold),
                    "message": (
                        f"Shipment {shipment_id} has an observed delay of {value:.1f}, "
                        f"approaching the configured duration threshold of {float(threshold):.1f}."
                    ),
                    "evidence": evidence,
                }
            )
    return _finalize(rows, detected_at or _now_iso())


def generate_cascade_alerts(
    dataset: pd.DataFrame,
    config: Optional[dict[str, Any]] = None,
    detected_at: Optional[str] = None,
    **cascade_kwargs: Any,
) -> pd.DataFrame:
    """Alert once per cascade candidate from the existing cascade analysis.

    No new cascade definition: ``detect_cascade_candidates`` output is
    reused directly (extra ``cascade_kwargs`` pass through to it).
    Severity WARNING for depth 1, CRITICAL at/above
    ``critical_cascade_depth``. Empty table when detection prerequisites
    are absent (propagates no exception).
    """
    cfg = resolve_config(config)
    try:
        candidates, _ = detect_cascade_candidates(
            dataset,
            min_delay_duration=cascade_kwargs.get(
                "min_delay_duration", cfg["cascade_min_delay_duration"]
            ),
            max_downstream_gap=cascade_kwargs.get(
                "max_downstream_gap", cfg["cascade_max_downstream_gap"]
            ),
        )
    except ValueError:
        return empty_alerts()
    if candidates.empty:
        return empty_alerts()
    critical_depth = cfg["critical_cascade_depth"]
    rows: list[dict[str, Any]] = []
    for _, row in candidates.iterrows():
        depth = int(row["cascade_depth"])
        severity = "CRITICAL" if depth >= critical_depth else "WARNING"
        rows.append(
            {
                "alert_type": ALERT_CASCADE,
                "severity": severity,
                "entity_type": "shipment",
                "entity_id": str(row["shipment_id"]),
                "metric": "cascade_depth",
                "metric_value": float(depth),
                "threshold": 1.0,
                "message": (
                    f"Shipment {row['shipment_id']} shows a cascade candidate "
                    f"with depth {depth} "
                    f"(initial delay followed by downstream delay observed)."
                ),
                "evidence": json.dumps(
                    {
                        "stages": [str(s) for s in (row["stages"] or [])],
                        "initial_delay_duration": _jsonable(row.get("initial_delay_duration")),
                        "downstream_delay_duration": _jsonable(
                            row.get("downstream_delay_duration")
                        ),
                        "initial_route": _jsonable(row.get("initial_route")),
                        "initial_warehouse": _jsonable(row.get("initial_warehouse")),
                    }
                ),
            }
        )
    return _finalize(rows, detected_at or _now_iso())


def generate_alerts(
    dataset: pd.DataFrame,
    config: Optional[dict[str, Any]] = None,
    detected_at: Optional[str] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run every alert generator and combine results deterministically.

    Returns ``(alerts, report)`` where report holds the resolved config,
    per-type counts, and explicit unavailability reasons. ``detected_at``
    (ISO string) pins the timestamp for reproducible output.
    """
    cfg = resolve_config(config)
    stamped = detected_at or _now_iso()
    parts = {
        ALERT_DELAY_RATE + ":route": generate_route_alerts(dataset, cfg, stamped),
        ALERT_DELAY_RATE + ":warehouse": generate_warehouse_alerts(dataset, cfg, stamped),
        ALERT_DURATION: generate_delay_duration_alerts(
            dataset, cfg, detected_at=stamped
        ),
        ALERT_CASCADE: generate_cascade_alerts(dataset, cfg, stamped),
    }
    non_empty = [frame for frame in parts.values() if not frame.empty]
    if not non_empty:
        alerts = empty_alerts()
    else:
        combined = pd.concat(non_empty, ignore_index=True)
        alerts = combined
        alerts["_rank"] = alerts["severity"].map(severity_rank)
        alerts = alerts.sort_values(
            ["_rank", "alert_type", "entity_type", "entity_id"],
            ascending=[False, True, True, True],
            kind="mergesort",
        ).reset_index(drop=True)
        alerts["alert_id"] = [f"ALT-{i + 1:04d}" for i in range(len(alerts))]
        alerts["detected_at"] = stamped
        alerts = alerts.drop(columns=["_rank"])[ALERT_COLUMNS]
    report = {
        "config": cfg,
        "total_alerts": int(len(alerts)),
        "by_type": {name: int(len(frame)) for name, frame in parts.items()},
        "unavailable": sorted(
            name for name, frame in parts.items() if frame.empty
        ),
        "note": (
            "Thresholds are configurable demonstration parameters, not "
            "production-learned values; data/processed/ is currently empty."
        ),
    }
    return alerts, report


def summarize_alerts(alerts: pd.DataFrame) -> dict[str, Any]:
    """Summarize an alert table: counts, entities, top exceedances.

    Reports observed metrics and threshold breaches only - no subjective
    risk score. Empty input yields zero counts (not n/a: zero alerts were
    observed on existing data).
    """
    if alerts.empty:
        return {
            "total_alerts": 0,
            "by_severity": {"CRITICAL": 0, "WARNING": 0, "INFO": 0},
            "by_type": {},
            "affected_routes": [],
            "affected_warehouses": [],
            "affected_shipments": [],
            "cascade_alerts": 0,
            "largest_exceedances": [],
        }
    by_severity = {
        level: int((alerts["severity"] == level).sum()) for level in _SEVERITY_BY_RANK
    }
    by_type = {str(k): int(v) for k, v in alerts["alert_type"].value_counts().items()}
    routes = sorted(alerts.loc[alerts["entity_type"] == "route", "entity_id"].astype(str).unique())
    warehouses = sorted(
        alerts.loc[alerts["entity_type"] == "warehouse", "entity_id"].astype(str).unique()
    )
    shipments = sorted(
        alerts.loc[alerts["entity_type"] == "shipment", "entity_id"].astype(str).unique()
    )
    numeric = alerts.copy()
    numeric["metric_value"] = pd.to_numeric(numeric["metric_value"], errors="coerce")
    numeric["threshold"] = pd.to_numeric(numeric["threshold"], errors="coerce")
    numeric["exceedance"] = numeric["metric_value"] - numeric["threshold"]
    top = numeric.sort_values("exceedance", ascending=False, kind="mergesort").head(5)
    return {
        "total_alerts": int(len(alerts)),
        "by_severity": by_severity,
        "by_type": by_type,
        "affected_routes": routes,
        "affected_warehouses": warehouses,
        "affected_shipments": shipments,
        "cascade_alerts": int((alerts["alert_type"] == ALERT_CASCADE).sum()),
        "largest_exceedances": [
            {
                "alert_id": row["alert_id"],
                "alert_type": row["alert_type"],
                "entity_id": str(row["entity_id"]),
                "metric_value": float(row["metric_value"]),
                "threshold": float(row["threshold"]),
                "exceedance": float(row["exceedance"]),
            }
            for _, row in top.iterrows()
        ],
    }
