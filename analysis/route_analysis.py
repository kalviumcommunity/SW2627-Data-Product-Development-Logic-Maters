"""Route-level operational analysis (read-only, factual metrics only).

No subjective route scores are produced. Outputs are plain delay facts
(shipments, rates, durations) that let the dashboard surface high-delay
routes. Associations are reported with neutral language; no causality is
claimed.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from analysis._schema import (
    find_delay_duration_column,
    find_route_column,
    find_shipment_column,
    find_timestamp_columns,
    resolve_delay_flag,
)


def _resolve_route_column(dataset: pd.DataFrame, route_column: Optional[str]) -> str:
    resolved = route_column or find_route_column(dataset)
    if resolved is None or resolved not in dataset.columns:
        raise ValueError(
            "No route column found. Pass route_column explicitly or ensure "
            "'route_id' is present in the dataset."
        )
    return resolved


def route_metrics(
    dataset: pd.DataFrame,
    route_column: Optional[str] = None,
    shipment_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
) -> pd.DataFrame:
    """Return one row per route with factual delay metrics.

    Columns: ``route``, ``records``, ``shipments``, ``delayed_shipments``,
    ``delay_rate`` (delayed/total shipments x 100, None when unresolvable),
    ``avg_delay``, ``median_delay``, ``total_delay`` (over delayed records
    with non-null duration; None when no duration column). Sorted by
    ``delay_rate`` descending (nulls last), then route ascending.
    """
    route_col = _resolve_route_column(dataset, route_column)
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
    working = dataset[[route_col]].copy()
    working["_is_delayed"] = flag if flag is not None else False
    working["_has_signal"] = flag is not None
    if dur_col is not None:
        working["_duration"] = pd.to_numeric(dataset[dur_col], errors="coerce")
    if ship_col is not None:
        working["_shipment"] = dataset[ship_col].astype("string")

    rows: list[dict[str, Any]] = []
    for route, group in working.groupby(route_col, sort=True):
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
                "route": str(route),
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
            "route", "records", "shipments", "delayed_shipments",
            "delay_rate", "avg_delay", "median_delay", "total_delay",
        ],
    )
    return result.sort_values(
        ["delay_rate", "route"], ascending=[False, True], kind="mergesort", na_position="last"
    ).reset_index(drop=True)


def top_delayed_routes(metrics: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Return the top ``n`` routes by delay rate (input must be route_metrics output)."""
    if "delay_rate" not in metrics.columns:
        raise ValueError("Expected route_metrics() output with a 'delay_rate' column.")
    if n <= 0:
        raise ValueError(f"Expected n > 0, got {n}.")
    return metrics.head(n).reset_index(drop=True)


def route_trends(
    dataset: pd.DataFrame,
    timestamp_column: Optional[str] = None,
    route_column: Optional[str] = None,
    shipment_column: Optional[str] = None,
    freq: str = "D",
) -> pd.DataFrame:
    """Return per-route, per-period shipment and delay counts (read-only).

    Periods with no records are omitted. Raises ValueError when no usable
    timestamp column exists.
    """
    route_col = _resolve_route_column(dataset, route_column)
    ts_columns = find_timestamp_columns(dataset)
    resolved_ts = timestamp_column or (ts_columns[0] if ts_columns else None)
    if resolved_ts is None or resolved_ts not in dataset.columns:
        raise ValueError("No timestamp column found for route trend analysis.")
    ship_col = shipment_column or find_shipment_column(dataset)
    if ship_col is not None and ship_col not in dataset.columns:
        ship_col = None

    stamps = pd.to_datetime(dataset[resolved_ts], errors="coerce", utc=True)
    valid = stamps.notna()
    if not bool(valid.any()):
        return pd.DataFrame(columns=["route", "period", "records", "shipments"])
    frame = pd.DataFrame(
        {
            "route": dataset.loc[valid, route_col].astype(str),
            "period": stamps[valid].dt.floor(freq),
            "shipment": (
                dataset.loc[valid, ship_col].astype("string")
                if ship_col is not None
                else None
            ),
        }
    )
    grouped = frame.groupby(["route", "period"], sort=True)
    result = grouped.size().to_frame("records").reset_index()
    if ship_col is not None:
        result["shipments"] = grouped["shipment"].nunique().to_numpy()
    else:
        result["shipments"] = result["records"]
    result["period"] = result["period"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    return result.sort_values(["route", "period"], kind="mergesort").reset_index(drop=True)
