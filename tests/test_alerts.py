"""Tests for the alert layer (synthetic frames; no production dependence)."""

import json

import pandas as pd
import pytest

from analysis.alerts import (
    ALERT_COLUMNS,
    empty_alerts,
    generate_alerts,
    generate_cascade_alerts,
    generate_delay_duration_alerts,
    generate_delay_rate_alerts,
    generate_route_alerts,
    generate_warehouse_alerts,
    summarize_alerts,
)
from config.alert_config import DEFAULT_ALERT_CONFIG, resolve_config

FIXED_TIME = "2024-06-01T00:00:00+00:00"
SMALL_CONFIG = {
    "min_shipments_for_rate_alert": 2,
    "near_miss_ratio": 0.8,
}


def alert_fixture() -> pd.DataFrame:
    """Rates: R1 75% (3/4), R2 25% (1/4, near-miss), R3 0% (0/2).

    Durations: S-HOT worst 90 (WARNING), S-CRIT worst 150 (CRITICAL).
    Cascade: S-CAS has two delayed events (depth-1 candidate).
    """
    rows = []
    plan = [
        ("R1", "W1", "S-R1A", 40.0), ("R1", "W1", "S-R1B", 10.0),
        ("R1", "W2", "S-R1C", 90.0), ("R1", "W2", "S-R1D", 0.0),
        ("R2", "W1", "S-R2A", 150.0), ("R2", "W1", "S-R2B", 0.0),
        ("R2", "W2", "S-R2C", 0.0), ("R2", "W2", "S-R2D", 0.0),
        ("R3", "W3", "S-R3A", 0.0), ("R3", "W3", "S-R3B", 0.0),
        ("R4", "W1", "S-CAS", 20.0),
    ]
    for i, (route, warehouse, shipment, duration) in enumerate(plan):
        rows.append(
            {
                "shipment_id": shipment,
                "timestamp": f"2024-05-{(i % 9) + 1:02d} 08:00:00",
                "route_id": route,
                "warehouse_id": warehouse,
                "delay_reason": "traffic" if duration > 0 else "none",
                "delay_duration": duration,
            }
        )
    rows.append(
        {
            "shipment_id": "S-CAS",
            "timestamp": "2024-05-10 08:00:00",
            "route_id": "R4",
            "warehouse_id": "W1",
            "delay_reason": "weather",
            "delay_duration": 25.0,
        }
    )
    return pd.DataFrame(rows)


def test_delay_rate_threshold_detection() -> None:
    alerts = generate_route_alerts(
        alert_fixture(), {**SMALL_CONFIG}, detected_at=FIXED_TIME
    )
    r1 = alerts[alerts["entity_id"] == "R1"]
    assert len(r1) == 1
    assert r1.iloc[0]["severity"] == "CRITICAL"  # 75% >= critical 50%
    assert r1.iloc[0]["metric_value"] == pytest.approx(75.0)
    assert r1.iloc[0]["threshold"] == pytest.approx(30.0)
    assert "R1" in r1.iloc[0]["message"] and "75.0%" in r1.iloc[0]["message"]


def test_no_alert_below_threshold_without_near_miss() -> None:
    alerts = generate_route_alerts(
        alert_fixture(), {**SMALL_CONFIG}, detected_at=FIXED_TIME
    )
    assert "R3" not in alerts["entity_id"].tolist()  # 0% is far below
    quiet = generate_route_alerts(
        alert_fixture(),
        {**SMALL_CONFIG, "delay_rate_threshold": 99.0, "critical_delay_rate": 99.5,
         "near_miss_ratio": None},
        detected_at=FIXED_TIME,
    )
    assert quiet.empty
    assert list(quiet.columns) == ALERT_COLUMNS


