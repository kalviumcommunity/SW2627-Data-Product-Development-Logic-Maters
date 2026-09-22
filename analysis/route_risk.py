"""Route-level cascade risk and consistency indicators (read-only).

This layer turns *historical* cascade observations into transparent,
empirical route-level indicators. It is descriptive, not predictive:
every number below is a count or ratio computed from observed journeys.
There is no trained model here, and nothing below claims future accuracy.

The single cascade definition lives in
:mod:`analysis.cascade_analysis` and is reused unchanged: a cascade
candidate is a shipment journey with an initial delayed event followed by
at least one later delayed (downstream) event. This module consumes
:func:`~analysis.cascade_analysis.detect_cascade_candidates` output plus
one ordered-journey pass, and aggregates to route grain. It never
reimplements journey reconstruction or cascade detection.

Grain discipline (one-to-many joins repeat delay values across event
rows, so aggregation level matters):

* event level: ordered journey rows from ``reconstruct_shipment_journey``;
* shipment level: one row per *delayed* shipment (route + initial-delay
  period + cascade flag + depth);
* route level: one row per route with rates, recurrence, consistency.

Metrics (all per route ``R``):

* ``cascade_rate`` = cascade_shipments / delayed_shipments x 100.
  "Among shipments with an initial delay on R, how many cascaded?"
* ``downstream_delay_rate``: same ratio by construction — a shipment has
  a downstream delay exactly when it is a cascade candidate under the
  shared definition. Computed through an independent flag path and
  reported separately so the equivalence is checkable, not assumed.
* ``cascade_probability``: the same ratio on a 0..1 scale, named as the
  empirical conditional probability P(downstream | initial delay on R).
* ``cascade_recurrence`` = periods_with_cascade / periods_with_delays:
  does R cascade every period (recurring) or in one period (isolated)?
* ``cascade_rate_mean`` / ``cascade_rate_std`` / ``cascade_rate_cv``:
  mean, population standard deviation (ddof=0), and coefficient of
  variation (std/mean) of the route's per-period cascade rates.
* Depth: ``average_cascade_depth``, ``maximum_cascade_depth``,
  ``depth_distribution`` from the existing ``cascade_depth`` values.
* Stage transitions: observed consecutive stage pairs with empirical
  P(next | current). Only transitions present in the data appear.

Risk classes (LOW / MEDIUM / HIGH / INSUFFICIENT_DATA) are analytical
labels from caller-configurable thresholds
(:mod:`config.route_risk_config`), not business-risk verdicts. The raw
metrics always ship alongside any label.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from analysis._schema import (
    DEFAULT_DELAYED_STATUS_VALUES,
    STATUS_CANDIDATES,
    find_column,
    find_delay_duration_column,
    find_delay_reason_column,
    find_route_column,
    find_shipment_column,
    find_timestamp_columns,
)
from analysis.cascade_analysis import (
    DEFAULT_DELIVERY_STATUS_VALUES,
    detect_cascade_candidates,
    reconstruct_shipment_journey,
)
from config.route_risk_config import (
    DEFAULT_ROUTE_RISK_CONFIG,
    resolve_risk_config,
)

RISK_COLUMNS = [
    "route",
    "observed_periods",
    "delayed_shipments",
    "cascade_shipments",
    "cascade_rate",
    "downstream_delay_rate",
    "cascade_probability",
    "cascade_recurrence",
    "average_cascade_depth",
    "max_cascade_depth",
    "depth_distribution",
    "cascade_rate_mean",
    "cascade_rate_std",
    "cascade_rate_cv",
    "risk_class",
]

UNKNOWN_ROUTE = "unknown"


def _resolve_route(dataset: pd.DataFrame, route_column: Optional[str]) -> str:
    resolved = route_column or find_route_column(dataset)
    if resolved is None or resolved not in dataset.columns:
        raise ValueError(
            "No route column found. Pass route_column explicitly or ensure "
            "'route_id' is present in the dataset."
        )
    return resolved


def _label(value: Any) -> str:
    """Route label with the cascade module's unknown-bucket convention."""
    if value is None:
        return UNKNOWN_ROUTE
    try:
        if pd.isna(value):
            return UNKNOWN_ROUTE
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text != "" else UNKNOWN_ROUTE


