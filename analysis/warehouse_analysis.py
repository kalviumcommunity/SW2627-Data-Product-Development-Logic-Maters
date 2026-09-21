"""Warehouse-level operational analysis (read-only, associations only).

Metrics describe what is *observed alongside* warehouses (delay rates,
transfer activity, waiting durations) for later investigation. A high
delay rate is reported as an association, never as proof that a
warehouse caused the delays.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from analysis._schema import (
    find_delay_duration_column,
    find_shipment_column,
    find_timestamp_columns,
    find_warehouse_columns,
    resolve_delay_flag,
)


def _resolve_warehouse_column(
    dataset: pd.DataFrame, warehouse_column: Optional[str]
) -> str:
    if warehouse_column is not None:
        if warehouse_column not in dataset.columns:
            raise ValueError(
                f"Warehouse column '{warehouse_column}' not found in dataset."
            )
        return warehouse_column
    columns = find_warehouse_columns(dataset)
    if not columns:
        raise ValueError(
            "No warehouse column found. Pass warehouse_column explicitly or "
            "ensure 'warehouse_id' (or a transfer endpoint) is present."
        )
    return columns[0]


def warehouse_metrics(
    dataset: pd.DataFrame,
    warehouse_column: Optional[str] = None,
    shipment_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
) -> pd.DataFrame:
    """Return one row per warehouse with factual delay metrics.

    Columns mirror :func:`analysis.route_analysis.route_metrics` with
    ``warehouse`` as the entity. Sorted by ``delay_rate`` descending
    (nulls last), then warehouse ascending.
    """
    warehouse_col = _resolve_warehouse_column(dataset, warehouse_column)
    ship_col = shipment_column or find_shipment_column(dataset)
    if ship_col is not None and ship_col not in dataset.columns:
        ship_col = None
    dur_col = duration_column or find_delay_duration_column(dataset)
    if dur_col is not None and dur_col not in dataset.columns:
        dur_col = None

    flag, _ = resolve_delay_flag(
        dataset,
        duration_column=dur_col,
        flag_column=flag_column,
        status_column=status_column,
    )
    working = dataset[[warehouse_col]].copy()
    working["_is_delayed"] = flag if flag is not None else False
    working["_has_signal"] = flag is not None
    if dur_col is not None:
        working["_duration"] = pd.to_numeric(dataset[dur_col], errors="coerce")
    if ship_col is not None:
        working["_shipment"] = dataset[ship_col].astype("string")

    rows: list[dict[str, Any]] = []
    for warehouse, group in working.groupby(warehouse_col, sort=True):
        shipments = (
            int(group["_shipment"].nunique(dropna=True))
            if ship_col is not None
            else int(len(group))
        )
        delayed_shipments: Optional[int] = None
        delay_rate: Optional[float] = None
        if bool(group["_has_signal"].iloc[0]):
            if ship_col is not None:
                delayed_shipments = int(
                    group.loc[group["_is_delayed"], "_shipment"].nunique(dropna=True)
                )
            else:
                delayed_shipments = int(group["_is_delayed"].sum())
            delay_rate = (
                delayed_shipments / shipments * 100.0 if shipments else None
            )
        avg_delay: Optional[float] = None
        median_delay: Optional[float] = None
        total_delay: Optional[float] = None
        if dur_col is not None:
            delayed_durations = group.loc[group["_is_delayed"], "_duration"].dropna()
            if not delayed_durations.empty:
                avg_delay = float(delayed_durations.mean())
                median_delay = float(delayed_durations.median())
                total_delay = float(delayed_durations.sum())
        rows.append(
            {
                "warehouse": str(warehouse),
                "records": int(len(group)),
                "shipments": shipments,
                "delayed_shipments": delayed_shipments,
                "delay_rate": delay_rate,
                "avg_delay": avg_delay,
                "median_delay": median_delay,
                "total_delay": total_delay,
            }
        )
    result = pd.DataFrame(
        rows,
        columns=[
            "warehouse", "records", "shipments", "delayed_shipments",
            "delay_rate", "avg_delay", "median_delay", "total_delay",
        ],
    )
    return result.sort_values(
        ["delay_rate", "warehouse"], ascending=[False, True], kind="mergesort", na_position="last"
    ).reset_index(drop=True)


def top_delayed_warehouses(metrics: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Return the top ``n`` warehouses by delay rate (warehouse_metrics output)."""
    if "delay_rate" not in metrics.columns:
        raise ValueError("Expected warehouse_metrics() output with a 'delay_rate' column.")
    if n <= 0:
        raise ValueError(f"Expected n > 0, got {n}.")
    return metrics.head(n).reset_index(drop=True)


def transfer_activity(dataset: pd.DataFrame) -> dict[str, Any]:
    """Summarize warehouse transfer endpoint activity (read-only).

    Counts records per ``source_warehouse`` and per
    ``destination_warehouse`` when those columns exist. Reports
    unavailability per endpoint instead of fabricating counts.
    """
    summary: dict[str, Any] = {}
    for endpoint in ("source_warehouse", "destination_warehouse"):
        if endpoint in dataset.columns:
            counts = (
                dataset[endpoint].astype("string").fillna("unknown")
                .value_counts().rename_axis("warehouse").reset_index(name="transfers")
                .sort_values("transfers", ascending=False, kind="mergesort")
                .reset_index(drop=True)
            )
            summary[endpoint] = {"available": True, "activity": counts}
        else:
            summary[endpoint] = {
                "available": False,
                "reason": f"column '{endpoint}' absent",
            }
    return summary


def warehouse_trends(
    dataset: pd.DataFrame,
    timestamp_column: Optional[str] = None,
    warehouse_column: Optional[str] = None,
    shipment_column: Optional[str] = None,
    freq: str = "D",
) -> pd.DataFrame:
    """Return per-warehouse, per-period shipment counts (read-only)."""
    warehouse_col = _resolve_warehouse_column(dataset, warehouse_column)
    ts_columns = find_timestamp_columns(dataset)
    resolved_ts = timestamp_column or (ts_columns[0] if ts_columns else None)
    if resolved_ts is None or resolved_ts not in dataset.columns:
        raise ValueError("No timestamp column found for warehouse trend analysis.")
    ship_col = shipment_column or find_shipment_column(dataset)
    if ship_col is not None and ship_col not in dataset.columns:
        ship_col = None

    stamps = pd.to_datetime(dataset[resolved_ts], errors="coerce", utc=True)
    valid = stamps.notna()
    if not bool(valid.any()):
        return pd.DataFrame(columns=["warehouse", "period", "records", "shipments"])
    frame = pd.DataFrame(
        {
            "warehouse": dataset.loc[valid, warehouse_col].astype(str),
            "period": stamps[valid].dt.floor(freq),
            "shipment": (
                dataset.loc[valid, ship_col].astype("string")
                if ship_col is not None
                else None
            ),
        }
    )
    grouped = frame.groupby(["warehouse", "period"], sort=True)
    result = grouped.size().to_frame("records").reset_index()
    if ship_col is not None:
        result["shipments"] = grouped["shipment"].nunique().to_numpy()
    else:
        result["shipments"] = result["records"]
    result["period"] = result["period"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    return result.sort_values(["warehouse", "period"], kind="mergesort").reset_index(drop=True)
