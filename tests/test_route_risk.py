"""Tests for analysis/route_risk.py (synthetic journeys only)."""

import pandas as pd
import pytest

from analysis.route_risk import (
    RISK_COLUMNS,
    build_shipment_risk_table,
    cascade_recurrence,
    classify_route_risk,
    route_cascade_risk,
    route_consistency,
    route_period_cascade_rates,
    stage_transition_matrix,
)
from config.route_risk_config import resolve_risk_config


def risk_frame(rows: list[dict]) -> pd.DataFrame:
    """Journey frame with canonical columns for risk tests."""
    base = {
        "route_id": "R1",
        "warehouse_id": "W1",
        "status": None,
        "delay_reason": None,
        "delay_duration": 0.0,
    }
    return pd.DataFrame([{**base, **row} for row in rows])


def late(shipment: str, route: str, day: str, duration: float,
         second_day: str | None = None, second_duration: float = 0.0) -> list[dict]:
    """One shipment: initial delay plus an optional downstream delay."""
    rows = [{
        "shipment_id": shipment, "route_id": route,
        "timestamp": f"2024-01-{day} 08:00", "delay_duration": duration,
    }]
    if second_day is not None:
        rows.append({
            "shipment_id": shipment, "route_id": route,
            "timestamp": f"2024-01-{second_day} 09:00",
            "delay_duration": second_duration,
        })
    return rows


def test_route_with_no_cascades() -> None:
    df = risk_frame(
        late("A", "R1", "01", 10.0) + late("B", "R1", "02", 20.0)
    )
    risk, info = route_cascade_risk(df)
    assert len(risk) == 1
    row = risk.iloc[0]
    assert row["delayed_shipments"] == 2
    assert row["cascade_shipments"] == 0
    assert row["cascade_rate"] == pytest.approx(0.0)
    assert row["downstream_delay_rate"] == pytest.approx(0.0)
    assert row["cascade_probability"] == pytest.approx(0.0)
    assert row["cascade_recurrence"] == pytest.approx(0.0)
    assert row["average_cascade_depth"] is None
    assert row["max_cascade_depth"] is None
    assert info["cascade_shipments"] == 0


def test_route_with_one_cascade() -> None:
    df = risk_frame(late("A", "R1", "01", 10.0, "02", 30.0))
    risk, _ = route_cascade_risk(df)
    row = risk.iloc[0]
    assert row["delayed_shipments"] == 1
    assert row["cascade_shipments"] == 1
    assert row["cascade_rate"] == pytest.approx(100.0)
    assert row["cascade_probability"] == pytest.approx(1.0)
    assert row["cascade_recurrence"] == pytest.approx(1.0)
    assert row["average_cascade_depth"] == pytest.approx(1.0)
    assert row["max_cascade_depth"] == 1


def test_route_with_repeated_cascades() -> None:
    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)
        + late("B", "R1", "08", 15.0, "09", 25.0)
        + late("C", "R1", "15", 12.0, "16", 22.0)
    )
    risk, _ = route_cascade_risk(df)
    row = risk.iloc[0]
    assert row["cascade_shipments"] == 3
    assert row["observed_periods"] == 3
    assert row["cascade_recurrence"] == pytest.approx(1.0)
    assert row["cascade_rate_mean"] == pytest.approx(100.0)
    assert row["cascade_rate_std"] == pytest.approx(0.0)
    assert row["cascade_rate_cv"] == pytest.approx(0.0)


def test_multiple_routes_sorted_and_independent() -> None:
    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)
        + late("B", "R1", "03", 10.0)
        + late("C", "R2", "01", 10.0)
        + late("D", "R2", "02", 10.0)
    )
    risk, info = route_cascade_risk(df)
    assert info["routes"] == 2
    by_route = risk.set_index("route")
    assert by_route.loc["R1", "cascade_rate"] == pytest.approx(50.0)
    assert by_route.loc["R2", "cascade_rate"] == pytest.approx(0.0)
    # Sorted by cascade rate descending.
    assert risk["route"].tolist() == ["R1", "R2"]
    assert list(risk.columns) == RISK_COLUMNS


def test_multiple_time_periods_partial_recurrence() -> None:
    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)   # week 1: cascade
        + late("B", "R1", "08", 10.0)              # week 2: delay only
        + late("C", "R1", "15", 10.0)              # week 3: delay only
    )
    risk, _ = route_cascade_risk(df)
    row = risk.iloc[0]
    assert row["observed_periods"] == 3
    assert row["cascade_recurrence"] == pytest.approx(1 / 3)
    # Period rates: 100, 0, 0 -> mean 100/3, population std.
    assert row["cascade_rate_mean"] == pytest.approx(100 / 3)
    assert row["cascade_rate_std"] == pytest.approx(
        pd.Series([100.0, 0.0, 0.0]).std(ddof=0)
    )


