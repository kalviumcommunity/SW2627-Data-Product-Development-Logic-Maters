"""Tests for analysis/cascade_analysis.py (synthetic journeys only)."""

from pathlib import Path

import pandas as pd
import pytest

from analysis.cascade_analysis import (
    cascade_by_route,
    cascade_by_warehouse,
    cascade_summary_metrics,
    classify_cascade_stage,
    detect_cascade_candidates,
    get_shipment_events,
    reconstruct_shipment_journey,
    root_cause_signals,
    save_cascade_candidates,
    sort_shipment_events,
)


def journey_frame(rows: list[dict]) -> pd.DataFrame:
    """Build a journey frame with canonical integrated-like columns."""
    base = {
        "route_id": None,
        "warehouse_id": None,
        "transfer_id": None,
        "status": None,
        "delay_reason": None,
        "delay_duration": 0.0,
    }
    return pd.DataFrame([{**base, **row} for row in rows])


def test_no_cascade_for_clean_shipment() -> None:
    df = journey_frame(
        [
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00"},
            {"shipment_id": "A", "timestamp": "2024-01-02 08:00"},
        ]
    )
    candidates, info = detect_cascade_candidates(df)

    assert candidates.empty
    assert info["candidate_shipments"] == 0
    assert list(candidates.columns)[:3] == [
        "shipment_id", "event_count", "delayed_event_count",
    ]


def test_single_delay_is_not_a_cascade() -> None:
    df = journey_frame(
        [
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
             "delay_duration": 45.0},
            {"shipment_id": "A", "timestamp": "2024-01-02 08:00"},
        ]
    )
    candidates, info = detect_cascade_candidates(df)

    assert candidates.empty
    assert info["single_delay_not_candidates"] == 1


def test_simple_propagation_is_a_candidate() -> None:
    df = journey_frame(
        [
            {"shipment_id": "B", "timestamp": "2024-01-01 08:00",
             "delay_duration": 30.0, "delay_reason": "traffic",
             "route_id": "R1", "warehouse_id": "W1"},
            {"shipment_id": "B", "timestamp": "2024-01-02 09:00",
             "delay_duration": 60.0, "route_id": "R1",
             "warehouse_id": "W2"},
        ]
    )
    candidates, info = detect_cascade_candidates(df)

    assert len(candidates) == 1
    row = candidates.iloc[0]
    assert row["shipment_id"] == "B"
    assert row["cascade_stage_count"] == 2
    assert row["cascade_depth"] == 1
    assert row["stages"][0] == "initial_delay"
    assert row["initial_delay_duration"] == pytest.approx(30.0)
    assert row["downstream_delay_duration"] == pytest.approx(60.0)
    assert row["downstream_delay_observed"] == pytest.approx(30.0)
    assert info["rule"] == {"min_delay_duration": None, "max_downstream_gap": None}


def test_multi_stage_propagation_chronological() -> None:
    df = journey_frame(
        [
            {"shipment_id": "C", "timestamp": "2024-01-04 18:00",
             "delay_duration": 50.0, "status": "delivered",
             "route_id": "R9", "warehouse_id": "W9"},
            {"shipment_id": "C", "timestamp": "2024-01-01 08:00",
             "delay_duration": 10.0, "route_id": "R1",
             "warehouse_id": "W1"},
            {"shipment_id": "C", "timestamp": "2024-01-02 10:00",
             "delay_duration": 20.0, "transfer_id": "T1",
             "warehouse_id": "W2"},
            {"shipment_id": "C", "timestamp": "2024-01-03 12:00"},
        ]
    )
    events, _ = reconstruct_shipment_journey(df)
    journey = get_shipment_events(events, "C")

    # Scrambled input is reordered chronologically with 1-based sequence.
    assert journey["_event_seq"].tolist() == [1, 2, 3, 4]
    assert journey["_event_time"].is_monotonic_increasing

    candidates, _ = detect_cascade_candidates(df)
    assert len(candidates) == 1
    row = candidates.iloc[0]
    assert row["stages"] == [
        "initial_delay", "transfer_disruption", "final_delivery_delay",
    ]
    assert row["cascade_depth"] == 2
    assert row["final_delay_duration"] == pytest.approx(50.0)


