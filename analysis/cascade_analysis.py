"""Cascading-delay analysis: journey reconstruction + cascade candidates.

Definitions (no invented thresholds, association - not causation):

* *Event*: one integrated record with a usable timestamp.
* *Delayed event*: per ``analysis._schema.resolve_delay_flag``
  (explicit flag, else duration > 0, else status values).
* *Cascade candidate*: a shipment journey with an initial delayed event
  followed by at least one later delayed (*downstream*) event. A single
  delay is NOT a cascade. Temporal order is reported as
  "downstream delay observed", never as proof of causation.

Defaults apply NO duration threshold and NO time window: any later
delayed event qualifies. Optional ``min_delay_duration`` and
``max_downstream_gap`` narrow the rule explicitly and are reported in
every output. There is no hardcoded 30/60-minute rule anywhere.

Aggregation levels:

* event level: ordered journey rows (``reconstruct_shipment_journey``);
* shipment level: one row per candidate shipment
  (``detect_cascade_candidates``). Durations are compared per event
  (initial vs final); rows are never blindly summed.

All functions are read-only, deterministic, and UI-independent. No
machine learning, no alerts, no Streamlit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

import numpy as np

from analysis._schema import (
    DEFAULT_DELAYED_STATUS_VALUES,
    STATUS_CANDIDATES,
    TRANSFER_MATCH_COLUMN,
    find_column,
    find_delay_duration_column,
    find_delay_reason_column,
    find_route_column,
    find_shipment_column,
    find_timestamp_columns,
    find_warehouse_columns,
    resolve_delay_flag,
)

PathLike = Union[str, Path]

DEFAULT_CASCADE_OUTPUT = Path("data/processed/cascade_candidates.csv")

#: Heuristic delivery-status values (caller-overridable) used only to label
#: a last delayed event as "final_delivery_delay". Mirrors the
#: ``delayed_status_values`` convention in analysis/_schema.py.
DEFAULT_DELIVERY_STATUS_VALUES = ("delivered",)

#: Signal columns treated as transfer evidence when non-null (besides an
#: explicit transfer_id column).
TRANSFER_SIGNAL_COLUMNS = ("transfer_id", TRANSFER_MATCH_COLUMN)

#: Cascade stage labels in chronological meaning (not every journey shows all).
STAGE_INITIAL = "initial_delay"
STAGE_TRANSFER = "transfer_disruption"
STAGE_WAREHOUSE = "warehouse_delay"
STAGE_ROUTE = "downstream_route_delay"
STAGE_FINAL = "final_delivery_delay"
STAGE_GENERIC = "downstream_delay"


def _resolve_required(
    dataset: pd.DataFrame,
    explicit: Optional[str],
    finder,
    label: str,
) -> str:
    """Resolve a required column or raise an actionable ValueError."""
    if explicit is not None:
        if explicit not in dataset.columns:
            raise ValueError(f"{label} column '{explicit}' not found in dataset.")
        return explicit
    resolved = finder(dataset)
    if resolved is None:
        raise ValueError(
            f"No {label} column found. Pass it explicitly or ensure the "
            f"integrated dataset contains it."
        )
    return resolved


def _has_signal(value: Any) -> bool:
    """True when a stage-signal cell carries information (non-null/non-blank)."""
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and value.strip() in ("", "unknown", "none"):
        return False
    return True


def reconstruct_shipment_journey(
    dataset: pd.DataFrame,
    shipment_column: Optional[str] = None,
    timestamp_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    status_column: Optional[str] = None,
    delayed_status_values: tuple[str, ...] = DEFAULT_DELAYED_STATUS_VALUES,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reconstruct ordered per-shipment event journeys (read-only).

    Keeps rows with a valid shipment ID and parsable primary timestamp,
    drops exact duplicate rows within a shipment (they cannot be separate
    stages), and sorts deterministically by timestamp; ties are broken by
    any additional timestamp columns present, then by stable input order
    (mergesort). Adds ``_event_time``, ``_event_seq`` (1-based per
    shipment), and ``_is_delayed``. The input frame is never modified.

    Returns ``(events, report)`` where report counts shipments, events,
    and explicitly skipped rows (missing shipment/timestamp, duplicates).
    An empty input yields an empty journey without column requirements.
    """
    if len(dataset) == 0:
        events = pd.DataFrame(
            {
                "_shipment": pd.Series(dtype="string"),
                "_event_time": pd.Series(dtype="datetime64[ns, UTC]"),
                "_is_delayed": pd.Series(dtype=bool),
                "_event_seq": pd.Series(dtype="int64"),
            }
        )
        for col in dataset.columns:
            events[f"src_{col}"] = pd.Series(dtype=object)
        report = {
            "shipment_column": None,
            "timestamp_column": None,
            "delay_signal": {"method": "unavailable", "reason": "empty input"},
            "input_rows": 0,
            "skipped_missing_shipment": 0,
            "skipped_unparsable_timestamp": 0,
            "skipped_total": 0,
            "duplicate_rows_removed": 0,
            "shipments": 0,
            "events": 0,
            "delayed_events": 0,
        }
        return events, report
    shipment_col = _resolve_required(
        dataset, shipment_column, find_shipment_column, "shipment"
    )
    ts_columns = find_timestamp_columns(dataset)
    primary_ts = timestamp_column
    if primary_ts is not None and primary_ts not in dataset.columns:
        raise ValueError(f"Timestamp column '{primary_ts}' not found in dataset.")
    if primary_ts is None:
        if not ts_columns:
            raise ValueError(
                "No timestamp column found. Pass timestamp_column explicitly "
                "or ensure the integrated dataset contains one."
            )
        primary_ts = ts_columns[0]
    secondary_ts = [c for c in ts_columns if c != primary_ts]
    if timestamp_column is not None:
        secondary_ts = [c for c in ts_columns if c != timestamp_column]

    flag, flag_info = resolve_delay_flag(
        dataset,
        duration_column=duration_column,
        flag_column=flag_column,
        status_column=status_column,
        delayed_status_values=delayed_status_values,
    )

    work = pd.DataFrame(
        {
            "_shipment": dataset[shipment_col].astype("string"),
            "_event_time": pd.to_datetime(
                dataset[primary_ts], errors="coerce", utc=True
            ),
        }
    )
    for extra in secondary_ts:
        work[f"_tiebreak_{extra}"] = pd.to_datetime(
            dataset[extra], errors="coerce", utc=True
        )
    work["_is_delayed"] = flag if flag is not None else False
    work["_source_pos"] = range(len(work))
    # Carry original columns for stage/event context (copied, not mutated).
    for col in dataset.columns:
        work[f"src_{col}"] = dataset[col].reset_index(drop=True).to_numpy()

    report: dict[str, Any] = {
        "shipment_column": shipment_col,
        "timestamp_column": primary_ts,
        "delay_signal": flag_info,
        "input_rows": int(len(dataset)),
    }
    missing_ship = int(work["_shipment"].isna().sum())
    # Rows skipped for either reason (missing shipment OR bad timestamp).
    skipped_mask = work["_shipment"].isna() | work["_event_time"].isna()
    report["skipped_missing_shipment"] = missing_ship
    report["skipped_unparsable_timestamp"] = int(
        (work["_event_time"].isna() & work["_shipment"].notna()).sum()
    )
    work = work.loc[~skipped_mask].reset_index(drop=True)
    report["skipped_total"] = int(skipped_mask.sum())

    before_dedup = int(len(work))
    dedup_subset = [c for c in work.columns if c != "_source_pos"]
    work = work.drop_duplicates(subset=dedup_subset, keep="first").reset_index(drop=True)
    report["duplicate_rows_removed"] = before_dedup - int(len(work))

    sort_keys = ["_shipment", "_event_time"] + [f"_tiebreak_{c}" for c in secondary_ts] + ["_source_pos"]
    work = work.sort_values(sort_keys, kind="mergesort", na_position="last").reset_index(drop=True)
    work["_event_seq"] = work.groupby("_shipment", sort=True).cumcount() + 1
    work = work.drop(columns=["_source_pos"])
    report["shipments"] = int(work["_shipment"].nunique())
    report["events"] = int(len(work))
    report["delayed_events"] = int(work["_is_delayed"].sum())
    return work, report


