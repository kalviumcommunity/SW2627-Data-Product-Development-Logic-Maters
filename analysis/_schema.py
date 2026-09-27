"""Shared schema helpers for the analytics layer (internal use).

Detects the columns the analytics functions need from whatever the
integrated (or cleaned) dataset actually contains. Candidate names come
from Design.md section 8 (expected source fields) and the integration
layer's traceability columns. Nothing is invented: a detector returns
``None`` when no candidate column is present, and callers report the gap
instead of fabricating a metric.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

SHIPMENT_CANDIDATES = ("shipment_id", "affected_shipment_id", "root_shipment_id")
DELAY_DURATION_CANDIDATES = (
    "delay_duration",
    "final_delay_minutes",
    "total_delay_minutes",
    "delay_minutes",
    "initial_delay_minutes",
)
DELAY_REASON_CANDIDATES = (
    "delay_reason",
    "root_cause_category",
    "root_cause",
    "disruption_type",
    "reason_name",
)
ROUTE_CANDIDATES = ("route_id", "route", "corridor")
WAREHOUSE_CANDIDATES = (
    "warehouse_id",
    "origin_location_id",
    "destination_location_id",
    "location_id",
    "upstream_location_id",
    "downstream_location_id",
    "source_warehouse",
    "destination_warehouse",
)
STATUS_CANDIDATES = ("status", "delivery_status", "event_status", "impact_status", "delay_status")
SCAN_TYPE_CANDIDATES = ("scan_type", "event_type", "propagation_type")
TIMESTAMP_CANDIDATES = (
    "timestamp",
    "actual_departure",
    "planned_departure",
    "scheduled_timestamp",
    "actual_timestamp",
    "actual_delivery_time",
    "promised_delivery_time",
    "start_time",
    "planned_dependency_time",
    "reported_at",
    "transfer_time",
    "expected_transfer_time",
    "actual_transfer_time",
)

#: Match columns written by ``pipeline.integration.build_integrated_dataset``.
DELAY_MATCH_COLUMN = "_delay_match"
TRANSFER_MATCH_COLUMN = "_transfer_match"

#: Default status values treated as "delayed" (case-insensitive, stripped).
#: Caller-overridable; used only when no duration/flag column exists.
DEFAULT_DELAYED_STATUS_VALUES = (
    "delayed",
    "delivered late",
    "at risk",
    "active cascade",
    "severe delay breached",
    "delayed - propagated",
)


def find_column(dataset: pd.DataFrame, candidates: tuple[str, ...]) -> Optional[str]:
    """Return the first candidate column present in ``dataset``, else None."""
    for candidate in candidates:
        if candidate in dataset.columns:
            return candidate
    return None


def find_shipment_column(dataset: pd.DataFrame) -> Optional[str]:
    """Return the shipment identifier column, else None."""
    return find_column(dataset, SHIPMENT_CANDIDATES)


def find_delay_duration_column(dataset: pd.DataFrame) -> Optional[str]:
    """Return the delay duration column, else None."""
    return find_column(dataset, DELAY_DURATION_CANDIDATES)


def find_delay_reason_column(dataset: pd.DataFrame) -> Optional[str]:
    """Return the delay reason column, else None."""
    return find_column(dataset, DELAY_REASON_CANDIDATES)


def find_route_column(dataset: pd.DataFrame) -> Optional[str]:
    """Return the route identifier column, else None."""
    return find_column(dataset, ROUTE_CANDIDATES)


def find_warehouse_columns(dataset: pd.DataFrame) -> list[str]:
    """Return warehouse identifier columns present, in candidate order."""
    return [col for col in WAREHOUSE_CANDIDATES if col in dataset.columns]


def find_timestamp_columns(dataset: pd.DataFrame) -> list[str]:
    """Return timestamp columns present, in candidate order."""
    return [col for col in TIMESTAMP_CANDIDATES if col in dataset.columns]


def resolve_delay_flag(
    dataset: pd.DataFrame,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
    delayed_status_values: tuple[str, ...] = DEFAULT_DELAYED_STATUS_VALUES,
) -> tuple[Optional[pd.Series], dict[str, Any]]:
    """Resolve a boolean per-record delay flag without modifying ``dataset``.

    Precedence (first available wins):

    1. Explicit ``flag_column`` (truthy values; NaN treated as not delayed).
    2. ``duration_column`` (or auto-detected): delay where duration > 0.
    3. ``status_column`` (or auto-detected): delay where the stripped,
       lowercased status is in ``delayed_status_values``.

    Returns ``(flag, info)`` where flag is a boolean Series (indexed like
    ``dataset``) or None when no delay signal exists. ``info`` records the
    ``method`` and ``source_column`` used, or the reason no flag exists.
    """
    if flag_column is not None and flag_column in dataset.columns:
        flag = dataset[flag_column].fillna(False).astype(bool)
        flag.index = dataset.index
        return flag, {"method": "flag_column", "source_column": flag_column}

    resolved_duration = duration_column
    if resolved_duration is None:
        resolved_duration = find_delay_duration_column(dataset)
    elif resolved_duration not in dataset.columns:
        resolved_duration = None
    if resolved_duration is not None:
        numeric = pd.to_numeric(dataset[resolved_duration], errors="coerce")
        flag = numeric.fillna(0) > 0
        flag.index = dataset.index
        return flag, {"method": "duration_gt_zero", "source_column": resolved_duration}

    resolved_status = status_column
    if resolved_status is None:
        resolved_status = find_column(dataset, STATUS_CANDIDATES)
    elif resolved_status not in dataset.columns:
        resolved_status = None
    if resolved_status is not None:
        lowered = {str(v).strip().lower() for v in delayed_status_values}
        flag = (
            dataset[resolved_status]
            .astype("string")
            .str.strip()
            .str.lower()
            .isin(lowered)
            .fillna(False)
        )
        flag.index = dataset.index
        return flag, {"method": "status_values", "source_column": resolved_status}

    return None, {"method": "unavailable", "reason": "no delay flag, duration, or status column present"}