def test_shipments_never_mixed() -> None:
    df = journey_frame(
        [
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
             "delay_duration": 10.0},
            {"shipment_id": "B", "timestamp": "2024-01-01 09:00",
             "delay_duration": 10.0},
            {"shipment_id": "A", "timestamp": "2024-01-05 08:00",
             "delay_duration": 10.0},
            {"shipment_id": "B", "timestamp": "2024-01-05 09:00"},
        ]
    )
    candidates, _ = detect_cascade_candidates(df)

    assert candidates["shipment_id"].tolist() == ["A"]
    assert get_shipment_events(
        reconstruct_shipment_journey(df)[0], "B"
    )["src_delay_duration"].tolist() == [10.0, 0.0]


def test_same_timestamp_deterministic_order() -> None:
    df = journey_frame(
        [
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
             "delay_duration": 10.0, "route_id": "R2"},
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
             "delay_duration": 20.0, "route_id": "R1"},
        ]
    )
    first, _ = reconstruct_shipment_journey(df)
    second, _ = reconstruct_shipment_journey(df)

    pd.testing.assert_frame_equal(first, second)
    # Stable input order breaks the tie deterministically.
    assert first["src_route_id"].tolist() == ["R2", "R1"]
    candidates, _ = detect_cascade_candidates(df)
    assert len(candidates) == 1


def test_missing_identifiers_handled_explicitly() -> None:
    df = journey_frame(
        [
            {"shipment_id": None, "timestamp": "2024-01-01 08:00",
             "delay_duration": 99.0},
            {"shipment_id": "A", "timestamp": None, "delay_duration": 99.0},
            {"shipment_id": "A", "timestamp": "2024-01-02 08:00",
             "delay_duration": 10.0},
            {"shipment_id": "A", "timestamp": "2024-01-03 08:00",
             "delay_duration": 10.0},
        ]
    )
    events, report = reconstruct_shipment_journey(df)

    assert report["skipped_missing_shipment"] == 1
    assert report["skipped_unparsable_timestamp"] == 1
    assert report["events"] == 2
    candidates, _ = detect_cascade_candidates(df)
    assert len(candidates) == 1  # incomplete rows never join the journey


def test_duplicate_rows_do_not_add_stages() -> None:
    row = {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
           "delay_duration": 10.0, "route_id": "R1"}
    df = journey_frame([row, dict(row), {
        "shipment_id": "A", "timestamp": "2024-01-02 08:00",
        "delay_duration": 10.0, "route_id": "R1",
    }])
    events, report = reconstruct_shipment_journey(df)

    assert report["duplicate_rows_removed"] == 1
    candidates, _ = detect_cascade_candidates(df)
    assert candidates.iloc[0]["cascade_stage_count"] == 2


def test_configurable_gap_and_duration() -> None:
    df = journey_frame(
        [
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
             "delay_duration": 5.0},
            {"shipment_id": "A", "timestamp": "2024-02-01 08:00",
             "delay_duration": 5.0},
        ]
    )
    wide, _ = detect_cascade_candidates(df)
    assert len(wide) == 1  # default: any later delay qualifies

    narrow, info = detect_cascade_candidates(df, max_downstream_gap="7D")
    assert narrow.empty
    assert info["rule"]["max_downstream_gap"] is not None

    tiny, _ = detect_cascade_candidates(df, min_delay_duration=60.0)
    assert tiny.empty
    with pytest.raises(ValueError, match="non-negative"):
        detect_cascade_candidates(df, min_delay_duration=-1.0)
    with pytest.raises(ValueError, match="Invalid max_downstream_gap"):
        detect_cascade_candidates(df, max_downstream_gap="not-a-gap")


def test_min_duration_requires_duration_column() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["A", "A"],
            "timestamp": ["2024-01-01 08:00", "2024-01-02 08:00"],
            "status": ["delayed", "delayed"],
        }
    )
    candidates, _ = detect_cascade_candidates(df)
    assert len(candidates) == 1  # status-based flags work without durations
    with pytest.raises(ValueError, match="requires a delay duration column"):
        detect_cascade_candidates(df, min_delay_duration=10.0)


def test_edge_cases_empty_single_and_missing_columns() -> None:
    empty = journey_frame([]).iloc[0:0]
    candidates, info = detect_cascade_candidates(empty)
    assert candidates.empty and info["shipments_checked"] == 0

    empty_with_columns = journey_frame(
        [{"shipment_id": "A", "timestamp": "2024-01-01"}]
    ).iloc[0:0]
    candidates, _ = detect_cascade_candidates(empty_with_columns)
    assert candidates.empty
    events, report = reconstruct_shipment_journey(empty_with_columns)
    assert events.empty and report["events"] == 0

    one_event = journey_frame(
        [{"shipment_id": "A", "timestamp": "2024-01-01 08:00",
          "delay_duration": 10.0}]
    )
    assert detect_cascade_candidates(one_event)[0].empty

    with pytest.raises(ValueError, match="No shipment column"):
        reconstruct_shipment_journey(pd.DataFrame({"a": [1]}))
    with pytest.raises(ValueError, match="No timestamp column"):
        reconstruct_shipment_journey(pd.DataFrame({"shipment_id": ["A"]}))
    with pytest.raises(ValueError, match="not found"):
        reconstruct_shipment_journey(
            journey_frame([{"shipment_id": "A", "timestamp": "2024-01-01"}]),
            timestamp_column="nope",
        )