def get_shipment_events(events: pd.DataFrame, shipment_id: str) -> pd.DataFrame:
    """Return the ordered journey rows for one shipment (read-only view)."""
    if "_shipment" not in events.columns:
        raise ValueError("Expected reconstruct_shipment_journey() output.")
    return events[events["_shipment"] == shipment_id].sort_values(
        "_event_seq", kind="mergesort"
    ).reset_index(drop=True)


def sort_shipment_events(events: pd.DataFrame) -> pd.DataFrame:
    """Deterministically sort journey rows by shipment then event sequence."""
    if "_shipment" not in events.columns or "_event_seq" not in events.columns:
        raise ValueError("Expected reconstruct_shipment_journey() output.")
    return events.sort_values(
        ["_shipment", "_event_seq"], kind="mergesort"
    ).reset_index(drop=True)


def _event_value(row: pd.Series, column: Optional[str]) -> Any:
    """Fetch an original ``src_<column>`` value from a journey row."""
    if column is None:
        return None
    key = f"src_{column}"
    if key not in row.index:
        return None
    value = row[key]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _transfer_signal(row: pd.Series) -> bool:
    """True when the row carries transfer evidence (id or match flag)."""
    for column in TRANSFER_SIGNAL_COLUMNS:
        key = f"src_{column}"
        if key not in row.index:
            continue
        value = row[key]
        if column == TRANSFER_MATCH_COLUMN:
            if isinstance(value, str) and value.strip().lower() == "both":
                return True
        elif _has_signal(value):
            return True
    return False


