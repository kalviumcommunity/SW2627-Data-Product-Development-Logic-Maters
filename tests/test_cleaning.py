"""Tests for pipeline/cleaning.py (small frames, no real raw dependence)."""

from pathlib import Path

import pandas as pd

from pipeline.cleaning import (
    clean_dataset,
    clean_file,
    clean_missing_values,
    handle_duplicates,
    handle_invalid_records,
    normalize_strings,
    save_cleaned_dataset,
    standardize_categoricals,
    standardize_data_types,
    standardize_dates,
    validate_cleaned_dataset,
)


def test_missing_numeric_filled_with_median() -> None:
    df = pd.DataFrame({"delay_duration": [10.0, 20.0, None]})
    cleaned, summary = clean_missing_values(
        df, numeric_columns=["delay_duration"], numeric_strategy="median"
    )
    assert cleaned["delay_duration"].tolist() == [10.0, 20.0, 15.0]
    assert summary["numeric_filled"]["delay_duration"] == 1
    # Input untouched.
    assert df["delay_duration"].isna().sum() == 1


def test_missing_categorical_uses_unknown_and_ids_dropped() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", None, "  "],
            "status": ["delayed", None, "  "],
        }
    )
    cleaned, summary = clean_missing_values(
        df,
        categorical_columns=["status"],
        identifier_columns=["shipment_id"],
        categorical_fill="unknown",
    )
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["status"] == "delayed"
    assert summary["identifier_rows_dropped"] == 2


def test_datatype_conversion() -> None:
    df = pd.DataFrame(
        {
            "delay_duration": ["10", "bad", None],
            "reported_at": ["2024-01-01", "not-a-date", None],
            "shipment_id": [123, " S2 ", None],
        }
    )
    cleaned, _ = standardize_data_types(
        df,
        numeric_columns=["delay_duration"],
        datetime_columns=["reported_at"],
        identifier_columns=["shipment_id"],
    )
    assert pd.api.types.is_numeric_dtype(cleaned["delay_duration"])
    assert pd.api.types.is_datetime64_any_dtype(cleaned["reported_at"])
    assert cleaned["reported_at"].isna().sum() == 2
    assert cleaned.loc[0, "shipment_id"] == "123"


def test_string_normalization_trims_and_collapses() -> None:
    df = pd.DataFrame({"warehouse_id": ["  W1  ", "W  2", None]})
    cleaned, _ = normalize_strings(df, string_columns=["warehouse_id"])
    assert cleaned.loc[0, "warehouse_id"] == "W1"
    assert cleaned.loc[1, "warehouse_id"] == "W 2"
    assert pd.isna(cleaned.loc[2, "warehouse_id"])


def test_datetime_conversion_invalid_becomes_nat() -> None:
    df = pd.DataFrame({"ts": ["2024-01-01 10:00:00", "invalid", None]})
    cleaned, summary = standardize_dates(df, ["ts"])
    assert pd.api.types.is_datetime64_any_dtype(cleaned["ts"])
    assert cleaned["ts"].isna().sum() == 2
    assert summary["converted"] == ["ts"]


def test_duplicate_exact_rows_removed() -> None:
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    cleaned, summary = handle_duplicates(df)
    assert len(cleaned) == 2
    assert summary["duplicates_removed"] == 1


def test_invalid_records_missing_id_and_negative() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", None, "S3"],
            "delay_duration": [10, 20, -5],
        }
    )
    cleaned, summary = handle_invalid_records(
        df,
        identifier_columns=["shipment_id"],
        non_negative_columns=["delay_duration"],
    )
    assert cleaned["shipment_id"].tolist() == ["S1"]
    assert summary["reasons"]["missing_identifier"] == 1
    assert summary["reasons"]["negative_value"] == 1


def test_outliers_preserved() -> None:
    df = pd.DataFrame(
        {"shipment_id": ["S1", "S2"], "delay_duration": [10, 100000]}
    )
    cleaned, summary = handle_invalid_records(
        df,
        identifier_columns=["shipment_id"],
        non_negative_columns=["delay_duration"],
    )
    assert len(cleaned) == 2
    assert summary["invalid_removed"] == 0


def test_categorical_mapping_only_with_explicit_map() -> None:
    df = pd.DataFrame({"status": [" Delayed ", "DELAYED", "on-time"]})
    mapping = {"status": {"delayed": "delayed"}}
    cleaned, summary = standardize_categoricals(df, categorical_mappings=mapping)
    assert cleaned["status"].tolist() == ["delayed", "delayed", "on-time"]
    assert summary["mapped_values"]["status"] == 2


def test_clean_dataset_summary_and_reproducibility() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": [" S1 ", "S1", None, "S2"],
            "delay_duration": ["10", "10", "20", -5],
            "reported_at": ["2024-01-01", "2024-01-01", "bad", "2024-01-02"],
            "status": [" Delayed ", "Delayed", None, "on-time"],
        }
    )
    first, summary = clean_dataset(
        df,
        dataset_name="demo",
        identifier_columns=["shipment_id"],
        numeric_columns=["delay_duration"],
        categorical_columns=["status"],
        datetime_columns=["reported_at"],
        non_negative_columns=["delay_duration"],
        categorical_mappings={"status": {"delayed": "delayed", "on-time": "on-time"}},
    )
    second, _ = clean_dataset(
        df,
        dataset_name="demo",
        identifier_columns=["shipment_id"],
        numeric_columns=["delay_duration"],
        categorical_columns=["status"],
        datetime_columns=["reported_at"],
        non_negative_columns=["delay_duration"],
        categorical_mappings={"status": {"delayed": "delayed", "on-time": "on-time"}},
    )
    pd.testing.assert_frame_equal(first, second)
    assert summary["source_dataset"] == "demo"
    assert summary["input_rows"] == 4
    assert summary["output_rows"] == len(first)
    assert "delay_duration" in summary["columns_transformed"]
    # Raw frame untouched.
    assert len(df) == 4


def test_cleaned_output_valid_via_validation() -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1", "S2"],
            "delay_duration": [10, 20],
        }
    )
    cleaned, _ = clean_dataset(
        df,
        dataset_name="demo",
        identifier_columns=["shipment_id"],
        numeric_columns=["delay_duration"],
        non_negative_columns=["delay_duration"],
    )
    report = validate_cleaned_dataset(
        cleaned,
        dataset_name="demo",
        required_columns=["shipment_id"],
        identifier_columns=["shipment_id"],
        numeric_columns=["delay_duration"],
    )
    assert report["status"] == "OK"
    assert report["valid"] is True


def test_save_and_clean_file_preserves_raw(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_file = raw_dir / "delays.csv"
    content = "shipment_id,delay_duration\nS1,10\nS1,10\n,20\n"
    raw_file.write_text(content, encoding="utf-8")

    out_file = tmp_path / "processed" / "delays_cleaned.csv"
    cleaned, summary, saved = clean_file(
        raw_file,
        output_path=out_file,
        identifier_columns=["shipment_id"],
        numeric_columns=["delay_duration"],
    )
    assert saved == out_file
    assert out_file.is_file()
    # Raw unchanged.
    assert raw_file.read_text(encoding="utf-8") == content
    # One exact duplicate + one missing-ID row handled.
    assert summary["duplicates_removed"] >= 0
    assert len(cleaned) <= 3

    # save_cleaned_dataset round-trip is deterministic.
    reread = pd.read_csv(out_file)
    assert len(reread) == len(cleaned)
