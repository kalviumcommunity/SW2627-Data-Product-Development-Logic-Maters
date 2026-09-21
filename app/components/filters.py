"""Centralized dashboard filtering (pure logic + Streamlit widgets).

:func:`apply_filters` is pure, operates on a copy, and is the single place
where filter semantics live - pages must not reimplement it. Widget
rendering (:func:`render_sidebar_filters`) is the only Streamlit-dependent
part. Only columns actually present produce filters; unknown selection
keys are ignored.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

try:
    import streamlit as st
except ImportError:  # pragma: no cover - Streamlit always present in app env
    st = None  # type: ignore[assignment]

from analysis._schema import (
    find_delay_duration_column,
    find_delay_reason_column,
    find_route_column,
    find_shipment_column,
    find_timestamp_columns,
    find_warehouse_columns,
    resolve_delay_flag,
)

DELAY_STATUS_OPTIONS = ("All", "Delayed", "On-time")


def available_filter_options(dataset: pd.DataFrame) -> dict[str, Any]:
    """Inspect which filters the dataset actually supports."""
    timestamps = find_timestamp_columns(dataset)
    stamps = (
        pd.to_datetime(dataset[timestamps[0]], errors="coerce", utc=True)
        if timestamps
        else pd.Series(dtype="datetime64[ns, UTC]")
    )
    valid = stamps.dropna()
    flag, _ = resolve_delay_flag(dataset)
    return {
        "timestamp_column": timestamps[0] if timestamps else None,
        "min_date": valid.min().date().isoformat() if not valid.empty else None,
        "max_date": valid.max().date().isoformat() if not valid.empty else None,
        "routes": sorted(dataset[find_route_column(dataset)].dropna().astype(str).unique().tolist())
        if find_route_column(dataset) else [],
        "warehouses": sorted(
            {str(v) for col in find_warehouse_columns(dataset) for v in dataset[col].dropna().tolist()}
        ),
        "reasons": sorted(dataset[find_delay_reason_column(dataset)].dropna().astype(str).unique().tolist())
        if find_delay_reason_column(dataset) else [],
        "delay_status_available": flag is not None,
        "shipment_column": find_shipment_column(dataset),
        "duration_column": find_delay_duration_column(dataset),
    }


def apply_filters(
    dataset: pd.DataFrame,
    routes: Optional[list[str]] = None,
    warehouses: Optional[list[str]] = None,
    reasons: Optional[list[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    delay_status: str = "All",
    route_column: Optional[str] = None,
    warehouse_columns: Optional[list[str]] = None,
    reason_column: Optional[str] = None,
    timestamp_column: Optional[str] = None,
) -> pd.DataFrame:
    """Return a filtered copy; the input frame is never modified.

    Empty/None selections mean "no constraint" for that dimension.
    ``delay_status`` is one of All/Delayed/On-time and uses the analytics
    layer's delay-flag resolution. Date bounds are ISO strings compared
    against the (coerced) timestamp column's date part.
    """
    if delay_status not in DELAY_STATUS_OPTIONS:
        raise ValueError(f"delay_status must be one of {DELAY_STATUS_OPTIONS}.")
    result = dataset.copy(deep=True)
    if result.empty:
        return result

    resolved_route = route_column or find_route_column(result)
    if routes and resolved_route in result.columns:
        result = result[result[resolved_route].astype("string").isin(set(routes))]

    resolved_wh = warehouse_columns or find_warehouse_columns(result)
    if warehouses and resolved_wh:
        present = [c for c in resolved_wh if c in result.columns]
        if present:
            mask = pd.Series(False, index=result.index)
            for column in present:
                mask = mask | result[column].astype("string").isin(set(warehouses))
            result = result[mask]

    resolved_reason = reason_column or find_delay_reason_column(result)
    if reasons and resolved_reason in result.columns:
        result = result[result[resolved_reason].astype("string").isin(set(reasons))]

    ts_columns = find_timestamp_columns(result)
    resolved_ts = timestamp_column or (ts_columns[0] if ts_columns else None)
    if (start_date or end_date) and resolved_ts in result.columns:
        stamps = pd.to_datetime(result[resolved_ts], errors="coerce", utc=True)
        if start_date:
            result = result[stamps >= pd.Timestamp(start_date, tz="UTC")]
            stamps = pd.to_datetime(result[resolved_ts], errors="coerce", utc=True)
        if end_date:
            result = result[stamps <= pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]

    if delay_status != "All":
        flag, _ = resolve_delay_flag(result)
        if flag is not None:
            flag = flag.reindex(result.index, fill_value=False).astype(bool)
            result = result[flag] if delay_status == "Delayed" else result[~flag]

    return result.reset_index(drop=True)


def render_sidebar_filters(dataset: pd.DataFrame) -> dict[str, Any]:
    """Render sidebar widgets for supported dimensions; return selections."""
    if st is None:  # pragma: no cover
        raise RuntimeError("Streamlit is required to render filters.")
    options = available_filter_options(dataset)
    selections: dict[str, Any] = {
        "routes": [], "warehouses": [], "reasons": [],
        "start_date": None, "end_date": None, "delay_status": "All",
    }
    st.sidebar.header("Filters")
    if options["timestamp_column"] and options["min_date"]:
        picked = st.sidebar.date_input(
            "Date range",
            value=(
                pd.Timestamp(options["min_date"]).date(),
                pd.Timestamp(options["max_date"]).date(),
            ),
            key="flt_dates",
        )
        # Range mode returns a tuple/list (possibly partial); be liberal.
        if isinstance(picked, (tuple, list)):
            start = picked[0] if len(picked) > 0 else None
            end = picked[1] if len(picked) > 1 else start
        else:
            start, end = picked, picked
        selections["start_date"] = start.isoformat() if start is not None else None
        selections["end_date"] = end.isoformat() if end is not None else None
    if options["routes"]:
        selections["routes"] = st.sidebar.multiselect(
            "Route", options["routes"], key="flt_routes"
        )
    if options["warehouses"]:
        selections["warehouses"] = st.sidebar.multiselect(
            "Warehouse", options["warehouses"], key="flt_warehouses"
        )
    if options["reasons"]:
        selections["reasons"] = st.sidebar.multiselect(
            "Delay reason", options["reasons"], key="flt_reasons"
        )
    if options["delay_status_available"]:
        selections["delay_status"] = st.sidebar.selectbox(
            "Shipment status", DELAY_STATUS_OPTIONS, key="flt_status"
        )
    return selections