def classify_cascade_stage(
    row: pd.Series,
    is_first_delayed: bool,
    is_last_event: bool,
    route_column: Optional[str] = None,
    warehouse_columns: Optional[list[str]] = None,
    status_column: Optional[str] = None,
    delivery_status_values: tuple[str, ...] = DEFAULT_DELIVERY_STATUS_VALUES,
) -> str:
    """Label one delayed journey event (documented precedence).

    1. first delayed event -> ``initial_delay``;
    2. transfer evidence -> ``transfer_disruption``;
    3. last journey event with a delivery status -> ``final_delivery_delay``;
    4. warehouse information -> ``warehouse_delay``;
    5. route information -> ``downstream_route_delay``;
    6. otherwise -> ``downstream_delay``.
    """
    if is_first_delayed:
        return STAGE_INITIAL
    if _transfer_signal(row):
        return STAGE_TRANSFER
    status_value = _event_value(row, status_column)
    if (
        is_last_event
        and isinstance(status_value, str)
        and status_value.strip().lower()
        in {str(v).strip().lower() for v in delivery_status_values}
    ):
        return STAGE_FINAL
    warehouse_columns = warehouse_columns or []
    if any(_has_signal(_event_value(row, col)) for col in warehouse_columns):
        return STAGE_WAREHOUSE
    if _has_signal(_event_value(row, route_column)):
        return STAGE_ROUTE
    return STAGE_GENERIC


