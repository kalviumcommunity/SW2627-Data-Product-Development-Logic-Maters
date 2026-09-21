"""Tests for analysis/kpis.py (synthetic frames, no production dependence)."""

import pandas as pd
import pytest

from _analytics_fixtures import integrated_like, shipments_100_20
from analysis.kpis import (
    compute_delay_kpis,
    compute_kpis,
    compute_operational_kpis,
    compute_shipment_kpis,
)


def test_delay_rate_20_percent_on_100_20_frame() -> None:
    df = shipments_100_20()
    kpis = compute_shipment_kpis(df)

    assert kpis["total_shipments"] == 100
    assert kpis["delayed_shipments"] == 20
    assert kpis["on_time_shipments"] == 80
    assert kpis["delay_rate"] == pytest.approx(20.0)
    assert kpis["on_time_rate"] == pytest.approx(80.0)


def test_delay_duration_stats_over_delayed_records() -> None:
    df = shipments_100_20()
    kpis = compute_delay_kpis(df)

    assert kpis["available"] is True
    assert kpis["delayed_records"] == 20
    assert kpis["delayed_records_without_duration"] == 0
    delayed = pd.to_numeric(df["delay_duration"])
    delayed = delayed[delayed > 0]
    assert kpis["average_delay"] == pytest.approx(float(delayed.mean()))
    assert kpis["median_delay"] == pytest.approx(float(delayed.median()))
    assert kpis["max_delay"] == pytest.approx(float(delayed.max()))
    assert kpis["min_delay"] == pytest.approx(float(delayed.min()))
    assert kpis["total_delay"] == pytest.approx(float(delayed.sum()))


def test_operational_match_rates_from_traceability() -> None:
    df = integrated_like()
    kpis = compute_operational_kpis(df)

    assert kpis["rows_with_delay_report_match"] == 3
    assert kpis["delay_report_match_rate"] == pytest.approx(75.0)
    assert kpis["rows_with_transfer_match"] == 2
    assert kpis["transfer_match_rate"] == pytest.approx(50.0)
    assert kpis["records_per_shipment"] == pytest.approx(4 / 3)


def test_full_bundle_keys_and_no_input_mutation() -> None:
    df = shipments_100_20()
    before = df.copy(deep=True)

    bundle = compute_kpis(df)

    assert set(bundle) == {"shipment", "delay", "operational"}
    assert bundle["shipment"]["delay_rate"] == pytest.approx(20.0)
    pd.testing.assert_frame_equal(df, before)


def test_empty_dataset_rates_are_none_not_zero() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": pd.Series(dtype="string"),
            "delay_duration": pd.Series(dtype="float64"),
        }
    )
    shipment = compute_shipment_kpis(df)
    assert shipment["total_shipments"] == 0
    assert shipment["delay_rate"] is None

    delay = compute_delay_kpis(df)
    assert delay["delayed_records"] == 0
    assert delay["average_delay"] is None


def test_missing_delay_signal_reports_reason() -> None:
    df = pd.DataFrame({"shipment_id": ["S1", "S2"], "route_id": ["R1", "R2"]})
    shipment = compute_shipment_kpis(df)

    assert shipment["delayed_shipments"] is None
    assert shipment["delay_rate"] is None
    assert shipment["warnings"]

    delay = compute_delay_kpis(df)
    assert delay["available"] is False


def test_status_based_flag_with_caller_values() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", "S2", "S3", "S4"],
            "status": ["Delayed", "on-time", "DELAYED ", "unknown"],
        }
    )
    kpis = compute_shipment_kpis(df)

    assert kpis["delayed_shipments"] == 2
    assert kpis["delay_rate"] == pytest.approx(50.0)


def test_deterministic_results() -> None:
    df = shipments_100_20()
    first = compute_kpis(df)
    second = compute_kpis(df)

    assert first == second