def test_duration_threshold_detection() -> None:
    alerts = generate_delay_duration_alerts(
        alert_fixture(), SMALL_CONFIG, detected_at=FIXED_TIME
    )
    by_id = {row["entity_id"]: row for _, row in alerts.iterrows()}
    assert by_id["S-R1C"]["severity"] == "WARNING"  # 90 in [60, 120)
    assert by_id["S-R2A"]["severity"] == "CRITICAL"  # 150 >= 120
    assert by_id["S-R2A"]["metric_value"] == pytest.approx(150.0)
    # S-CAS (worst 25) is below the near-miss band [48, 60): correctly silent.
    assert "S-CAS" not in by_id
    # Duplicated rows still yield one alert per shipment.
    doubled = pd.concat(
        [alert_fixture(), alert_fixture().iloc[[4]]], ignore_index=True
    )
    duped = generate_delay_duration_alerts(
        doubled, SMALL_CONFIG, detected_at=FIXED_TIME
    )
    assert sum(1 for _, r in duped.iterrows() if r["entity_id"] == "S-R2A") == 1


def test_route_and_warehouse_alert_shapes() -> None:
    routes = generate_route_alerts(alert_fixture(), SMALL_CONFIG, FIXED_TIME)
    assert set(routes["entity_type"].unique()) <= {"route"}
    assert list(routes.columns) == ALERT_COLUMNS
    warehouses = generate_warehouse_alerts(alert_fixture(), SMALL_CONFIG, FIXED_TIME)
    assert set(warehouses["entity_type"].unique()) <= {"warehouse"}
    # Invalid entity rejected, not silently accepted.
    with pytest.raises(ValueError, match="entity must be"):
        generate_delay_rate_alerts(alert_fixture(), entity="planet")


def test_cascade_alerts_reuse_existing_analysis() -> None:
    from analysis.cascade_analysis import detect_cascade_candidates

    df = alert_fixture()
    expected, _ = detect_cascade_candidates(df)
    alerts = generate_cascade_alerts(df, SMALL_CONFIG, detected_at=FIXED_TIME)

    assert set(alerts["entity_id"]) == set(expected["shipment_id"])
    assert (alerts["alert_type"] == "cascade_detected").all()
    assert (alerts["severity"] == "WARNING").all()  # all depth 1 here
    evidence = json.loads(alerts.iloc[0]["evidence"])
    assert "stages" in evidence and "initial_route" in evidence


def test_multiple_types_combined_with_stable_ids() -> None:
    alerts, report = generate_alerts(alert_fixture(), SMALL_CONFIG, FIXED_TIME)

    assert report["total_alerts"] == len(alerts)
    assert set(alerts["alert_type"].unique()) >= {
        "delay_rate", "excessive_delay", "cascade_detected",
    }
    assert alerts["alert_id"].tolist() == [
        f"ALT-{i + 1:04d}" for i in range(len(alerts))
    ]
    # CRITICAL sorts before WARNING before INFO.
    ranks = {"CRITICAL": 2, "WARNING": 1, "INFO": 0}
    observed = [ranks[s] for s in alerts["severity"]]
    assert observed == sorted(observed, reverse=True)
    assert alerts["detected_at"].unique().tolist() == [FIXED_TIME]


def test_severity_assignment_including_info() -> None:
    alerts = generate_route_alerts(alert_fixture(), SMALL_CONFIG, FIXED_TIME)
    by_id = {row["entity_id"]: row["severity"] for _, row in alerts.iterrows()}
    assert by_id["R1"] == "CRITICAL"
    assert by_id["R2"] == "INFO"  # 25% in [24%, 30%) near-miss band


def test_configurable_thresholds_and_disable() -> None:
    df = alert_fixture()
    strict = generate_route_alerts(
        df, {**SMALL_CONFIG, "delay_rate_threshold": 80.0,
             "critical_delay_rate": 90.0, "near_miss_ratio": None}, FIXED_TIME,
    )
    assert strict.empty  # 75% no longer breaches

    disabled, report = generate_alerts(
        df,
        {**SMALL_CONFIG, "delay_rate_threshold": None,
         "delay_duration_threshold": None},
        FIXED_TIME,
    )
    assert "excessive_delay" not in disabled["alert_type"].tolist()
    assert not any(
        t.startswith("delay_rate") and v > 0
        for t, v in report["by_type"].items()
    )

    with pytest.raises(ValueError, match="Unknown alert config keys"):
        resolve_config({"made_up": 1})
    with pytest.raises(ValueError, match="critical_delay_rate"):
        resolve_config({"delay_rate_threshold": 60.0, "critical_delay_rate": 50.0})
    with pytest.raises(ValueError, match="near_miss_ratio"):
        resolve_config({"near_miss_ratio": 1.5})
    assert resolve_config(None) == DEFAULT_ALERT_CONFIG