def test_zero_delayed_shipments_yields_empty_table() -> None:
    df = risk_frame([
        {"shipment_id": "A", "timestamp": "2024-01-01 08:00"},
        {"shipment_id": "B", "timestamp": "2024-01-02 08:00"},
    ])
    risk, info = route_cascade_risk(df)
    assert risk.empty
    assert list(risk.columns) == RISK_COLUMNS
    assert info["delayed_shipments"] == 0
    assert info["cascade_shipments"] == 0


def test_missing_timestamps_keep_rates_but_skip_recurrence() -> None:
    # Shipment B has no usable timestamp: journey reconstruction skips it
    # (documented skip count), so only timestamped shipments inform risk.
    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)
        + [{"shipment_id": "B", "route_id": "R1",
            "timestamp": None, "delay_duration": 10.0}]
    )
    risk, info = route_cascade_risk(df)
    assert info["skipped_unparsable_timestamp"] == 1
    row = risk.iloc[0]
    assert row["delayed_shipments"] == 1
    assert row["cascade_shipments"] == 1
    assert row["cascade_rate"] == pytest.approx(100.0)
    assert row["observed_periods"] == 1
    assert row["cascade_recurrence"] == pytest.approx(1.0)
    assert row["cascade_rate_std"] is None
    assert row["cascade_rate_cv"] is None


def test_missing_route_identifiers_raise() -> None:
    df = pd.DataFrame({
        "shipment_id": ["A", "A"],
        "timestamp": ["2024-01-01 08:00", "2024-01-02 08:00"],
        "delay_duration": [10.0, 20.0],
    })
    with pytest.raises(ValueError, match="No route column"):
        route_cascade_risk(df)


def test_single_period_route_has_no_dispersion() -> None:
    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)
        + late("B", "R1", "03", 10.0)
    )
    risk, _ = route_cascade_risk(df)
    row = risk.iloc[0]
    assert row["observed_periods"] == 1
    assert row["cascade_rate_mean"] == pytest.approx(50.0)
    assert row["cascade_rate_std"] is None
    assert row["cascade_rate_cv"] is None


def test_cascade_depth_calculation() -> None:
    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)  # depth 1
        + [
            {"shipment_id": "B", "route_id": "R1",
             "timestamp": "2024-01-03 08:00", "delay_duration": 10.0},
            {"shipment_id": "B", "route_id": "R1",
             "timestamp": "2024-01-04 08:00", "delay_duration": 20.0},
            {"shipment_id": "B", "route_id": "R1",
             "timestamp": "2024-01-05 08:00", "delay_duration": 30.0},
        ]  # depth 2
    )
    risk, _ = route_cascade_risk(df)
    row = risk.iloc[0]
    assert row["average_cascade_depth"] == pytest.approx(1.5)
    assert row["max_cascade_depth"] == 2
    assert row["depth_distribution"] == {"1": 1, "2": 1}


def test_stage_transition_calculation() -> None:
    from analysis.cascade_analysis import detect_cascade_candidates

    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)
        + late("B", "R1", "03", 10.0, "04", 30.0)
    )
    candidates, _ = detect_cascade_candidates(df)
    matrix = stage_transition_matrix(candidates)
    # Two identical two-stage chains: one observed transition type.
    assert len(matrix) == 1
    assert matrix.iloc[0]["transitions"] == 2
    assert matrix.iloc[0]["transition_probability"] == pytest.approx(1.0)
    assert stage_transition_matrix(candidates.iloc[0:0]).empty


def test_input_dataframe_is_not_mutated() -> None:
    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)
        + late("B", "R2", "08", 10.0)
    )
    before = df.copy(deep=True)
    route_cascade_risk(df)
    pd.testing.assert_frame_equal(df, before)


def test_correct_empirical_probability() -> None:
    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)
        + late("B", "R1", "03", 10.0)
        + late("C", "R1", "04", 10.0)
        + late("D", "R1", "05", 10.0)
    )
    risk, _ = route_cascade_risk(df)
    row = risk.iloc[0]
    # 1 cascade of 4 initial delays: P = 0.25, rate = 25.0.
    assert row["cascade_probability"] == pytest.approx(0.25)
    assert row["cascade_rate"] == pytest.approx(25.0)
    assert row["cascade_probability"] == pytest.approx(row["cascade_rate"] / 100.0)