def _to_timedelta(value: Any) -> Optional[pd.Timedelta]:
    """Convert a gap parameter to Timedelta (None stays None)."""
    if value is None:
        return None
    if isinstance(value, pd.Timedelta):
        return value
    try:
        return pd.to_timedelta(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid max_downstream_gap: {value!r} (expected None, "
            "a pandas Timedelta, or a parseable offset like '7D')."
        ) from exc


def detect_cascade_candidates(
    dataset: pd.DataFrame,
    shipment_column: Optional[str] = None,
    timestamp_column: Optional[str] = None,
    duration_column: Optional[str] = None,
    reason_column: Optional[str] = None,
    route_column: Optional[str] = None,
    warehouse_column: Optional[str] = None,
    status_column: Optional[str] = None,
    flag_column: Optional[str] = None,
    delayed_status_values: tuple[str, ...] = DEFAULT_DELAYED_STATUS_VALUES,
    delivery_status_values: tuple[str, ...] = DEFAULT_DELIVERY_STATUS_VALUES,
    min_delay_duration: Optional[float] = None,
    max_downstream_gap: Any = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Detect cascade candidates: initial delay + later downstream delay(s).

    A shipment is a *cascade candidate* when its ordered journey holds at
    least two delayed events: the first delayed event (initial) and at
    least one qualifying later delayed event (downstream). One delayed
    event alone is never a candidate.

    Configurable rule (all reported in ``info``):

    * ``min_delay_duration`` (default None): counted delayed events must
      have duration >= this value. Events delayed via flag/status without
      a measurable duration cannot satisfy a threshold and are skipped
      while it is set. Requires a duration column when set.
    * ``max_downstream_gap`` (default None): downstream events must occur
      within this offset after the initial delay (Timedelta or parseable
      string such as ``'7D'``). None means any later delay qualifies.

    Returns ``(candidates, info)``: one row per candidate shipment with
    initial/downstream/final event evidence, stage list, depth, and
    observed (non-causal) delay differences. Empty DataFrame with full
    columns when no candidate qualifies (including empty input, which
    skips column requirements).
    """
    gap = _to_timedelta(max_downstream_gap)
    if min_delay_duration is not None and float(min_delay_duration) < 0:
        raise ValueError("min_delay_duration must be non-negative.")
    if len(dataset) == 0:
        columns = [
            "shipment_id", "event_count", "delayed_event_count",
            "cascade_stage_count", "cascade_depth", "stages",
            "initial_delay_time", "initial_delay_duration", "initial_delay_reason",
            "initial_route", "initial_warehouse", "downstream_event_time",
            "downstream_event_seq", "downstream_delay_duration",
            "downstream_route", "downstream_warehouse", "final_event_time",
            "final_delay_duration", "downstream_delay_observed",
        ]
        info = {
            "rule": {
                "min_delay_duration": min_delay_duration,
                "max_downstream_gap": str(gap) if gap is not None else None,
            },
            "shipments_checked": 0,
            "candidate_shipments": 0,
            "single_delay_not_candidates": 0,
            "journey_report": {"input_rows": 0, "events": 0},
            "note": "Empty input; no journeys checked.",
        }
        return pd.DataFrame(columns=columns), info

    resolved_duration = duration_column or find_delay_duration_column(dataset)
    if resolved_duration is not None and resolved_duration not in dataset.columns:
        resolved_duration = None
    if min_delay_duration is not None and resolved_duration is None:
        raise ValueError(
            "min_delay_duration requires a delay duration column, "
            "but none is present."
        )
    resolved_reason = reason_column or find_delay_reason_column(dataset)
    if resolved_reason is not None and resolved_reason not in dataset.columns:
        resolved_reason = None
    resolved_route = route_column or find_route_column(dataset)
    if resolved_route is not None and resolved_route not in dataset.columns:
        resolved_route = None
    if warehouse_column is not None and warehouse_column not in dataset.columns:
        raise ValueError(f"Warehouse column '{warehouse_column}' not found.")
    warehouse_columns = (
        [warehouse_column] if warehouse_column is not None
        else find_warehouse_columns(dataset)
    )
    resolved_status = status_column or find_column(dataset, STATUS_CANDIDATES)
    if resolved_status is not None and resolved_status not in dataset.columns:
        resolved_status = None

    events, journey_report = reconstruct_shipment_journey(
        dataset,
        shipment_column=shipment_column,
        timestamp_column=timestamp_column,
        duration_column=resolved_duration,
        flag_column=flag_column,
        status_column=resolved_status,
        delayed_status_values=delayed_status_values,
    )

    def duration_of_pos(pos: int) -> Optional[float]:
        # Same semantics as the old per-row duration_of(), but on a
        # precomputed numeric array: NaN / unparseable -> None.
        if durations_all is not None:
            value = float(durations_all[pos])
            return None if pd.isna(value) else value
        value = _event_value(events.iloc[pos], resolved_duration)
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if pd.isna(number):
            return None
        return number

    # Vectorized qualification: the old per-row ``qualifies(journey.iloc[i])``
    # loop built one Series per event (minutes on 50k+ rows). Compute the
    # boolean mask once for the whole frame instead. Semantics preserved:
    # delayed flag required, plus duration >= threshold when set (NaN or
    # unparseable durations fail the threshold, as before).
    is_delayed = events["_is_delayed"].to_numpy(dtype=bool, copy=False)
    if min_delay_duration is not None:
        durations_all = pd.to_numeric(
            events[f"src_{resolved_duration}"], errors="coerce"
        ).to_numpy(dtype="float64", copy=False)
        qual_mask = is_delayed & (durations_all >= float(min_delay_duration))
    else:
        durations_all = None
        qual_mask = is_delayed
    qual_mask = np.asarray(qual_mask, dtype=bool)

    # Group positions without slicing one DataFrame per shipment (25k+
    # slices on a wide frame). factorize(sort=True) reproduces the
    # groupby(sort=True) shipment order of the previous implementation.
    codes, uniques = pd.factorize(events["_shipment"], sort=True)
    n_groups = len(uniques)
    shipments_checked = int(n_groups)
    qual_counts = np.bincount(
        codes, weights=qual_mask.astype(np.int64), minlength=n_groups
    ).astype(np.int64)
    single_delay_skipped = int(np.sum(qual_counts == 1))

    rows: list[dict[str, Any]] = []
    candidate_codes = np.flatnonzero(qual_counts >= 2)
    for code in candidate_codes:
        shipment_id = uniques[code]
        pos = np.flatnonzero(codes == code)
        journey = events.iloc[pos]
        qpos = np.flatnonzero(qual_mask[pos])
        initial_rel = int(qpos[0])
        times = journey["_event_time"].reset_index(drop=True)
        initial_time = times.iloc[initial_rel]
        if gap is not None:
            # Same predicate as before: skip a downstream event iff
            # (event_time - initial_time) > gap. Series-based so tz-aware
            # timestamps behave identically to the old scalar comparison.
            diffs = times.iloc[[int(r) for r in qpos[1:]]].reset_index(drop=True)
            diffs = diffs - initial_time
            downstream_rel = qpos[1:][~(diffs > gap).to_numpy(dtype=bool)]
        else:
            downstream_rel = qpos[1:]
        if len(downstream_rel) == 0:
            single_delay_skipped += 1
            continue
        first_down_rel = int(downstream_rel[0])
        last_down_rel = int(downstream_rel[-1])
        initial = journey.iloc[initial_rel]
        first_down = journey.iloc[first_down_rel]
        last_down = journey.iloc[last_down_rel]
        stages = [
            classify_cascade_stage(
                journey.iloc[rel],
                is_first_delayed=(rel == initial_rel),
                is_last_event=(rel == len(journey) - 1),
                route_column=resolved_route,
                warehouse_columns=warehouse_columns,
                status_column=resolved_status,
                delivery_status_values=delivery_status_values,
            )
            for rel in [initial_rel] + [int(r) for r in downstream_rel]
        ]
        initial_duration = duration_of_pos(int(pos[initial_rel]))
        final_duration = duration_of_pos(int(pos[last_down_rel]))
        rows.append(
            {
                "shipment_id": str(shipment_id),
                "event_count": int(len(journey)),
                "delayed_event_count": int(len(qpos)),
                "cascade_stage_count": int(len(stages)),
                "cascade_depth": int(len(stages) - 1),
                "stages": stages,
                "initial_delay_time": initial_time,
                "initial_delay_duration": initial_duration,
                "initial_delay_reason": _event_value(initial, resolved_reason),
                "initial_route": _event_value(initial, resolved_route),
                "initial_warehouse": (
                    _event_value(initial, warehouse_columns[0])
                    if warehouse_columns else None
                ),
                "downstream_event_time": first_down["_event_time"],
                "downstream_event_seq": int(first_down["_event_seq"]),
                "downstream_delay_duration": duration_of_pos(int(pos[first_down_rel])),
                "downstream_route": _event_value(first_down, resolved_route),
                "downstream_warehouse": (
                    _event_value(first_down, warehouse_columns[0])
                    if warehouse_columns else None
                ),
                "final_event_time": last_down["_event_time"],
                "final_delay_duration": final_duration,
                "downstream_delay_observed": (
                    (final_duration - initial_duration)
                    if initial_duration is not None and final_duration is not None
                    else None
                ),
            }
        )

    columns = [
        "shipment_id", "event_count", "delayed_event_count",
        "cascade_stage_count", "cascade_depth", "stages",
        "initial_delay_time", "initial_delay_duration", "initial_delay_reason",
        "initial_route", "initial_warehouse", "downstream_event_time",
        "downstream_event_seq", "downstream_delay_duration",
        "downstream_route", "downstream_warehouse", "final_event_time",
        "final_delay_duration", "downstream_delay_observed",
    ]
    candidates = pd.DataFrame(rows, columns=columns)
    info: dict[str, Any] = {
        "rule": {
            "min_delay_duration": min_delay_duration,
            "max_downstream_gap": str(gap) if gap is not None else None,
        },
        "shipments_checked": shipments_checked,
        "candidate_shipments": int(len(candidates)),
        "single_delay_not_candidates": single_delay_skipped,
        "journey_report": journey_report,
        "note": (
            "Candidates describe observed delay sequences (association), "
            "not proven causation."
        ),
    }
    return candidates, info


def cascade_summary_metrics(
    candidates: pd.DataFrame,
    total_shipments: Optional[int] = None,
) -> dict[str, Any]:
    """Summarize cascade candidates (candidate grain; read-only).

    ``total_shipments`` enables the candidate rate; without it the rate is
    None with a reason. Depth = delayed stages beyond the initial delay.
    """
    if candidates.empty:
        return {
            "candidate_count": 0,
            "shipments_with_candidates": 0,
            "candidate_rate": None,
            "candidate_rate_unavailable": (
                "no candidates" if total_shipments else "no shipments provided"
            ),
            "avg_cascade_depth": None,
            "max_cascade_depth": None,
            "depth_distribution": {},
            "avg_downstream_delay": None,
        }
    depths = pd.to_numeric(candidates["cascade_depth"], errors="coerce")
    downstream = pd.to_numeric(
        candidates["downstream_delay_duration"], errors="coerce"
    ).dropna()
    rate: Optional[float] = None
    if total_shipments:
        rate = len(candidates) / total_shipments * 100.0
    return {
        "candidate_count": int(len(candidates)),
        "shipments_with_candidates": int(candidates["shipment_id"].nunique()),
        "candidate_rate": rate,
        "avg_cascade_depth": float(depths.mean()),
        "max_cascade_depth": int(depths.max()),
        "depth_distribution": {
            str(k): int(v) for k, v in depths.value_counts(sort=False).sort_index().items()
        },
        "avg_downstream_delay": float(downstream.mean()) if not downstream.empty else None,
    }


def cascade_by_route(
    candidates: pd.DataFrame,
    shipments_per_route: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Aggregate candidates by initial route (factual metrics, no scores)."""
    if candidates.empty:
        return pd.DataFrame(
            columns=["route", "candidates", "shipments", "candidate_rate",
                     "avg_cascade_depth", "avg_downstream_delay"]
        )
    rows: list[dict[str, Any]] = []
    for route, group in candidates.groupby("initial_route", sort=True, dropna=False):
        label = "unknown" if pd.isna(route) else str(route)
        shipments = int(group["shipment_id"].nunique())
        rate: Optional[float] = None
        if shipments_per_route is not None and label in shipments_per_route:
            total = shipments_per_route[label]
            rate = len(group) / total * 100.0 if total else None
        downstream = pd.to_numeric(
            group["downstream_delay_duration"], errors="coerce"
        ).dropna()
        rows.append(
            {
                "route": label,
                "candidates": int(len(group)),
                "shipments": shipments,
                "candidate_rate": rate,
                "avg_cascade_depth": float(
                    pd.to_numeric(group["cascade_depth"]).mean()
                ),
                "avg_downstream_delay": (
                    float(downstream.mean()) if not downstream.empty else None
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["candidates", "route"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)


def cascade_by_warehouse(
    candidates: pd.DataFrame,
    shipments_per_warehouse: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Aggregate candidates by initial warehouse (patterns, not causes)."""
    if candidates.empty:
        return pd.DataFrame(
            columns=["warehouse", "candidates", "shipments", "candidate_rate",
                     "avg_downstream_delay"]
        )
    rows: list[dict[str, Any]] = []
    for warehouse, group in candidates.groupby(
        "initial_warehouse", sort=True, dropna=False
    ):
        label = "unknown" if pd.isna(warehouse) else str(warehouse)
        shipments = int(group["shipment_id"].nunique())
        rate: Optional[float] = None
        if shipments_per_warehouse is not None and label in shipments_per_warehouse:
            total = shipments_per_warehouse[label]
            rate = len(group) / total * 100.0 if total else None
        downstream = pd.to_numeric(
            group["downstream_delay_duration"], errors="coerce"
        ).dropna()
        rows.append(
            {
                "warehouse": label,
                "candidates": shipments,
                "shipments": shipments,
                "candidate_rate": rate,
                "avg_downstream_delay": (
                    float(downstream.mean()) if not downstream.empty else None
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["candidates", "warehouse"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)


def root_cause_signals(candidates: pd.DataFrame) -> pd.DataFrame:
    """Count stage-signal presence across candidates (read-only).

    Answers "what operational events commonly appear before downstream
    delay": for each stage label, the number (and share) of candidate
    shipments whose journey contains it at least once. Presence-based,
    so shares never exceed 100%. Only stages actually observed appear;
    no causal claim is made.
    """
    if candidates.empty:
        return pd.DataFrame(columns=["signal", "candidates", "share_pct"])
    total = float(len(candidates))
    counts: dict[str, int] = {}
    for stages in candidates["stages"]:
        for stage in set(stages or []):
            counts[str(stage)] = counts.get(str(stage), 0) + 1
    result = pd.DataFrame(
        {
            "signal": list(counts.keys()),
            "candidates": list(counts.values()),
        }
    )
    result["share_pct"] = result["candidates"] / total * 100.0
    return result.sort_values(
        ["candidates", "signal"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)


def save_cascade_candidates(
    candidates: pd.DataFrame,
    output_path: PathLike = DEFAULT_CASCADE_OUTPUT,
) -> Path:
    """Write cascade candidates to ``data/processed/`` (creates parents).

    The ``stages`` list column is serialized as ``>``-joined text so the
    CSV stays consumable. Raises ValueError on an empty frame.
    """
    if candidates.empty:
        raise ValueError("Refusing to save an empty cascade-candidates table.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    export = candidates.copy(deep=True)
    export["stages"] = export["stages"].map(
        lambda stages: ">".join(str(s) for s in (stages or []))
    )
    for column in ("initial_delay_time", "downstream_event_time", "final_event_time"):
        if column in export.columns:
            export[column] = pd.to_datetime(
                export[column], errors="coerce", utc=True
            ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    export.to_csv(output, index=False)
    return output
