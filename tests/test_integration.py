"""Tests for pipeline/integration.py (synthetic frames, no production dependence)."""

from pathlib import Path

import pandas as pd
import pytest

from pipeline.integration import (
    build_integrated_dataset,
    check_temporal_consistency,
    inspect_join_keys,
    load_processed_datasets,
    merge_datasets,
    save_integrated_dataset,
    validate_join_keys,
    validate_join_result,
)


def _scans() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "shipment_id": ["S1", "S1", "S2", "S3"],
            "timestamp": ["2024-01-01 08:00", "2024-01-01 12:00", "2024-01-02 09:00", "2024-01-03 10:00"],
            "warehouse_id": ["W1", "W2", "W1", "W3"],
            "route_id": ["R1", "R1", "R2", "R3"],
        }
    )


def _delays() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "shipment_id": ["S1", "S2"],
            "delay_reason": ["traffic", "weather"],
            "delay_duration": [30, 60],
        }
    )


def _transfers() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "shipment_id": ["S1", "S4"],
            "transfer_id": ["T1", "T2"],
            "source_warehouse": ["W1", "W9"],
        }
    )


def test_valid_join_preserves_base_and_reports_coverage() -> None:
    merged, report = merge_datasets(_scans(), _delays(), "shipment_id", how="left")

    assert report["left_rows"] == 4
    assert report["right_rows"] == 2
    # S1 has 2 scans x 1 delay = 2 rows; S2 1x1 = 1; S3 unmatched = 1.
    assert report["output_rows"] == 4
    assert report["matched"] == 3
    assert report["left_only"] == 1  # S3 scan without delay
    assert report["right_only"] == 0
    assert report["relationship"] == "many-to-one"
    assert not report["is_many_to_many"]
    assert "shipment_id" in merged.columns
    assert "delay_reason" in merged.columns


def test_unmatched_records_surfaced_not_dropped() -> None:
    merged, report = merge_datasets(_scans(), _transfers(), "shipment_id", how="left")

    assert report["left_only"] == 2  # S2, S3 scans without transfer
    # Left joins exclude right-only rows from output; key-level validation
    # still surfaces the S4 transfer key with no matching scan.
    assert report["right_only"] == 0
    key_check = validate_join_keys(_scans(), _transfers(), "shipment_id")
    assert key_check["right_only"] == 1  # S4 transfer without scan
    # Left join keeps every scan row.
    assert len(merged) == 4
    assert report["unmatched"] == 2
    assert report["unmatched_pct"] == pytest.approx(50.0)


def test_duplicate_keys_flag_many_to_many() -> None:
    left = pd.DataFrame({"shipment_id": ["S1", "S1"], "a": [1, 2]})
    right = pd.DataFrame({"shipment_id": ["S1", "S1"], "b": [3, 4]})

    validation = validate_join_keys(left, right, "shipment_id")
    assert validation["relationship"] == "many-to-many"
    assert validation["is_many_to_many"] is True

    merged, report = merge_datasets(left, right, "shipment_id", how="left")
    assert report["output_rows"] == 4  # 2 x 2 cartesian
    assert report["expansion_factor"] == pytest.approx(2.0)
    assert any("many-to-many" in w.lower() for w in report["warnings"])
    assert len(merged) == 4


def test_missing_join_key_raises_actionable_error() -> None:
    left = pd.DataFrame({"shipment_id": ["S1"]})
    right = pd.DataFrame({"other_id": ["S1"]})

    with pytest.raises(ValueError, match="not found"):
        merge_datasets(left, right, "shipment_id")

    validation = validate_join_keys(left, right, "shipment_id")
    assert validation["valid"] is False


def test_missing_key_values_reported() -> None:
    left = pd.DataFrame({"shipment_id": ["S1", None, "  "]})
    right = pd.DataFrame({"shipment_id": ["S1", "S2"]})

    validation = validate_join_keys(left, right, "shipment_id", "scans", "delays")
    assert validation["left_stats"]["missing"] == 2
    assert any("missing join key" in w for w in validation["warnings"])


def test_record_count_validation_detects_inconsistency() -> None:
    merged, report = merge_datasets(_scans(), _delays(), "shipment_id", how="left")
    result = validate_join_result(merged, report, "shipment_id")

    assert result["checks"]["row_count_consistent"] is True
    assert result["checks"]["missing_join_keys"] == 0

    tampered = dict(report)
    tampered["output_rows"] = 999
    bad = validate_join_result(merged, tampered, "shipment_id")
    assert bad["passed"] is False
    assert any("differ" in w for w in bad["warnings"])


