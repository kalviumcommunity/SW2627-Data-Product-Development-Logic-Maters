"""Tests for pipeline/ingestion.py.

Uses temporary test data only — real files under data/raw/ are never
created, modified, or deleted by these tests.
"""

from pathlib import Path

import pandas as pd
import pytest

from pipeline.ingestion import (
    DatasetLoadError,
    UnsupportedFileTypeError,
    discover_datasets,
    get_dataset_metadata,
    load_csv,
    load_dataset,
    load_json,
)


def test_load_valid_csv(tmp_path: Path) -> None:
    csv_file = tmp_path / "shipments.csv"
    csv_file.write_text(
        "shipment_id,warehouse_id,status\nS1,W1,delivered\nS2,W2,delayed\n",
        encoding="utf-8",
    )

    df = load_csv(csv_file)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["shipment_id", "warehouse_id", "status"]
    assert len(df) == 2
    # Source data preserved as-is (no cleaning/normalization).
    assert df.iloc[0]["shipment_id"] == "S1"


def test_load_valid_json_array(tmp_path: Path) -> None:
    json_file = tmp_path / "delays.json"
    json_file.write_text(
        '[{"shipment_id": "S1", "delay_duration": 30},'
        ' {"shipment_id": "S2", "delay_duration": 45}]',
        encoding="utf-8",
    )

    df = load_json(json_file)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert set(df.columns) == {"shipment_id", "delay_duration"}


def test_load_dataset_dispatches_by_extension(tmp_path: Path) -> None:
    csv_file = tmp_path / "a.csv"
    csv_file.write_text("x\n1\n", encoding="utf-8")
    json_file = tmp_path / "b.json"
    json_file.write_text('[{"x": 1}]', encoding="utf-8")

    assert len(load_dataset(csv_file)) == 1
    assert len(load_dataset(json_file)) == 1


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        load_csv(missing)
    with pytest.raises(FileNotFoundError):
        load_json(tmp_path / "does_not_exist.json")
    with pytest.raises(FileNotFoundError):
        load_dataset(missing)


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "data.xlsx"
    bad_file.write_text("not a real xlsx", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError, match=r"\.xlsx"):
        load_dataset(bad_file)

    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("hello", encoding="utf-8")
    with pytest.raises(UnsupportedFileTypeError):
        load_dataset(txt_file)


def test_basic_metadata(tmp_path: Path) -> None:
    csv_file = tmp_path / "scans.csv"
    csv_file.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
    df = load_csv(csv_file)

    metadata = get_dataset_metadata(df, csv_file)

    assert metadata["filename"] == "scans.csv"
    assert metadata["file_type"] == ".csv"
    assert metadata["row_count"] == 2
    assert metadata["column_count"] == 3
    assert metadata["columns"] == ["a", "b", "c"]


def test_malformed_json_raises_dataset_load_error(tmp_path: Path) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(DatasetLoadError):
        load_json(bad_json)


def test_empty_json_raises_dataset_load_error(tmp_path: Path) -> None:
    empty_json = tmp_path / "empty.json"
    empty_json.write_text("", encoding="utf-8")

    with pytest.raises(DatasetLoadError):
        load_json(empty_json)


def test_malformed_csv_raises_dataset_load_error(tmp_path: Path) -> None:
    # An empty CSV has no header/rows for pandas to parse.
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")

    with pytest.raises(DatasetLoadError):
        load_csv(empty_csv)


def test_discover_datasets_returns_only_supported_sorted(tmp_path: Path) -> None:
    (tmp_path / "b.json").write_text("[]", encoding="utf-8")
    (tmp_path / "a.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
    (tmp_path / "workbook.xlsx").write_text("ignore me", encoding="utf-8")

    found = discover_datasets(tmp_path)

    assert [entry.name for entry in found] == ["a.csv", "b.json"]


def test_discover_datasets_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert discover_datasets(tmp_path / "no_such_dir") == []


def test_loading_does_not_modify_source_file(tmp_path: Path) -> None:
    csv_file = tmp_path / "raw.csv"
    content = "shipment_id,status\nS1,delayed\n"
    csv_file.write_text(content, encoding="utf-8")

    load_dataset(csv_file)

    assert csv_file.read_text(encoding="utf-8") == content