def test_stage_classification_and_sort_helpers() -> None:
    df = journey_frame(
        [
            {"shipment_id": "B", "timestamp": "2024-01-02 08:00",
             "delay_duration": 5.0},
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
             "delay_duration": 5.0},
        ]
    )
    events, _ = reconstruct_shipment_journey(df)
    ordered = sort_shipment_events(events.sample(frac=1.0, random_state=7))

    assert ordered["_shipment"].tolist() == ["A", "B"]
    with pytest.raises(ValueError, match="reconstruct_shipment_journey"):
        sort_shipment_events(pd.DataFrame({"a": [1]}))
    with pytest.raises(ValueError, match="reconstruct_shipment_journey"):
        get_shipment_events(pd.DataFrame({"a": [1]}), "A")

    row = pd.Series({"src_transfer_id": "T1", "src_route_id": "R1"})
    assert (
        classify_cascade_stage(row, is_first_delayed=False, is_last_event=False,
                               route_column="route_id")
        == "transfer_disruption"
    )
    plain = pd.Series({"src_route_id": "R1"})
    assert (
        classify_cascade_stage(plain, is_first_delayed=False, is_last_event=False,
                               route_column="route_id")
        == "downstream_route_delay"
    )
    bare = pd.Series({})
    assert (
        classify_cascade_stage(bare, is_first_delayed=False, is_last_event=False)
        == "downstream_delay"
    )


def test_summary_route_warehouse_and_signals() -> None:
    df = journey_frame(
        [
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
             "delay_duration": 10.0, "route_id": "R1", "warehouse_id": "W1"},
            {"shipment_id": "A", "timestamp": "2024-01-02 08:00",
             "delay_duration": 40.0, "route_id": "R1", "warehouse_id": "W2"},
            {"shipment_id": "B", "timestamp": "2024-01-01 08:00",
             "delay_duration": 10.0, "route_id": "R2", "warehouse_id": "W1"},
            {"shipment_id": "B", "timestamp": "2024-01-03 08:00"},
        ]
    )
    candidates, _ = detect_cascade_candidates(df)
    summary = cascade_summary_metrics(candidates, total_shipments=2)

    assert summary["candidate_count"] == 1
    assert summary["candidate_rate"] == pytest.approx(50.0)
    assert summary["avg_cascade_depth"] == pytest.approx(1.0)
    assert summary["max_cascade_depth"] == 1
    assert summary["avg_downstream_delay"] == pytest.approx(40.0)

    by_route = cascade_by_route(candidates, shipments_per_route={"R1": 1, "R2": 1})
    assert by_route.set_index("route").loc["R1", "candidate_rate"] == pytest.approx(100.0)

    by_wh = cascade_by_warehouse(candidates)
    assert by_wh.iloc[0]["warehouse"] == "W1"

    signals = root_cause_signals(candidates)
    assert set(signals["signal"]) == {"initial_delay", "warehouse_delay"}
    assert root_cause_signals(candidates.iloc[0:0]).empty
    assert cascade_summary_metrics(candidates.iloc[0:0])["candidate_count"] == 0
    assert cascade_by_route(candidates.iloc[0:0]).empty


def test_save_and_no_mutation(tmp_path: Path) -> None:
    df = journey_frame(
        [
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
             "delay_duration": 10.0},
            {"shipment_id": "A", "timestamp": "2024-01-02 08:00",
             "delay_duration": 20.0},
        ]
    )
    before = df.copy(deep=True)
    candidates, _ = detect_cascade_candidates(df)
    out = save_cascade_candidates(candidates, tmp_path / "cascade_candidates.csv")

    assert out.is_file()
    reread = pd.read_csv(out)
    assert len(reread) == 1
    # No route/warehouse signals in this fixture: generic downstream stage.
    assert reread.iloc[0]["stages"] == "initial_delay>downstream_delay"
    pd.testing.assert_frame_equal(df, before)
    with pytest.raises(ValueError, match="empty cascade"):
        save_cascade_candidates(candidates.iloc[0:0], tmp_path / "empty.csv")