def test_important_columns_preserved_with_suffixes() -> None:
    left = pd.DataFrame({"shipment_id": ["S1"], "warehouse_id": ["W1"], "status": ["scanned"]})
    right = pd.DataFrame({"shipment_id": ["S1"], "warehouse_id": ["W2"], "status": ["delayed"]})

    merged, _ = merge_datasets(left, right, "shipment_id", how="left", suffixes=("_scan", "_delay"))

    assert "shipment_id" in merged.columns
    assert "warehouse_id_scan" in merged.columns
    assert "warehouse_id_delay" in merged.columns
    assert merged.iloc[0]["warehouse_id_scan"] == "W1"
    assert merged.iloc[0]["warehouse_id_delay"] == "W2"


def test_temporal_consistency_flags_violations_without_altering() -> None:
    df = pd.DataFrame(
        {
            "timestamp": ["2024-01-02 10:00", "2024-01-01 10:00"],
            "reported_at": ["2024-01-01 10:00", "2024-01-03 10:00"],
        }
    )
    before = df.copy(deep=True)
    result = check_temporal_consistency(df, [("timestamp", "reported_at")])

    detail = result["pairs"]["timestamp <= reported_at"]
    assert detail["comparable_rows"] == 2
    assert detail["violations"] == 1
    pd.testing.assert_frame_equal(df, before)


def test_build_integrated_dataset_end_to_end(tmp_path: Path) -> None:
    datasets = {
        "shipment_scans_cleaned": _scans(),
        "delay_reports_cleaned": _delays(),
        "warehouse_transfers_cleaned": _transfers(),
    }
    integrated, report = build_integrated_dataset(datasets)

    assert report["base_dataset"] == "shipment_scans_cleaned"
    assert len(report["joins"]) == 2
    assert report["row_count"] == len(integrated)
    # Traceability columns exist and record provenance.
    assert "_record_source" in integrated.columns
    assert "_source_datasets" in integrated.columns
    assert "_delay_match" in integrated.columns
    assert "_transfer_match" in integrated.columns
    assert "_integration_key" in integrated.columns
    # Source columns preserved for later analytics.
    for col in ("route_id", "delay_reason", "transfer_id", "warehouse_id"):
        assert col in integrated.columns or any(col in c for c in integrated.columns)
    # Deterministic ordering by shipment.
    assert integrated["shipment_id"].tolist() == sorted(integrated["shipment_id"].tolist())
    # Inputs untouched.
    assert len(datasets["shipment_scans_cleaned"]) == 4

    saved = save_integrated_dataset(integrated, tmp_path / "integrated_logistics_data.csv")
    assert saved.is_file()
    reread = pd.read_csv(saved)
    assert len(reread) == len(integrated)


def test_build_skips_dataset_missing_key_with_reason() -> None:
    datasets = {
        "shipment_scans_cleaned": _scans(),
        "orphan_cleaned": pd.DataFrame({"route_id": ["R1"], "note": ["x"]}),
    }
    integrated, report = build_integrated_dataset(datasets)

    assert report["skipped"] == [{"dataset": "orphan_cleaned", "reason": "missing key 'shipment_id'"}]
    assert len(integrated) == 4


def test_inspect_join_keys_finds_common_and_missing() -> None:
    inspection = inspect_join_keys(
        {"a": _scans(), "b": _delays()}, candidate_keys=["shipment_id", "route_id"]
    )
    assert "shipment_id" in inspection["common_columns"]
    assert inspection["keys"]["shipment_id"]["present_in"] == ["a", "b"]
    assert inspection["keys"]["route_id"]["present_in"] == ["a"]


def test_load_processed_datasets_excludes_integrated(tmp_path: Path) -> None:
    (tmp_path / "scans_cleaned.csv").write_text("shipment_id\nS1\n", encoding="utf-8")
    (tmp_path / "integrated_logistics_data.csv").write_text("shipment_id\nS9\n", encoding="utf-8")

    loaded = load_processed_datasets(tmp_path)
    assert list(loaded) == ["scans_cleaned"]

    loaded_all = load_processed_datasets(tmp_path, include_integrated=True)
    assert set(loaded_all) == {"scans_cleaned", "integrated_logistics_data"}
