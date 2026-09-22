"""Tests for pipeline/synthetic_showcase.py (deterministic synthetic sources)."""

import pandas as pd

from analysis.cascade_analysis import (
    cascade_summary_metrics,
    detect_cascade_candidates,
)
from analysis.route_analysis import route_metrics
from analysis.warehouse_analysis import transfer_activity, warehouse_metrics
from pipeline.integration import build_integrated_dataset
from pipeline.synthetic_showcase import (
    CLEANING_CONFIGS,
    generate_showcase,
    run_showcase_pipeline,
)


def test_generation_deterministic_and_shaped() -> None:
    first = generate_showcase(seed=7, n_shipments=200)
    second = generate_showcase(seed=7, n_shipments=200)
    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])

    scans, delays, transfers = (
        first["showcase_shipment_scans"],
        first["showcase_delay_reports"],
        first["showcase_warehouse_transfers"],
    )
    # Three sources, correct grains.
    assert len(scans) > 200  # multiple events per shipment
    # Every delay/transfer shipment exists in scans (joins will match).
    assert set(delays["shipment_id"]) <= set(scans["shipment_id"])
    assert set(transfers["shipment_id"]) <= set(scans["shipment_id"])
    assert delays["shipment_id"].is_unique  # shipment grain
    assert transfers["shipment_id"].is_unique  # one leg per shipment max
    # Join keys present, identifiers never missing, durations non-negative.
    for frame in (scans, delays, transfers):
        assert frame["shipment_id"].notna().all()
        assert (frame["shipment_id"].astype(str).str.strip() != "").all()
    assert (scans["delay_duration"] >= 0).all()
    assert (delays["delay_duration"] >= 0).all()
    # Full product surface present.
    assert set(scans["route_id"].unique()) == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert set(scans["warehouse_id"].dropna().unique()) == {
        "W1", "W2", "W3", "W4", "W5",
    }
    assert set(delays["delay_reason"].unique()) == {
        "traffic", "weather", "customs", "congestion", "mechanical",
    }
    assert not scans.duplicated().any()
    # Chronological journeys per shipment.
    stamps = pd.to_datetime(scans["timestamp"], utc=True)
    for _, group in scans.groupby("shipment_id"):
        assert stamps.loc[group.index].is_monotonic_increasing


def test_showcase_pipeline_smoke_tmp(tmp_path) -> None:
    info = run_showcase_pipeline(
        seed=11,
        n_shipments=150,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        output_path=tmp_path / "integrated.csv",
    )
    # Cleaning loses nothing.
    for summary in info["cleaning"].values():
        assert summary["output_rows"] == summary["input_rows"]
    report = info["integration_report"]
    assert report["roles"] == {
        "scans": "showcase_shipment_scans_cleaned",
        "delays": "showcase_delay_reports_cleaned",
        "transfers": "showcase_warehouse_transfers_cleaned",
    }
    assert not any(j.get("is_many_to_many") for j in report["joins"])
    pairs = report["temporal_consistency"]["pairs"]
    assert pairs["timestamp <= reported_at"]["violations"] == 0

    integrated = pd.read_csv(info["integrated_path"])
    for col in (
        "shipment_id", "route_id", "warehouse_id", "delay_reason",
        "transfer_id", "source_warehouse", "destination_warehouse",
        "_delay_match", "_transfer_match",
    ):
        assert col in integrated.columns
    # Analytics surface populated: cascades exist at small scale too.
    candidates, _ = detect_cascade_candidates(integrated)
    assert len(candidates) >= 5
    assert not warehouse_metrics(integrated).empty
    assert not route_metrics(integrated).empty
    assert transfer_activity(integrated)["source_warehouse"]["available"] is True


def test_cleaning_configs_cover_declared_columns() -> None:
    frames = generate_showcase(seed=7, n_shipments=50)
    for name, frame in frames.items():
        config = CLEANING_CONFIGS[name]
        declared = (
            (config.get("identifier_columns") or [])
            + (config.get("numeric_columns") or [])
            + (config.get("categorical_columns") or [])
            + (config.get("datetime_columns") or [])
        )
        for col in declared:
            assert col in frame.columns, f"{name} missing declared {col}"
    # Cascade summary works on the default-scale output shape.
    frames = generate_showcase(seed=42, n_shipments=300)
    from pipeline.cleaning import clean_dataset
    from pipeline.integration import load_processed_datasets  # noqa: F401

    cleaned = {}
    for name, frame in frames.items():
        out, _ = clean_dataset(frame, dataset_name=name, **CLEANING_CONFIGS[name])
        cleaned[name + "_cleaned"] = out
    integrated, _ = build_integrated_dataset(
        cleaned, timestamp_pairs=[("timestamp", "reported_at")]
    )
    candidates, _ = detect_cascade_candidates(integrated)
    summary = cascade_summary_metrics(candidates, total_shipments=300)
    assert summary["candidate_count"] >= 10
    assert summary["max_cascade_depth"] >= 1
