"""Business KPI layer for Cascading Delay Intelligence.

KPI definitions (mathematical, no invented thresholds):

* ``delay_rate = delayed_shipments / total_shipments * 100``
* ``on_time_rate = 100 - delay_rate`` (when delay status is resolvable)
* Delay duration stats (mean/median/max/min/total) are computed over
  delayed records with a non-null duration.
* ``transfer_match_rate = rows with a matched transfer / total rows * 100``
  (same for delay reports); based on the integration traceability columns
  when present.

All functions are read-only and deterministic. Unresolvable KPIs are
returned as None with a documented reason — never fabricated. Zero
denominators yield None (not 0) to avoid implying a measured rate.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from analysis._schema import (
    DELAY_MATCH_COLUMN,
    TRANSFER_MATCH_COLUMN,
    find_delay_duration_column,
    find_shipment_column,
    resolve_delay_flag,
)


def _rate(numerator: int, denominator: int) -> Optional[float]:
    """Return ``numerator / denominator * 100`` or None when empty."""
    if denominator <= 0:
        return None
    return numerator / denominator * 100.0


def compute_shipment_kpis(
    dataset: pd.DataFrame,
    shipment_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
) -> dict[str, Any]:
    """Compute shipment-level KPIs (read-only).

    * ``total_shipments``: distinct shipment IDs (or row count when no
      shipment column exists; documented in ``shipment_basis``).
    * ``delayed_shipments``: distinct shipments with any delayed record.
    * ``on_time_shipments``: total minus delayed (when resolvable).
    * Rates follow the definitions in the module docstring.
    """
    resolved_shipment = shipment_column or find_shipment_column(dataset)
    if resolved_shipment is not None and resolved_shipment not in dataset.columns:
        resolved_shipment = None
    if resolved_shipment:
        total_shipments = int(dataset[resolved_shipment].nunique(dropna=True))
        shipment_basis = f"distinct {resolved_shipment}"
    else:
        total_shipments = int(len(dataset))
        shipment_basis = "rows (no shipment column present)"

    flag, flag_info = resolve_delay_flag(
        dataset,
        duration_column=duration_column,
        flag_column=flag_column,
        status_column=status_column,
    )
    warnings: list[str] = []
    if flag is None:
        warnings.append(f"Delay status unresolvable: {flag_info.get('reason')}.")
        return {
            "total_records": int(len(dataset)),
            "total_shipments": total_shipments,
            "shipment_basis": shipment_basis,
            "delayed_shipments": None,
            "on_time_shipments": None,
            "delay_rate": None,
            "on_time_rate": None,
            "delay_signal": flag_info,
            "warnings": warnings,
        }

    if resolved_shipment:
        delayed_shipments: Optional[int] = int(
            dataset.loc[flag, resolved_shipment].nunique(dropna=True)
        )
    else:
        delayed_shipments = int(flag.sum())
        warnings.append("No shipment column; delayed count is record-based.")
    on_time = total_shipments - delayed_shipments
    delay_rate = _rate(delayed_shipments, total_shipments)
    if delay_rate is None:
        warnings.append("Empty dataset; rates are undefined.")
    return {
        "total_records": int(len(dataset)),
        "total_shipments": total_shipments,
        "shipment_basis": shipment_basis,
        "delayed_shipments": delayed_shipments,
        "on_time_shipments": on_time,
        "delay_rate": delay_rate,
        "on_time_rate": (100.0 - delay_rate) if delay_rate is not None else None,
        "delay_signal": flag_info,
        "warnings": warnings,
    }


def compute_delay_kpis(
    dataset: pd.DataFrame,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
) -> dict[str, Any]:
    """Compute delay-duration KPIs over delayed records (read-only).

    Stats describe records flagged delayed that also carry a non-null
    duration. ``delayed_records_without_duration`` is reported so the gap
    is visible instead of hidden.
    """
    resolved = duration_column or find_delay_duration_column(dataset)
    if resolved is not None and resolved not in dataset.columns:
        resolved = None
    if resolved is None:
        return {
            "available": False,
            "reason": "no delay duration column present",
            "delayed_records": None,
            "average_delay": None,
            "median_delay": None,
            "max_delay": None,
            "min_delay": None,
            "total_delay": None,
        }
    flag, flag_info = resolve_delay_flag(
        dataset,
        duration_column=resolved,
        flag_column=flag_column,
        status_column=status_column,
    )
    durations = pd.to_numeric(dataset[resolved], errors="coerce")
    if flag is not None:
        delayed_durations = durations[flag].dropna()
        delayed_records = int(flag.sum())
    else:  # No flag signal: fall back to positive durations only.
        delayed_durations = durations[durations > 0].dropna()
        delayed_records = int((durations > 0).sum())
    without_duration = delayed_records - int(len(delayed_durations))
    if delayed_durations.empty:
        return {
            "available": True,
            "source_column": resolved,
            "delay_signal": flag_info if flag is not None else {"method": "duration_gt_zero"},
            "delayed_records": delayed_records,
            "delayed_records_without_duration": without_duration,
            "average_delay": None,
            "median_delay": None,
            "max_delay": None,
            "min_delay": None,
            "total_delay": None,
        }
    return {
        "available": True,
        "source_column": resolved,
        "delay_signal": flag_info if flag is not None else {"method": "duration_gt_zero"},
        "delayed_records": delayed_records,
        "delayed_records_without_duration": without_duration,
        "average_delay": float(delayed_durations.mean()),
        "median_delay": float(delayed_durations.median()),
        "max_delay": float(delayed_durations.max()),
        "min_delay": float(delayed_durations.min()),
        "total_delay": float(delayed_durations.sum()),
    }


def compute_operational_kpis(dataset: pd.DataFrame) -> dict[str, Any]:
    """Compute integration-coverage KPIs from traceability columns.

    Reports the share of integrated rows matched to a delay report and to
    a warehouse transfer, plus average operational records per shipment.
    Missing traceability columns yield None with a reason.
    """
    total_rows = int(len(dataset))
    result: dict[str, Any] = {"total_records": total_rows}

    for label, column in (
        ("delay_report", DELAY_MATCH_COLUMN),
        ("transfer", TRANSFER_MATCH_COLUMN),
    ):
        if column in dataset.columns:
            matched = int((dataset[column].astype("string") == "both").sum())
            result[f"rows_with_{label}_match"] = matched
            result[f"{label}_match_rate"] = _rate(matched, total_rows)
        else:
            result[f"rows_with_{label}_match"] = None
            result[f"{label}_match_rate"] = None
            result[f"{label}_match_unavailable"] = f"column '{column}' absent"

    shipment_column = find_shipment_column(dataset)
    if shipment_column and total_rows:
        shipments = int(dataset[shipment_column].nunique(dropna=True))
        result["records_per_shipment"] = total_rows / shipments if shipments else None
    else:
        result["records_per_shipment"] = None
    return result


def compute_kpis(
    dataset: pd.DataFrame,
    shipment_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
) -> dict[str, Any]:
    """Compute the full KPI bundle (shipment + delay + operational)."""
    return {
        "shipment": compute_shipment_kpis(
            dataset,
            shipment_column=shipment_column,
            duration_column=duration_column,
            flag_column=flag_column,
            status_column=status_column,
        ),
        "delay": compute_delay_kpis(
            dataset,
            duration_column=duration_column,
            flag_column=flag_column,
            status_column=status_column,
        ),
        "operational": compute_operational_kpis(dataset),
    }