def test_correct_recurrence_calculation() -> None:
    shipments = pd.DataFrame({
        "shipment_id": ["A", "B", "C", "D"],
        "route": ["R1"] * 4,
        "initial_delay_time": pd.to_datetime(
            ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"], utc=True
        ),
        "initial_period": pd.to_datetime(
            ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"], utc=True
        ),
        "is_cascade": [True, False, True, False],
        "cascade_depth": [1.0, None, 2.0, None],
        "stages": [["initial_delay", "downstream_delay"], None,
                   ["initial_delay", "downstream_delay"], None],
    })
    recurrence = cascade_recurrence(shipments)
    assert recurrence.iloc[0]["periods_with_delays"] == 4
    assert recurrence.iloc[0]["periods_with_cascade"] == 2
    assert recurrence.iloc[0]["cascade_recurrence"] == pytest.approx(0.5)


def test_correct_route_level_aggregation() -> None:
    # Shipment A has three delayed EVENT rows but is one shipment.
    df = risk_frame([
        {"shipment_id": "A", "route_id": "R1",
         "timestamp": "2024-01-01 08:00", "delay_duration": 10.0},
        {"shipment_id": "A", "route_id": "R1",
         "timestamp": "2024-01-02 08:00", "delay_duration": 20.0},
        {"shipment_id": "A", "route_id": "R1",
         "timestamp": "2024-01-03 08:00", "delay_duration": 30.0},
        {"shipment_id": "B", "route_id": "R1",
         "timestamp": "2024-01-04 08:00", "delay_duration": 5.0},
    ])
    shipments, _ = build_shipment_risk_table(df)
    assert len(shipments) == 2  # shipment grain, not event grain
    risk, _ = route_cascade_risk(df)
    assert risk.iloc[0]["delayed_shipments"] == 2
    assert risk.iloc[0]["cascade_shipments"] == 1


def test_risk_classification_and_config() -> None:
    df = risk_frame(
        late("A", "R1", "01", 10.0, "02", 30.0)
        + late("B", "R1", "03", 10.0)
        + late("E", "R2", "01", 10.0, "02", 30.0)  # cascade, week 1
        + late("F", "R2", "08", 10.0)  # delay-only weeks below
        + late("G", "R2", "08", 10.0)
        + late("H", "R2", "15", 10.0)
        + late("C", "R3", "01", 10.0)  # no cascade anywhere
    )
    config = {"min_delayed_shipments": 1, "medium_cascade_rate": 50.0,
              "high_cascade_rate": 90.0, "medium_recurrence": 0.5,
              "min_periods": 1}
    risk, _ = route_cascade_risk(df, risk_config=config)
    by_route = risk.set_index("route")
    assert by_route.loc["R1", "risk_class"] == "MEDIUM"  # 50% in [50, 90)
    # R2: rate 25% < 50, but cascades in 1 of 3 delay weeks... below 0.5.
    assert by_route.loc["R2", "risk_class"] == "LOW"
    assert by_route.loc["R3", "risk_class"] == "LOW"
    # Recurrence-driven MEDIUM: 1 cascade in 2 delay periods (0.5).
    df2 = risk_frame(
        late("A", "R4", "01", 10.0, "02", 30.0)
        + late("B", "R4", "08", 10.0)
        + late("C", "R4", "08", 10.0)
        + late("D", "R4", "08", 10.0)
    )
    risk2, _ = route_cascade_risk(df2, risk_config=config)
    assert risk2.iloc[0]["cascade_rate"] == pytest.approx(25.0)
    assert risk2.iloc[0]["cascade_recurrence"] == pytest.approx(0.5)
    assert risk2.iloc[0]["risk_class"] == "MEDIUM"
    # Default guards mark tiny samples insufficient, never safe.
    defaulted, _ = route_cascade_risk(df)
    assert set(defaulted["risk_class"]) == {"INSUFFICIENT_DATA"}
    # Config validation.
    with pytest.raises(ValueError, match="Unknown route-risk config keys"):
        resolve_risk_config({"nope": 1})
    with pytest.raises(ValueError, match="must be <= 'high_cascade_rate'"):
        resolve_risk_config({"medium_cascade_rate": 90.0})
    assert classify_route_risk(
        pd.DataFrame(columns=RISK_COLUMNS)
    ).empty


def test_empty_input_and_period_rates() -> None:
    empty = risk_frame([]).iloc[0:0]
    risk, info = route_cascade_risk(empty)
    assert risk.empty and list(risk.columns) == RISK_COLUMNS
    assert info["routes"] == 0
    shipments, _ = build_shipment_risk_table(empty)
    assert route_period_cascade_rates(shipments).empty
    assert route_consistency(route_period_cascade_rates(shipments)).empty
    # Unknown route bucket when the route value is missing.
    df = risk_frame(late("A", "R1", "01", 10.0, "02", 30.0))
    df.loc[0, "route_id"] = None
    risk, _ = route_cascade_risk(df)
    assert risk.iloc[0]["route"] == "unknown"