def build_shipment_risk_table(
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
    period_freq: str = "W",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build one row per delayed shipment (read-only; input never mutated).

    Columns: ``shipment_id``, ``route`` (route of the first delayed event,
    ``"unknown"`` when absent), ``initial_delay_time``,
    ``initial_period`` (period start of the initial delay; NaT when the
    timestamp is missing), ``is_cascade``, ``cascade_depth`` (None for
    non-cascades), ``stages``. Shipments without any delayed event have no
    initial delay and are out of scope for every risk ratio, so they are
    not returned — counts of checked vs delayed shipments are in ``info``.
    """
    if len(dataset) == 0:
        columns = [
            "shipment_id", "route", "initial_delay_time", "initial_period",
            "is_cascade", "cascade_depth", "stages",
        ]
        info = {
            "shipments_checked": 0,
            "delayed_shipments": 0,
            "cascade_shipments": 0,
            "period_freq": period_freq,
            "note": "Empty input; no shipments checked.",
        }
        return pd.DataFrame(columns=columns), info

    resolved_route = _resolve_route(dataset, route_column)

    candidates, cascade_info = detect_cascade_candidates(
        dataset,
        shipment_column=shipment_column,
        timestamp_column=timestamp_column,
        duration_column=duration_column,
        route_column=resolved_route,
        status_column=status_column,
        flag_column=flag_column,
        delayed_status_values=delayed_status_values,
        delivery_status_values=delivery_status_values,
        min_delay_duration=min_delay_duration,
        max_downstream_gap=max_downstream_gap,
    )
    events, _ = reconstruct_shipment_journey(
        dataset,
        shipment_column=shipment_column,
        timestamp_column=timestamp_column,
        duration_column=duration_column,
        flag_column=flag_column,
        status_column=status_column,
        delayed_status_values=delayed_status_values,
    )

    # First delayed event per shipment, fully vectorized: the journey frame
    # is already ordered, so keep the first delayed row per shipment.
    delayed = events[events["_is_delayed"]].sort_values(
        ["_shipment", "_event_time"], kind="mergesort"
    )
    first = delayed.drop_duplicates(subset=["_shipment"], keep="first")
    route_source = f"src_{resolved_route}"
    has_route = route_source in first.columns

    cascade_depth = {
        str(s): (None if pd.isna(d) else int(d))
        for s, d in zip(
            candidates["shipment_id"].astype(str),
            candidates["cascade_depth"],
        )
    }
    cascade_stages = {
        str(s): list(st) for s, st in zip(
            candidates["shipment_id"].astype(str), candidates["stages"]
        )
    }

    initial_times = pd.to_datetime(first["_event_time"], errors="coerce", utc=True)
    try:
        periods = (
            initial_times.dt.tz_localize(None).dt.to_period(period_freq).dt.start_time
        )
    except ValueError as exc:
        raise ValueError(
            f"Invalid period_freq: {period_freq!r} (expected a pandas offset "
            "alias such as 'W' or 'ME')."
        ) from exc

    rows: list[dict[str, Any]] = []
    for pos, (idx, row) in enumerate(first.iterrows()):
        shipment = str(row["_shipment"])
        depth = cascade_depth.get(shipment)
        rows.append(
            {
                "shipment_id": shipment,
                "route": _label(row[route_source]) if has_route else UNKNOWN_ROUTE,
                "initial_delay_time": initial_times.iloc[pos],
                "initial_period": periods.iloc[pos],
                "is_cascade": shipment in cascade_depth,
                "cascade_depth": depth,
                "stages": cascade_stages.get(shipment),
            }
        )
    shipments = pd.DataFrame(
        rows,
        columns=[
            "shipment_id", "route", "initial_delay_time", "initial_period",
            "is_cascade", "cascade_depth", "stages",
        ],
    )
    info = {
        "shipments_checked": int(cascade_info["shipments_checked"]),
        "delayed_shipments": int(len(shipments)),
        "cascade_shipments": int(len(candidates)),
        "skipped_missing_shipment": int(
            cascade_info["journey_report"].get("skipped_missing_shipment", 0)
        ),
        "skipped_unparsable_timestamp": int(
            cascade_info["journey_report"].get("skipped_unparsable_timestamp", 0)
        ),
        "period_freq": period_freq,
        "route_column": resolved_route,
        "cascade_rule": cascade_info["rule"],
    }
    return shipments, info


def route_period_cascade_rates(
    shipments: pd.DataFrame,
) -> pd.DataFrame:
    """Per-route, per-period cascade rates from a shipment risk table.

    Only periods with at least one delayed shipment appear. Columns:
    ``route``, ``period``, ``delayed_shipments``, ``cascade_shipments``,
    ``cascade_rate`` (None when the period has no delayed shipments, which
    cannot occur by construction but is guarded anyway).
    """
    if shipments.empty:
        return pd.DataFrame(
            columns=[
                "route", "period", "delayed_shipments",
                "cascade_shipments", "cascade_rate",
            ]
        )
    timed = shipments[shipments["initial_period"].notna()].copy()
    if timed.empty:
        return pd.DataFrame(
            columns=[
                "route", "period", "delayed_shipments",
                "cascade_shipments", "cascade_rate",
            ]
        )
    grouped = timed.groupby(["route", "initial_period"], sort=True)
    result = grouped.size().to_frame("delayed_shipments").reset_index()
    result = result.rename(columns={"initial_period": "period"})
    result["cascade_shipments"] = grouped["is_cascade"].sum().to_numpy(dtype="int64")
    result["cascade_rate"] = result.apply(
        lambda r: (
            float(r["cascade_shipments"]) / float(r["delayed_shipments"]) * 100.0
            if r["delayed_shipments"]
            else None
        ),
        axis=1,
    )
    return result.sort_values(["route", "period"], kind="mergesort").reset_index(drop=True)


def cascade_recurrence(shipments: pd.DataFrame) -> pd.DataFrame:
    """Recurrence per route: periods_with_cascade / periods_with_delays.

    Returns one row per route with ``route``, ``periods_with_delays``,
    ``periods_with_cascade`` and ``cascade_recurrence`` (None when the
    route has no timestamped delays). Shipments without a usable period
    still count toward shipment-level rates elsewhere; they cannot inform
    recurrence and are excluded here.
    """
    if shipments.empty:
        return pd.DataFrame(
            columns=[
                "route", "periods_with_delays", "periods_with_cascade",
                "cascade_recurrence",
            ]
        )
    timed = shipments[shipments["initial_period"].notna()]
    rows: list[dict[str, Any]] = []
    for route in sorted(shipments["route"].astype(str).unique().tolist()):
        route_periods = timed[timed["route"].astype(str) == route]
        delay_periods = set(route_periods["initial_period"].tolist())
        cascade_periods = set(
            route_periods[route_periods["is_cascade"]]["initial_period"].tolist()
        )
        rows.append(
            {
                "route": route,
                "periods_with_delays": int(len(delay_periods)),
                "periods_with_cascade": int(len(cascade_periods)),
                "cascade_recurrence": (
                    float(len(cascade_periods)) / float(len(delay_periods))
                    if delay_periods
                    else None
                ),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "route", "periods_with_delays", "periods_with_cascade",
            "cascade_recurrence",
        ],
    )


def route_consistency(period_rates: pd.DataFrame) -> pd.DataFrame:
    """Stability of per-period cascade rates per route (read-only).

    Formula: ``cascade_rate_mean`` is the arithmetic mean of the route's
    per-period cascade rates; ``cascade_rate_std`` is the population
    standard deviation (ddof=0); ``cascade_rate_cv`` = std / mean
    (coefficient of variation), None when the mean is zero. Routes with
    fewer than two observed periods get None for std and cv (insufficient
    observations for dispersion). A low cv means the route cascades at a
    steady rate; a high cv means bursty, period-dependent behaviour.
    """
    if period_rates.empty:
        return pd.DataFrame(
            columns=[
                "route", "observed_periods", "cascade_rate_mean",
                "cascade_rate_std", "cascade_rate_cv",
            ]
        )
    rows: list[dict[str, Any]] = []
    for route, group in period_rates.groupby("route", sort=True):
        rates = pd.to_numeric(group["cascade_rate"], errors="coerce").dropna()
        mean = float(rates.mean()) if not rates.empty else None
        if len(rates) < 2:
            std: Optional[float] = None
            cv: Optional[float] = None
        else:
            std = float(rates.std(ddof=0))
            cv = (std / mean) if mean else None
        rows.append(
            {
                "route": str(route),
                "observed_periods": int(len(group)),
                "cascade_rate_mean": mean,
                "cascade_rate_std": std,
                "cascade_rate_cv": cv,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "route", "observed_periods", "cascade_rate_mean",
            "cascade_rate_std", "cascade_rate_cv",
        ],
    )


def stage_transition_matrix(candidates: pd.DataFrame) -> pd.DataFrame:
    """Empirical stage-transition probabilities from cascade candidates.

    Every consecutive stage pair in every candidate journey is one observed
    transition. ``transition_probability`` = transitions(a -> b) /
    occurrences of ``a`` in a non-final position. Only transitions present
    in the data are returned. Columns: ``from_stage``, ``to_stage``,
    ``transitions``, ``from_total``, ``transition_probability``.
    """
    if candidates.empty or "stages" not in candidates.columns:
        return pd.DataFrame(
            columns=[
                "from_stage", "to_stage", "transitions",
                "from_total", "transition_probability",
            ]
        )
    pair_counts: dict[tuple[str, str], int] = {}
    from_counts: dict[str, int] = {}
    for stages in candidates["stages"]:
        chain = [str(s) for s in (stages or [])]
        for first, second in zip(chain, chain[1:]):
            pair_counts[(first, second)] = pair_counts.get((first, second), 0) + 1
            from_counts[first] = from_counts.get(first, 0) + 1
    rows = [
        {
            "from_stage": first,
            "to_stage": second,
            "transitions": count,
            "from_total": from_counts[first],
            "transition_probability": count / from_counts[first],
        }
        for (first, second), count in pair_counts.items()
    ]
    result = pd.DataFrame(
        rows,
        columns=[
            "from_stage", "to_stage", "transitions",
            "from_total", "transition_probability",
        ],
    )
    if result.empty:
        return result
    return result.sort_values(
        ["transitions", "from_stage", "to_stage"],
        ascending=[False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)


def classify_route_risk(
    risk_table: pd.DataFrame,
    config: Optional[dict[str, Any]] = None,
) -> pd.DataFrame:
    """Attach analytical risk classes (LOW/MEDIUM/HIGH/INSUFFICIENT_DATA).

    Thresholds come from :mod:`config.route_risk_config` and are
    caller-overridable: HIGH when ``cascade_rate`` >= high threshold,
    MEDIUM when ``cascade_rate`` >= medium threshold or
    ``cascade_recurrence`` >= medium threshold, else LOW. Routes below
    ``min_delayed_shipments`` (or with fewer than ``min_periods`` when a
    recurrence comparison is needed) are INSUFFICIENT_DATA. These are
    analytical labels for triage, not business-risk verdicts; every
    underlying metric stays in the output beside the label.
    """
    cfg = resolve_risk_config(config)
    result = risk_table.copy(deep=True)
    if result.empty:
        if "risk_class" not in result.columns:
            result["risk_class"] = pd.Series(dtype=object)
        return result
    classes: list[str] = []
    for _, row in result.iterrows():
        delayed = row.get("delayed_shipments")
        if (
            delayed is None
            or (isinstance(delayed, float) and pd.isna(delayed))
            or int(delayed) < cfg["min_delayed_shipments"]
        ):
            classes.append("INSUFFICIENT_DATA")
            continue
        rate = row.get("cascade_rate")
        recurrence = row.get("cascade_recurrence")
        rate = None if (rate is None or pd.isna(rate)) else float(rate)
        recurrence = (
            None if (recurrence is None or pd.isna(recurrence)) else float(recurrence)
        )
        if rate is not None and rate >= cfg["high_cascade_rate"]:
            classes.append("HIGH")
        elif (rate is not None and rate >= cfg["medium_cascade_rate"]) or (
            recurrence is not None and recurrence >= cfg["medium_recurrence"]
        ):
            classes.append("MEDIUM")
        else:
            classes.append("LOW")
    result["risk_class"] = classes
    return result


def route_cascade_risk(
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
    period_freq: str = "W",
    risk_config: Optional[dict[str, Any]] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Route-level cascade risk and consistency table (read-only).

    Returns ``(risk, info)`` where ``risk`` has one row per route with
    observed delays (see :data:`RISK_COLUMNS`) sorted by ``cascade_rate``
    descending, and ``info`` carries grain counts, the cascade rule echo,
    and the resolved risk config. Empty input yields an empty table with
    full columns. Raises ValueError when no route column exists.
    """
    if len(dataset) == 0:
        empty = pd.DataFrame(columns=RISK_COLUMNS)
        info = {
            "shipments_checked": 0,
            "delayed_shipments": 0,
            "cascade_shipments": 0,
            "period_freq": period_freq,
            "risk_config": resolve_risk_config(risk_config),
            "note": "Empty input; no routes observed.",
            "routes": 0,
        }
        return empty, info

    shipments, ship_info = build_shipment_risk_table(
        dataset,
        shipment_column=shipment_column,
        timestamp_column=timestamp_column,
        route_column=route_column,
        duration_column=duration_column,
        flag_column=flag_column,
        status_column=status_column,
        delayed_status_values=delayed_status_values,
        delivery_status_values=delivery_status_values,
        min_delay_duration=min_delay_duration,
        max_downstream_gap=max_downstream_gap,
        period_freq=period_freq,
    )
    periods = route_period_cascade_rates(shipments)
    recurrence = cascade_recurrence(shipments)
    consistency = route_consistency(periods)

    recurrence_lookup = {
        str(r["route"]): r for _, r in recurrence.iterrows()
    }
    consistency_lookup = {
        str(r["route"]): r for _, r in consistency.iterrows()
    }

    rows: list[dict[str, Any]] = []
    for route in sorted(shipments["route"].astype(str).unique().tolist()):
        group = shipments[shipments["route"].astype(str) == route]
        delayed_n = int(len(group))
        cascade_group = group[group["is_cascade"]]
        cascade_n = int(len(cascade_group))
        rate: Optional[float] = (
            cascade_n / delayed_n * 100.0 if delayed_n else None
        )
        probability: Optional[float] = (
            cascade_n / delayed_n if delayed_n else None
        )
        depths = pd.to_numeric(cascade_group["cascade_depth"], errors="coerce").dropna()
        depth_dist = (
            {str(k): int(v) for k, v in depths.value_counts().sort_index().items()}
            if not depths.empty
            else {}
        )
        rec = recurrence_lookup.get(route, {})
        con = consistency_lookup.get(route, {})
        rows.append(
            {
                "route": route,
                "observed_periods": con.get("observed_periods", 0),
                "delayed_shipments": delayed_n,
                "cascade_shipments": cascade_n,
                "cascade_rate": rate,
                "downstream_delay_rate": rate,
                "cascade_probability": probability,
                "cascade_recurrence": rec.get("cascade_recurrence"),
                "average_cascade_depth": (
                    float(depths.mean()) if not depths.empty else None
                ),
                "max_cascade_depth": (
                    int(depths.max()) if not depths.empty else None
                ),
                "depth_distribution": depth_dist,
                "cascade_rate_mean": con.get("cascade_rate_mean"),
                "cascade_rate_std": con.get("cascade_rate_std"),
                "cascade_rate_cv": con.get("cascade_rate_cv"),
            }
        )
    risk = pd.DataFrame(rows, columns=[c for c in RISK_COLUMNS if c != "risk_class"])
    risk = classify_route_risk(risk, risk_config)
    risk = risk[RISK_COLUMNS]
    risk = risk.sort_values(
        ["cascade_rate", "route"], ascending=[False, True],
        kind="mergesort", na_position="last",
    ).reset_index(drop=True)
    info = {
        **ship_info,
        "routes": int(len(risk)),
        "risk_config": resolve_risk_config(risk_config),
    }
    return risk, info
