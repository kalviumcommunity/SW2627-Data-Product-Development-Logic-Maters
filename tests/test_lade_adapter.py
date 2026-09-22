"""Tests for the LaDe source adapter (offline fixtures, no network).

The adapter maps real LaDe pickup columns to the product's operational
sources. These tests use tiny hand-built LaDe-shaped frames to verify the
mapping rules: subset selection, per-stage lateness, incident grain, and
the honest absence of warehouse/reason data.
"""

import pandas as pd
import pytest

from pipeline.lade_adapter import (
    build_delay_reports,
    build_shipment_scans,
    load_lade_pickup,
    parse_lade_time,
)


def _lade_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_id": [1, 2, 3],
            "region_id": [9, 9, 11],
            "city": ["Jilin", "Jilin", "Jilin"],
            "courier_id": [7, 7, 8],
            # pkg 1: accept late (after window start), pickup on time
            "accept_time": ["06-05 10:00:00", "06-05 08:00:00", "06-19 08:00:00"],
            "time_window_start": ["06-05 09:00:00", "06-05 09:00:00", "06-19 09:00:00"],
            "time_window_end": ["06-05 11:00:00", "06-05 11:00:00", "06-19 11:00:00"],
            "lng": [126.9, 126.9, 126.9],
            "lat": [44.4, 44.4, 44.4],
            "aoi_id": [12, 12, 13],
            "aoi_type": [14, 14, 3],
            # pkg 2: pickup late; pkg 3 (ds=619) is outside the window
            "pickup_time": ["06-05 10:30:00", "06-05 11:30:00", "06-19 10:00:00"],
            "ds": [605, 606, 619],        }
    )


def test_parse_lade_time_uses_assumed_year():
    parsed = parse_lade_time(pd.Series(["06-05 08:00:00"]))
    assert str(parsed.iloc[0]) == "2022-06-05 08:00:00"


def test_load_lade_pickup_applies_ds_window(tmp_path):
    path = tmp_path / "pickup_jl.csv"
    _lade_frame().to_csv(path, index=False)
    subset, info = load_lade_pickup(path, ds_min=605, ds_max=618)
    assert info["source_rows"] == 3
    assert info["subset_rows"] == 2
    assert set(subset["order_id"]) == {1, 2}
    assert "_lade_row_id" in subset.columns


def test_load_lade_pickup_rejects_unknown_schema(tmp_path):
    path = tmp_path / "pickup_jl.csv"
    pd.DataFrame({"foo": [1]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="schema mismatch"):
        load_lade_pickup(path)


def test_build_shipment_scans_two_events_per_package():
    frame = _lade_frame()
    frame["_lade_row_id"] = range(len(frame))
    scans = build_shipment_scans(frame)
    assert len(scans) == 6  # 2 events per package
    assert set(scans["event_type"]) == {"accept", "pickup"}
    # pkg 1 accept is 60 min late; pickup on time
    accept1 = scans[(scans["shipment_id"] == "1") & (scans["event_type"] == "accept")].iloc[0]
    pickup1 = scans[(scans["shipment_id"] == "1") & (scans["event_type"] == "pickup")].iloc[0]
    assert float(accept1["delay_duration"]) == 60.0
    assert accept1["status"] == "delayed"
    assert float(pickup1["delay_duration"]) == 0.0
    assert pickup1["status"] == "on_time"
    # provenance retained
    assert "source_row_id" in scans.columns and "source_event_id" in scans.columns
    assert "delay_reason" not in scans.columns  # not available in LaDe
    assert "warehouse_id" not in scans.columns  # not available in LaDe


def test_build_delay_reports_incidents_only_and_shipment_grain():
    frame = _lade_frame()
    frame["_lade_row_id"] = range(len(frame))
    delays, info = build_delay_reports(frame)
    # pkg 1 (accept late) and pkg 2 (pickup late) are incidents; pkg 3 is on time
    assert info["incident_packages"] == 2
    assert len(delays) == 2
    assert delays["shipment_id"].is_unique  # shipment grain, no cartesian risk
    pkg2 = delays[delays["shipment_id"] == "2"].iloc[0]
    assert float(pkg2["delay_duration"]) == 30.0
    assert pkg2["delay_stage"] == "pickup"
    pkg1 = delays[delays["shipment_id"] == "1"].iloc[0]
    assert float(pkg1["delay_duration"]) == 0.0  # pickup on time
    assert float(pkg1["initial_delay_duration"]) == 60.0
    assert pkg1["delay_stage"] == "accept"
