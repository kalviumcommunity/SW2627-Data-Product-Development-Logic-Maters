"""Tests for analysis/warehouse_analysis.py (synthetic frames only)."""

import pandas as pd
import pytest

from _analytics_fixtures import shipments_100_20
from analysis.warehouse_analysis import (
    top_delayed_warehouses,
    transfer_activity,
    warehouse_metrics,
    warehouse_trends,
)


def test_warehouse_metrics_aggregation_correctness() -> None:
    df = shipments_100_20()
    metrics = warehouse_metrics(df).set_index("warehouse")

    # W1 holds odd shipments: 8 delayed of S001-S015 + 3 of S051-S055 = 11.
    # W2 holds even shipments: 7 + 2 = 9 delayed of 50.
    assert metrics.loc["W1", "shipments"] == 50
    assert metrics.loc["W2", "shipments"] == 50
    assert metrics.loc["W1", "delayed_shipments"] == 11
    assert metrics.loc["W2", "delayed_shipments"] == 9
    assert metrics.loc["W1", "delay_rate"] == pytest.approx(22.0)


def test_top_delayed_warehouses_and_validation() -> None:
    metrics = warehouse_metrics(shipments_100_20())
    top = top_delayed_warehouses(metrics, n=2)

    assert len(top) == 2
    with pytest.raises(ValueError, match="n > 0"):
        top_delayed_warehouses(metrics, n=0)
    with pytest.raises(ValueError, match="delay_rate"):
        top_delayed_warehouses(pd.DataFrame({"a": [1]}))


def test_missing_warehouse_column_raises() -> None:
    df = pd.DataFrame({"shipment_id": ["S1"], "delay_duration": [5.0]})
    with pytest.raises(ValueError, match="No warehouse column"):
        warehouse_metrics(df)
    with pytest.raises(ValueError, match="not found"):
        warehouse_metrics(df, warehouse_column="nope")


def test_explicit_transfer_endpoint_column() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", "S2", "S3"],
            "source_warehouse": ["WA", "WA", "WB"],
            "delay_duration": [10.0, 0.0, 20.0],
        }
    )
    metrics = warehouse_metrics(df, warehouse_column="source_warehouse").set_index("warehouse")

    assert metrics.loc["WA", "shipments"] == 2
    assert metrics.loc["WA", "delay_rate"] == pytest.approx(50.0)
    assert metrics.loc["WB", "delay_rate"] == pytest.approx(100.0)


def test_transfer_activity_counts_and_unavailable() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", "S2", "S3"],
            "source_warehouse": ["WA", "WA", "WB"],
            "destination_warehouse": ["WB", "WC", "WC"],
        }
    )
    activity = transfer_activity(df)

    assert activity["source_warehouse"]["available"] is True
    source = activity["source_warehouse"]["activity"].set_index("warehouse")
    assert source.loc["WA", "transfers"] == 2
    dest = activity["destination_warehouse"]["activity"].set_index("warehouse")
    assert dest.loc["WC", "transfers"] == 2

    missing = transfer_activity(pd.DataFrame({"shipment_id": ["S1"]}))
    assert missing["source_warehouse"]["available"] is False


def test_warehouse_trends_counts() -> None:
    trends = warehouse_trends(shipments_100_20(), freq="D")

    assert set(trends.columns) == {"warehouse", "period", "records", "shipments"}
    assert trends["records"].sum() == 100


def test_warehouse_analysis_does_not_modify_input() -> None:
    df = shipments_100_20()
    before = df.copy(deep=True)

    warehouse_metrics(df)
    warehouse_trends(df)
    transfer_activity(df)

    pd.testing.assert_frame_equal(df, before)
