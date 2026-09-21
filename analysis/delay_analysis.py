"""Delay-focused analysis: reasons, segments, and time patterns.

All functions are read-only and deterministic. Time features are derived
from timestamp columns into a *copy* (the source frame is never modified).
Rolling metrics require a full window (``min_periods = window``) and flag
sparse inputs instead of implying trends from thin data. No cascade flags
or thresholds are created here.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from analysis._schema import (
    DELAY_MATCH_COLUMN,
    TRANSFER_MATCH_COLUMN,
    find_delay_duration_column,
    find_delay_reason_column,
    find_route_column,
    find_shipment_column,
    find_timestamp_columns,
    find_warehouse_columns,
    resolve_delay_flag,
)

_FREQUENCY_ALIASES = {"M": "ME", "m": "ME"}


def _normalize_freq(freq: str) -> str:
    return _FREQUENCY_ALIASES.get(freq, freq)


def delay_reason_breakdown(
    dataset: pd.DataFrame,
    reason_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """Return per-reason records, share, and delay durations (read-only).

    Raises ValueError when no reason column exists. Duration stats cover
    records with a non-null duration; reasons without any duration show
    None stats rather than zeros.
    """
    resolved_reason = reason_column or find_delay_reason_column(dataset)
    if resolved_reason is None or resolved_reason not in dataset.columns:
        raise ValueError(
            "No delay reason column found. Pass reason_column explicitly or "
            "ensure 'delay_reason' is present in the dataset."
        )
    dur_col = duration_column or find_delay_duration_column(dataset)
    if dur_col is not None and dur_col not in dataset.columns:
        dur_col = None

    reasons = dataset[resolved_reason].astype("string").fillna("unknown")
    durations = (
        pd.to_numeric(dataset[dur_col], errors="coerce") if dur_col is not None else None
    )
    total = float(len(dataset)) if len(dataset) else 1.0
    rows: list[dict[str, Any]] = []
    for reason, group_idx in reasons.groupby(reasons, sort=True).groups.items():
        count = int(len(group_idx))
        avg_delay: Optional[float] = None
        median_delay: Optional[float] = None
        total_delay: Optional[float] = None
        if durations is not None:
            observed = durations.loc[group_idx].dropna()
            if not observed.empty:
                avg_delay = float(observed.mean())
                median_delay = float(observed.median())
                total_delay = float(observed.sum())
        rows.append(
            {
                "delay_reason": str(reason),
                "records": count,
                "pct_of_records": count / total * 100.0,
                "avg_delay": avg_delay,
                "median_delay": median_delay,
                "total_delay": total_delay,
            }
        )
    result = pd.DataFrame(
        rows,
        columns=[
            "delay_reason", "records", "pct_of_records",
            "avg_delay", "median_delay", "total_delay",
        ],
    )
    result = result.sort_values("records", ascending=False, kind="mergesort").reset_index(drop=True)
    if top_n is not None:
        if top_n <= 0:
            raise ValueError(f"Expected top_n > 0, got {top_n}.")
        result = result.head(top_n).reset_index(drop=True)
    return result


def delay_by_segment(
    dataset: pd.DataFrame,
    segment_column: str,
    shipment_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
) -> pd.DataFrame:
    """Return delay metrics grouped by any caller-chosen segment column.

    Only the named segment column is used, so this works for route,
    warehouse, delay reason, or any other dimension actually present.
    Raises ValueError when the segment column is absent.
    """
    if segment_column not in dataset.columns:
        raise ValueError(f"Segment column '{segment_column}' not found in dataset.")
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
    working = pd.DataFrame({"segment": dataset[segment_column].astype("string").fillna("unknown")})
    working["_is_delayed"] = flag if flag is not None else False
    working["_has_signal"] = flag is not None
    if dur_col is not None:
        working["_duration"] = pd.to_numeric(dataset[dur_col], errors="coerce")
    if ship_col is not None:
        working["_shipment"] = dataset[ship_col].astype("string")

    rows: list[dict[str, Any]] = []
    for segment, group in working.groupby("segment", sort=True):
        shipments = (
            int(group["_shipment"].nunique(dropna=True))
            if ship_col is not None
            else int(len(group))
        )
        delayed: Optional[int] = None
        rate: Optional[float] = None
        if bool(group["_has_signal"].iloc[0]):
            delayed = (
                int(group.loc[group["_is_delayed"], "_shipment"].nunique(dropna=True))
                if ship_col is not None
                else int(group["_is_delayed"].sum())
            )
            rate = delayed / shipments * 100.0 if shipments else None
        avg_delay: Optional[float] = None
        if dur_col is not None:
            observed = group.loc[group["_is_delayed"], "_duration"].dropna()
            if not observed.empty:
                avg_delay = float(observed.mean())
        rows.append(
            {
                "segment": str(segment),
                "records": int(len(group)),
                "shipments": shipments,
                "delayed": delayed,
                "delay_rate": rate,
                "avg_delay": avg_delay,
            }
        )
    result = pd.DataFrame(
        rows, columns=["segment", "records", "shipments", "delayed", "delay_rate", "avg_delay"]
    )
    return result.sort_values(
        ["delay_rate", "segment"], ascending=[False, True], kind="mergesort", na_position="last"
    ).reset_index(drop=True)


def derive_time_features(
    dataset: pd.DataFrame,
    timestamp_column: Optional[str] = None,
) -> pd.DataFrame:
    """Return a copy with date parts derived from one timestamp column.

    Adds ``<column>_date``, ``_year``, ``_month`` (YYYY-MM), ``_iso_week``
    (YYYY-Www), ``_day_of_week``, and ``_hour``. Unparsable values yield
    NaT/None. The input frame is never modified. Raises ValueError when no
    usable timestamp column exists.
    """
    ts_columns = find_timestamp_columns(dataset)
    resolved = timestamp_column or (ts_columns[0] if ts_columns else None)
    if resolved is None or resolved not in dataset.columns:
        raise ValueError("No timestamp column found for time feature derivation.")
    stamps = pd.to_datetime(dataset[resolved], errors="coerce", utc=True)
    enriched = dataset.copy(deep=True)
    enriched[f"{resolved}_date"] = stamps.dt.date.astype("string")
    enriched[f"{resolved}_year"] = stamps.dt.year.astype("Int64")
    enriched[f"{resolved}_month"] = stamps.dt.strftime("%Y-%m").astype("string")
    iso = stamps.dt.isocalendar()
    enriched[f"{resolved}_iso_week"] = (
        iso["year"].astype("string") + "-W" + iso["week"].astype("string").str.zfill(2)
    )
    enriched[f"{resolved}_day_of_week"] = stamps.dt.day_name().astype("string")
    enriched[f"{resolved}_hour"] = stamps.dt.hour.astype("Int64")
    return enriched


def delay_over_time(
    dataset: pd.DataFrame,
    timestamp_column: Optional[str] = None,
    shipment_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
    freq: str = "D",
) -> pd.DataFrame:
    """Aggregate shipments, delays, and durations per time period.

    Returns columns ``period`` (UTC start), ``records``, ``shipments``,
    ``delayed_shipments``, ``delay_rate``, ``avg_delay``. Empty periods are
    omitted. Raises ValueError when no usable timestamp column exists.
    """
    freq = _normalize_freq(freq)
    ts_columns = find_timestamp_columns(dataset)
    resolved_ts = timestamp_column or (ts_columns[0] if ts_columns else None)
    if resolved_ts is None or resolved_ts not in dataset.columns:
        raise ValueError("No timestamp column found for time-series analysis.")
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

    stamps = pd.to_datetime(dataset[resolved_ts], errors="coerce", utc=True)
    valid = stamps.notna()
    if not bool(valid.any()):
        return pd.DataFrame(
            columns=["period", "records", "shipments", "delayed_shipments", "delay_rate", "avg_delay"]
        )
    valid_index = dataset.index[valid]
    if flag is not None:
        delayed_mask = flag.loc[valid_index].to_numpy(dtype=bool)
    else:
        delayed_mask = [False] * int(valid.sum())
    if dur_col is not None:
        durations_all = pd.to_numeric(dataset[dur_col], errors="coerce")
    else:
        durations_all = None
    frame = pd.DataFrame(
        {
            "period": stamps[valid].to_numpy(),
            "shipment": (
                dataset.loc[valid_index, ship_col].astype("string").to_numpy()
                if ship_col is not None
                else None
            ),
            "is_delayed": delayed_mask,
            "duration": (
                durations_all.loc[valid_index].to_numpy()
                if durations_all is not None
                else float("nan")
            ),
        }
    )
    frame["period"] = pd.to_datetime(frame["period"], utc=True).dt.floor(freq)
    rows: list[dict[str, Any]] = []
    for period, group in frame.groupby("period", sort=True):
        shipments = (
            int(pd.Series(group["shipment"]).nunique(dropna=True))
            if ship_col is not None
            else int(len(group))
        )
        delayed_shipments: Optional[int] = None
        delay_rate: Optional[float] = None
        if flag is not None:
            mask = group["is_delayed"].astype(bool).to_numpy()
            if ship_col is not None:
                delayed_shipments = int(pd.Series(group["shipment"])[mask].nunique(dropna=True))
            else:
                delayed_shipments = int(mask.sum())
            delay_rate = delayed_shipments / shipments * 100.0 if shipments else None
        avg_delay: Optional[float] = None
        if dur_col is not None and flag is not None:
            observed = pd.to_numeric(group["duration"], errors="coerce")[
                group["is_delayed"].astype(bool).to_numpy()
            ].dropna()
            if not observed.empty:
                avg_delay = float(observed.mean())
        rows.append(
            {
                "period": period,
                "records": int(len(group)),
                "shipments": shipments,
                "delayed_shipments": delayed_shipments,
                "delay_rate": delay_rate,
                "avg_delay": avg_delay,
            }
        )
    result = pd.DataFrame(
        rows,
        columns=["period", "records", "shipments", "delayed_shipments", "delay_rate", "avg_delay"],
    ).sort_values("period", kind="mergesort").reset_index(drop=True)
    return result


def rolling_delay_rate(
    trend: pd.DataFrame,
    window: int = 7,
    value_column: str = "delay_rate",
) -> pd.DataFrame:
    """Add rolling-average columns to a :func:`delay_over_time` table.

    Requires a full ``window`` of periods (``min_periods = window``); early
    rows are NaN rather than partial averages. Returns
    ``sparse_warning=True`` in ``attrs`` when the table holds fewer than
    ``window`` periods. Raises ValueError for invalid input.
    """
    if window <= 0:
        raise ValueError(f"Expected window > 0, got {window}.")
    if value_column not in trend.columns:
        raise ValueError(f"Column '{value_column}' not found in trend table.")
    if "period" not in trend.columns:
        raise ValueError("Trend table must contain a 'period' column.")
    result = trend.sort_values("period", kind="mergesort").reset_index(drop=True).copy(deep=True)
    series = pd.to_numeric(result[value_column], errors="coerce")
    result[f"rolling_avg_{value_column}_{window}"] = series.rolling(
        window=window, min_periods=window
    ).mean()
    result.attrs["sparse_warning"] = bool(len(result) < window)
    result.attrs["window"] = window
    return result


def available_dimensions(dataset: pd.DataFrame) -> dict[str, Any]:
    """Report which analytical dimensions the dataset actually supports."""
    warehouses = find_warehouse_columns(dataset)
    timestamps = find_timestamp_columns(dataset)
    return {
        "shipment": find_shipment_column(dataset),
        "delay_duration": find_delay_duration_column(dataset),
        "delay_reason": find_delay_reason_column(dataset),
        "route": find_route_column(dataset),
        "warehouses": warehouses,
        "timestamps": timestamps,
        "delay_match": DELAY_MATCH_COLUMN if DELAY_MATCH_COLUMN in dataset.columns else None,
        "transfer_match": TRANSFER_MATCH_COLUMN if TRANSFER_MATCH_COLUMN in dataset.columns else None,
    }


def segment_summary(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return delay_by_segment tables for each available dimension."""
    dims = available_dimensions(dataset)
    tables: dict[str, pd.DataFrame] = {}
    if dims["route"] is not None:
        tables["route"] = delay_by_segment(dataset, dims["route"])
    for warehouse_col in dims["warehouses"]:
        tables[f"warehouse:{warehouse_col}"] = delay_by_segment(dataset, warehouse_col)
    if dims["delay_reason"] is not None:
        tables["delay_reason"] = delay_by_segment(dataset, dims["delay_reason"])
    return tables
