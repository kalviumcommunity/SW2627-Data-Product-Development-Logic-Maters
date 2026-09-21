"""Exploratory data analysis over integrated/cleaned logistics data.

All functions are read-only: the input DataFrame is never modified.
Metrics are computed only for columns actually present; absent dimensions
are reported as unavailable instead of fabricated.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from analysis._schema import (
    SCAN_TYPE_CANDIDATES,
    STATUS_CANDIDATES,
    find_column,
    find_delay_duration_column,
    find_delay_reason_column,
    find_route_column,
    find_shipment_column,
    find_timestamp_columns,
    find_warehouse_columns,
    resolve_delay_flag,
)


def get_dataset_summary(dataset: pd.DataFrame) -> dict[str, Any]:
    """Return structural summary: shape, shipments, missingness, duplicates."""
    row_count = int(len(dataset))
    shipment_column = find_shipment_column(dataset)
    missing = {str(col): int(dataset[col].isna().sum()) for col in dataset.columns}
    total_missing = int(sum(missing.values()))
    return {
        "row_count": row_count,
        "column_count": int(len(dataset.columns)),
        "columns": [str(col) for col in dataset.columns],
        "dtypes": {str(col): str(dataset[col].dtype) for col in dataset.columns},
        "shipment_column": shipment_column,
        "total_shipments": (
            int(dataset[shipment_column].nunique(dropna=True))
            if shipment_column
            else None
        ),
        "total_missing_cells": total_missing,
        "missing_by_column": missing,
        "duplicate_rows": int(dataset.duplicated().sum()) if row_count else 0,
    }


def get_missingness_summary(dataset: pd.DataFrame) -> pd.DataFrame:
    """Return per-column missing counts and percentages (read-only)."""
    row_count = len(dataset)
    rows = [
        {
            "column": str(col),
            "missing": int(dataset[col].isna().sum()),
            "missing_pct": (
                float(dataset[col].isna().mean() * 100.0) if row_count else 0.0
            ),
        }
        for col in dataset.columns
    ]
    result = pd.DataFrame(rows, columns=["column", "missing", "missing_pct"])
    return result.sort_values("missing", ascending=False, kind="mergesort").reset_index(drop=True)


def _distribution(
    dataset: pd.DataFrame, column: Optional[str], top_n: Optional[int] = None
) -> pd.DataFrame:
    """Return value counts for ``column``; empty frame when column is None."""
    if column is None or column not in dataset.columns:
        return pd.DataFrame(columns=["value", "count", "pct"])
    counts = dataset[column].astype("string").fillna("unknown").value_counts(dropna=False)
    total = float(len(dataset)) if len(dataset) else 1.0
    result = pd.DataFrame(
        {"value": counts.index.astype(str), "count": counts.to_numpy(dtype="int64")}
    )
    result["pct"] = result["count"] / total * 100.0
    result = result.sort_values("count", ascending=False, kind="mergesort").reset_index(drop=True)
    if top_n is not None:
        result = result.head(top_n).reset_index(drop=True)
    return result


def get_delay_distribution(
    dataset: pd.DataFrame,
    duration_column: Optional[str] = None,
    bins: int = 10,
) -> dict[str, Any]:
    """Describe the delay-duration distribution (delayed records only).

    Delayed records are those with duration > 0. Returns summary stats plus
    a histogram table; reports unavailability when no duration column exists.
    """
    resolved = duration_column or find_delay_duration_column(dataset)
    if resolved is None or resolved not in dataset.columns:
        return {"available": False, "reason": "no delay duration column present"}
    numeric = pd.to_numeric(dataset[resolved], errors="coerce")
    delayed = numeric[numeric > 0].dropna()
    if delayed.empty:
        return {
            "available": True,
            "source_column": resolved,
            "delayed_records": 0,
            "stats": None,
            "histogram": pd.DataFrame(columns=["bin_start", "bin_end", "count"]),
        }
    stats = {
        "min": float(delayed.min()),
        "max": float(delayed.max()),
        "mean": float(delayed.mean()),
        "median": float(delayed.median()),
        "std": float(delayed.std()) if len(delayed) > 1 else 0.0,
    }
    hist_counts, bin_edges = pd.cut(delayed, bins=bins, retbins=True)
    hist_table = pd.DataFrame(
        {
            "bin_start": bin_edges[:-1],
            "bin_end": bin_edges[1:],
            "count": hist_counts.value_counts(sort=False).to_numpy(dtype="int64"),
        }
    )
    return {
        "available": True,
        "source_column": resolved,
        "delayed_records": int(len(delayed)),
        "stats": stats,
        "histogram": hist_table,
    }


def get_delay_reason_distribution(
    dataset: pd.DataFrame,
    reason_column: Optional[str] = None,
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """Return delay-reason counts; empty frame when the column is absent."""
    resolved = reason_column or find_delay_reason_column(dataset)
    return _distribution(dataset, resolved, top_n=top_n)


def get_route_distribution(
    dataset: pd.DataFrame,
    route_column: Optional[str] = None,
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """Return shipment-record counts per route; empty frame when absent."""
    resolved = route_column or find_route_column(dataset)
    return _distribution(dataset, resolved, top_n=top_n)


def get_warehouse_distribution(
    dataset: pd.DataFrame,
    warehouse_column: Optional[str] = None,
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """Return record counts per warehouse; empty frame when absent.

    Defaults to the first warehouse column present
    (``warehouse_id``, then transfer endpoints).
    """
    resolved = warehouse_column
    if resolved is None:
        columns = find_warehouse_columns(dataset)
        resolved = columns[0] if columns else None
    return _distribution(dataset, resolved, top_n=top_n)


def get_event_distribution(dataset: pd.DataFrame) -> pd.DataFrame:
    """Return record counts per operational event type.

    Uses ``scan_type`` when present, else ``status``; empty frame when
    neither exists.
    """
    column = find_column(dataset, SCAN_TYPE_CANDIDATES) or find_column(
        dataset, STATUS_CANDIDATES
    )
    result = _distribution(dataset, column)
    result.attrs["source_column"] = column or ""
    return result


def get_time_distribution(
    dataset: pd.DataFrame,
    timestamp_column: Optional[str] = None,
    freq: str = "D",
) -> dict[str, Any]:
    """Return record counts per time period for one timestamp column.

    Uses the first available timestamp column when none is given. Periods
    with no records are omitted (no misleading zero-filling).
    """
    resolved = timestamp_column
    if resolved is None:
        columns = find_timestamp_columns(dataset)
        resolved = columns[0] if columns else None
    if resolved is None or resolved not in dataset.columns:
        return {"available": False, "reason": "no timestamp column present"}
    stamps = pd.to_datetime(dataset[resolved], errors="coerce", utc=True).dropna()
    if stamps.empty:
        return {"available": True, "source_column": resolved, "periods": pd.DataFrame(
            columns=["period", "records"])}
    periods = (
        stamps.dt.floor(freq).value_counts().sort_index().rename_axis("period").reset_index(name="records")
    )
    periods["period"] = periods["period"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    return {"available": True, "source_column": resolved, "freq": freq, "periods": periods}


def get_delay_flag_summary(
    dataset: pd.DataFrame,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
) -> dict[str, Any]:
    """Summarize how delay status was resolved and what share is delayed."""
    flag, info = resolve_delay_flag(
        dataset,
        duration_column=duration_column,
        flag_column=flag_column,
        status_column=status_column,
    )
    if flag is None:
        return {"available": False, "info": info}
    shipment_column = find_shipment_column(dataset)
    delayed_shipments: Optional[int] = None
    if shipment_column:
        delayed_shipments = int(
            dataset.loc[flag, shipment_column].nunique(dropna=True)
        )
    return {
        "available": True,
        "info": info,
        "delayed_records": int(flag.sum()),
        "delayed_records_pct": float(flag.mean() * 100.0) if len(flag) else 0.0,
        "delayed_shipments": delayed_shipments,
    }