def test_empty_dataframe_returns_empty_table() -> None:
    df = alert_fixture().iloc[0:0]
    alerts, report = generate_alerts(df, SMALL_CONFIG, FIXED_TIME)
    assert alerts.empty and list(alerts.columns) == ALERT_COLUMNS
    assert report["total_alerts"] == 0
    summary = summarize_alerts(alerts)
    assert summary["total_alerts"] == 0
    assert summary["by_severity"] == {"CRITICAL": 0, "WARNING": 0, "INFO": 0}


def test_missing_columns_yield_empty_with_reasons() -> None:
    bare = pd.DataFrame({"shipment_id": ["S1", "S2"]})
    assert generate_route_alerts(bare, SMALL_CONFIG, FIXED_TIME).empty
    assert generate_warehouse_alerts(bare, SMALL_CONFIG, FIXED_TIME).empty
    assert generate_delay_duration_alerts(bare, SMALL_CONFIG, detected_at=FIXED_TIME).empty
    assert generate_cascade_alerts(bare, SMALL_CONFIG, FIXED_TIME).empty
    alerts, report = generate_alerts(bare, SMALL_CONFIG, FIXED_TIME)
    assert alerts.empty
    assert sorted(report["unavailable"]) == sorted(report["by_type"].keys())


def test_duplicates_safe_and_deterministic() -> None:
    df = alert_fixture()
    doubled = pd.concat([df, df], ignore_index=True)
    first, _ = generate_alerts(df, SMALL_CONFIG, FIXED_TIME)
    again, _ = generate_alerts(df, SMALL_CONFIG, FIXED_TIME)
    duped, _ = generate_alerts(doubled, SMALL_CONFIG, FIXED_TIME)
    pd.testing.assert_frame_equal(first, again)
    assert not duped.empty  # duplicates flow through metrics without crashing
    assert duped["alert_id"].is_unique


def test_input_never_mutated() -> None:
    df = alert_fixture()
    before = df.copy(deep=True)
    generate_alerts(df, SMALL_CONFIG, FIXED_TIME)
    generate_route_alerts(df, SMALL_CONFIG, FIXED_TIME)
    generate_warehouse_alerts(df, SMALL_CONFIG, FIXED_TIME)
    generate_delay_duration_alerts(df, SMALL_CONFIG, detected_at=FIXED_TIME)
    generate_cascade_alerts(df, SMALL_CONFIG, FIXED_TIME)
    summarize_alerts(empty_alerts())
    pd.testing.assert_frame_equal(df, before)


def test_no_false_alerts_when_values_unavailable() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", "S2", "S3"],
            "route_id": ["R1", "R1", "R1"],
            "delay_duration": [None, None, None],
        }
    )
    alerts, _ = generate_alerts(df, SMALL_CONFIG, FIXED_TIME)
    # No measurable delay anywhere: duration/cascade generators stay silent.
    assert "excessive_delay" not in alerts["alert_type"].tolist()
    assert "cascade_detected" not in alerts["alert_type"].tolist()


def test_summary_reports_facts_not_scores() -> None:
    alerts, _ = generate_alerts(alert_fixture(), SMALL_CONFIG, FIXED_TIME)
    summary = summarize_alerts(alerts)

    assert summary["total_alerts"] == len(alerts)
    assert sum(summary["by_severity"].values()) == len(alerts)
    assert "R1" in summary["affected_routes"]
    assert summary["cascade_alerts"] >= 1
    assert "risk_score" not in summary
    top = summary["largest_exceedances"][0]
    assert top["exceedance"] == pytest.approx(
        top["metric_value"] - top["threshold"]
    )
    for row in summary["largest_exceedances"]:
        assert set(row) == {
            "alert_id", "alert_type", "entity_id",
            "metric_value", "threshold", "exceedance",
        }


def test_evidence_is_structured_json() -> None:
    alerts, _ = generate_alerts(alert_fixture(), SMALL_CONFIG, FIXED_TIME)
    for _, row in alerts.iterrows():
        payload = json.loads(row["evidence"])
        assert isinstance(payload, dict)
    assert "delay-rate threshold" in alerts.iloc[0]["message"] or "threshold" in alerts.iloc[0]["message"]
