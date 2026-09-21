"""Tests for analysis/eda.py and analysis/delay_analysis.py."""

import pandas as pd
import pytest

from _analytics_fixtures import shipments_100_20
from analysis.delay_analysis import (
    available_dimensions,
    delay_by_segment,
    delay_over_time,
    delay_reason_breakdown,
    derive_time_features,
    rolling_delay_rate,
    segment_summary,
)
from analysis.eda import (
    get_dataset_summary,
    get_delay_distribution,
    get_delay_flag_summary,
    get_delay_reason_distribution,
    get_event_distribution,
    get_missingness_summary,
    get_route_distribution,
    get_time_distribution,
    get_warehouse_distribution,
)


def test_dataset_summary_counts_and_immutability() -> None:
    df = shipments_100_20()
    before = df.copy(deep=True)

    summary = get_dataset_summary(df)

    assert summary["row_count"] == 100
    assert summary["total_shipments"] == 100
    assert summary["duplicate_rows"] == 0
    pd.testing.assert_frame_equal(df, before)


def test_distributions_cover_reasons_routes_warehouses() -> None:
    df = shipments_100_20()

    reasons = get_delay_reason_distribution(df).set_index("value")
    assert reasons["count"].sum() == 100
    assert reasons.loc["traffic", "count"] + reasons.loc["weather", "count"] > 0

    routes = get_route_distribution(df).set_index("value")
    assert routes.loc["R1", "count"] == 50
    assert routes.loc["R2", "count"] == 50

    warehouses = get_warehouse_distribution(df).set_index("value")
    assert warehouses["count"].sum() == 100

    events = get_event_distribution(df)
    assert events.empty  # fixture has neither scan_type nor status

    with_status = pd.DataFrame({"status": ["delayed", "on-time", "delayed"]})
    status_events = get_event_distribution(with_status).set_index("value")
    assert status_events.loc["delayed", "count"] == 2


def test_distributions_empty_when_column_absent() -> None:
    df = pd.DataFrame({"shipment_id": ["S1"]})

    assert get_delay_reason_distribution(df).empty
    assert get_route_distribution(df).empty
    assert get_warehouse_distribution(df).empty
    assert get_event_distribution(df).empty


def test_delay_distribution_stats_and_histogram() -> None:
    result = get_delay_distribution(shipments_100_20())

    assert result["available"] is True
    assert result["delayed_records"] == 20
    assert result["stats"]["min"] == pytest.approx(10.0)
    assert result["stats"]["max"] == pytest.approx(150.0)
    assert result["histogram"]["count"].sum() == 20

    missing = get_delay_distribution(pd.DataFrame({"shipment_id": ["S1"]}))
    assert missing["available"] is False


def test_missingness_and_time_distribution() -> None:
    df = shipments_100_20()
    missing = get_missingness_summary(df)

    assert missing["missing"].sum() == 0
    assert list(missing.columns) == ["column", "missing", "missing_pct"]

    time_dist = get_time_distribution(df, freq="D")
    assert time_dist["available"] is True
    assert time_dist["periods"]["records"].sum() == 100

    no_time = get_time_distribution(pd.DataFrame({"a": [1]}))
    assert no_time["available"] is False


def test_delay_flag_summary_reports_method() -> None:
    summary = get_delay_flag_summary(shipments_100_20())

    assert summary["available"] is True
    assert summary["delayed_records"] == 20
    assert summary["delayed_shipments"] == 20
    assert summary["info"]["method"] == "duration_gt_zero"


def test_delay_reason_breakdown_values_and_validation() -> None:
    df = shipments_100_20()
    breakdown = delay_reason_breakdown(df).set_index("delay_reason")

    assert breakdown["records"].sum() == 100
    assert breakdown.loc["traffic", "records"] > 0
    assert breakdown.loc["none", "avg_delay"] == pytest.approx(0.0)

    with pytest.raises(ValueError, match="No delay reason column"):
        delay_reason_breakdown(pd.DataFrame({"shipment_id": ["S1"]}))


def test_delay_by_segment_generic_dimension() -> None:
    df = shipments_100_20()
    by_route = delay_by_segment(df, "route_id").set_index("segment")

    assert by_route.loc["R1", "delay_rate"] == pytest.approx(30.0)
    assert by_route.loc["R2", "delay_rate"] == pytest.approx(10.0)

    with pytest.raises(ValueError, match="Segment column"):
        delay_by_segment(df, "nope")


def test_derive_time_features_adds_parts_without_mutation() -> None:
    df = shipments_100_20()
    before = df.copy(deep=True)

    enriched = derive_time_features(df)

    assert "timestamp_date" in enriched.columns
    assert "timestamp_month" in enriched.columns
    assert "timestamp_hour" in enriched.columns
    assert enriched["timestamp_month"].str.startswith("2024-01").all()
    assert (enriched["timestamp_hour"] == 8).all()
    pd.testing.assert_frame_equal(df, before)

    with pytest.raises(ValueError, match="No timestamp column"):
        derive_time_features(pd.DataFrame({"a": [1]}))


def test_delay_over_time_daily_counts() -> None:
    df = shipments_100_20()
    trend = delay_over_time(df, freq="D")

    assert trend["records"].sum() == 100
    assert trend["shipments"].sum() == 100
    assert trend["delayed_shipments"].sum() == 20
    # Fixture design: days 1-5 carry 3 delayed of 10 (30%), days 6-10 carry
    # 1 of 10 (10%).
    assert trend["delay_rate"].head(5).tolist() == [pytest.approx(30.0)] * 5
    assert trend["delay_rate"].tail(5).tolist() == [pytest.approx(10.0)] * 5


def test_rolling_requires_full_window_and_flags_sparse() -> None:
    df = shipments_100_20()
    trend = delay_over_time(df, freq="D")  # 10 periods

    rolled = rolling_delay_rate(trend, window=7)
    assert rolled["rolling_avg_delay_rate_7"].head(6).isna().all()
    # Mean of first full window: five days at 30% + two days at 10%.
    assert rolled["rolling_avg_delay_rate_7"].iloc[6] == pytest.approx((30 * 5 + 10 * 2) / 7)

    sparse = rolling_delay_rate(trend.head(3), window=7)
    assert sparse.attrs["sparse_warning"] is True
    assert sparse["rolling_avg_delay_rate_7"].isna().all()

    with pytest.raises(ValueError, match="window > 0"):
        rolling_delay_rate(trend, window=0)
    with pytest.raises(ValueError, match="not found"):
        rolling_delay_rate(trend, value_column="nope")


def test_available_dimensions_and_segment_summary() -> None:
    df = shipments_100_20()
    dims = available_dimensions(df)

    assert dims["shipment"] == "shipment_id"
    assert dims["route"] == "route_id"
    assert dims["delay_reason"] == "delay_reason"
    assert "warehouse_id" in dims["warehouses"]
    assert "timestamp" in dims["timestamps"]

    tables = segment_summary(df)
    assert set(tables) >= {"route", "delay_reason"}
    assert "delay_rate" in tables["route"].columns
