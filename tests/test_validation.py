"""Tests for pipeline/validation.py (detection only, no cleaning)."""

import pandas as pd

from pipeline.validation import (
    check_categoricals,
    check_data_types,
    check_duplicates,
    check_identifiers,
    check_missing_values,
    check_numeric_values,
    check_required_columns,
    check_timestamps,
    format_report,
    profile_dataset,
    validate_dataset,
)


def test_missing_values_detected() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", "S2", None],
            "warehouse_id": ["W1", None, None],
        }
    )
    result = check_missing_values(df)
    by_col = {row["column"]: row for row in result.to_dict(orient="records")}
    assert by_col["shipment_id"]["missing"] == 1
    assert by_col["warehouse_id"]["missing"] == 2
    # Original data untouched.
    assert df.isna().sum().sum() == 3


def test_duplicates_detected() -> None:
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    result = check_duplicates(df)
    assert result["duplicate_rows"] == 1
    assert result["duplicate_pct"] == 1 / 3 * 100.0
    # No removal performed.
    assert len(df) == 3


def test_data_types_flag_mismatch() -> None:
    df = pd.DataFrame({"delay_duration": ["30", "bad", None]})
    result = check_data_types(df, {"delay_duration": "numeric"})
    assert not result["passed"]
    assert result["mismatches"][0]["column"] == "delay_duration"


def test_empty_identifier_detected() -> None:
    df = pd.DataFrame({"shipment_id": [None, None], "x": [1, 2]})
    result = check_identifiers(df, ["shipment_id"])
    assert result["shipment_id"]["completely_empty"] is True

    report = validate_dataset(
        df, dataset_name="test", identifier_columns=["shipment_id"]
    )
    assert report["valid"] is False
    assert report["status"] == "ERROR"


def test_missing_required_column_is_error() -> None:
    df = pd.DataFrame({"a": [1]})
    check = check_required_columns(df, ["shipment_id"])
    assert check["missing"] == ["shipment_id"]

    report = validate_dataset(df, dataset_name="test", required_columns=["shipment_id"])
    assert report["valid"] is False
    assert report["status"] == "ERROR"


def test_timestamp_unparsable_detected() -> None:
    df = pd.DataFrame({"reported_at": ["2024-01-01", "not-a-date", None]})
    result = check_timestamps(df, ["reported_at"])
    assert result["reported_at"]["unparsable"] == 1
    assert result["reported_at"]["missing"] == 1


def test_numeric_negative_and_non_numeric_detected() -> None:
    df = pd.DataFrame({"delay_duration": [10, -5, "bad"]})
    result = check_numeric_values(df, ["delay_duration"])
    assert result["delay_duration"]["negative"] == 1
    assert result["delay_duration"]["non_numeric"] == 1


def test_categorical_case_inconsistency_reported_not_fixed() -> None:
    df = pd.DataFrame({"status": ["Delayed", "delayed", "DELAYED", "on-time"]})
    result = check_categoricals(df, ["status"])
    assert result["status"]["case_inconsistencies"]
    # Values unchanged (no normalization).
    assert set(df["status"].tolist()) == {"Delayed", "delayed", "DELAYED", "on-time"}


def test_profile_dataset_structure() -> None:
    df = pd.DataFrame({"a": [1, 2, None], "b": ["x", "x", "y"]})
    profile = profile_dataset(df, dataset_name="demo")
    assert profile["row_count"] == 3
    assert profile["column_count"] == 2
    assert profile["missing"]["a"] == 1
    assert profile["duplicate_row_count"] == 0
    assert profile["numeric_summary"]["a"]["min"] == 1.0
    assert profile["categorical_summary"]["b"]["unique_count"] == 2


def test_valid_dataset_passes() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", "S2"],
            "reported_at": ["2024-01-01", "2024-01-02"],
            "delay_duration": [10, 20],
            "status": ["delayed", "on-time"],
        }
    )
    report = validate_dataset(
        df,
        dataset_name="valid_demo",
        required_columns=["shipment_id"],
        identifier_columns=["shipment_id"],
        timestamp_columns=["reported_at"],
        numeric_columns=["delay_duration"],
        categorical_columns=["status"],
        expected_types={"delay_duration": "numeric"},
    )
    assert report["valid"] is True
    assert report["status"] == "OK"

    text = format_report(report, profile_dataset(df, "valid_demo"))
    assert "DATA QUALITY REPORT" in text
    assert "Overall Status: OK" in text
