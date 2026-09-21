"""Tests for analysis/route_analysis.py (synthetic frames only)."""

import pandas as pd
import pytest

from _analytics_fixtures import shipments_100_20
from analysis.route_analysis import route_metrics, route_trends, top_delayed_routes


def test_route_metrics_aggregation_correctness() -> None:
    df = shipments_100_20()
    metrics = route_metrics(df).set_index("route")

    assert metrics.loc["R1", "shipments"] == 50
    assert metrics.loc["R2", "shipments"] == 50
    assert metrics.loc["R1", "delayed_shipments"] == 15
    assert metrics.loc["R2", "delayed_shipments"] == 5
    assert metrics.loc["R1", "delay_rate"] == pytest.approx(30.0)
    assert metrics.loc["R2", "delay_rate"] == pytest.approx(10.0)
    # Highest delay rate first.
    assert route_metrics(df).iloc[0]["route"] == "R1"


def test_route_average_delay_matches_manual() -> None:
    df = shipments_100_20()
    metrics = route_metrics(df).set_index("route")

    r1_delayed = pd.to_numeric(df.loc[df["route_id"] == "R1", "delay_duration"])
    r1_delayed = r1_delayed[r1_delayed > 0]
    assert metrics.loc["R1", "avg_delay"] == pytest.approx(float(r1_delayed.mean()))
    assert metrics.loc["R1", "median_delay"] == pytest.approx(float(r1_delayed.median()))
    assert metrics.loc["R1", "total_delay"] == pytest.approx(float(r1_delayed.sum()))


def test_top_delayed_routes_order_and_validation() -> None:
    metrics = route_metrics(shipments_100_20())
    top = top_delayed_routes(metrics, n=1)

    assert len(top) == 1
    assert top.iloc[0]["route"] == "R1"
    with pytest.raises(ValueError, match="n > 0"):
        top_delayed_routes(metrics, n=0)
    with pytest.raises(ValueError, match="delay_rate"):
        top_delayed_routes(pd.DataFrame({"a": [1]}))


def test_missing_route_column_raises_actionable_error() -> None:
    df = pd.DataFrame({"shipment_id": ["S1"], "delay_duration": [10.0]})
    with pytest.raises(ValueError, match="No route column"):
        route_metrics(df)


def test_route_metrics_without_duration_has_none_stats() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", "S2"],
            "route_id": ["R1", "R1"],
            "status": ["delayed", "on-time"],
        }
    )
    metrics = route_metrics(df)

    assert metrics.iloc[0]["delay_rate"] == pytest.approx(50.0)
    assert metrics.iloc[0]["avg_delay"] is None


def test_route_trends_counts_and_missing_timestamps() -> None:
    df = shipments_100_20()
    trends = route_trends(df, freq="D")

    assert set(trends.columns) == {"route", "period", "records", "shipments"}
    assert trends["records"].sum() == 100
    assert trends["shipments"].sum() == 100

    no_time = pd.DataFrame({"shipment_id": ["S1"], "route_id": ["R1"]})
    with pytest.raises(ValueError, match="No timestamp column"):
        route_trends(no_time)


def test_route_analysis_does_not_modify_input() -> None:
    df = shipments_100_20()
    before = df.copy(deep=True)

    route_metrics(df)
    route_trends(df)

    pd.testing.assert_frame_equal(df, before)


def test_route_metrics_deterministic() -> None:
    df = shipments_100_20()
    pd.testing.assert_frame_equal(route_metrics(df), route_metrics(df))
