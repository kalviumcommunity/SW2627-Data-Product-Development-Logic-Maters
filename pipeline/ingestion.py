"""Data ingestion layer for Cascading Delay Intelligence.

Responsibility (feature/data-ingestion branch only)::

    data/raw/
        -> file discovery
        -> file loading (CSV / JSON)
        -> basic schema inspection
        -> in-memory pandas DataFrame

This module intentionally does NOT implement validation, cleaning,
integration, analytics, KPIs, or dashboard logic. It preserves source
data as-is and never modifies files under ``data/raw/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

import pandas as pd

PathLike = Union[str, Path]

SUPPORTED_SUFFIXES = {".csv", ".json"}

DEFAULT_RAW_DIR = Path("data/raw")


class UnsupportedFileTypeError(ValueError):
    """Raised when a dataset file extension is not supported."""


class DatasetLoadError(RuntimeError):
    """Raised when a supported dataset file cannot be parsed."""


def _resolve_existing_file(path: PathLike) -> Path:
    """Return ``path`` as a :class:`Path` if it exists and is a file.

    Raises:
        FileNotFoundError: If the path does not exist or is not a file.
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Dataset not found: {resolved}")
    return resolved


def load_csv(path: PathLike, encoding: str = "utf-8", **kwargs) -> pd.DataFrame:
    """Load a CSV file into a DataFrame without modifying its content.

    Args:
        path: Path to the ``.csv`` file.
        encoding: Text encoding passed to :func:`pandas.read_csv`.
        **kwargs: Additional keyword arguments forwarded to
            :func:`pandas.read_csv` for future configuration.

    Raises:
        FileNotFoundError: If the file does not exist.
        DatasetLoadError: If the file cannot be parsed as CSV.
    """
    resolved = _resolve_existing_file(path)
    try:
        return pd.read_csv(resolved, encoding=encoding, **kwargs)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise DatasetLoadError(
            f"Failed to load CSV dataset: {resolved} ({exc})"
        ) from exc


def load_json(path: PathLike, encoding: str = "utf-8") -> pd.DataFrame:
    """Load a JSON file into a DataFrame without modifying its content.

    Supported shapes (kept minimal on purpose):

    * JSON array of objects: ``[{"a": 1}, {"a": 2}]``
    * Column-oriented object: ``{"a": [1, 2], "b": [3, 4]}``
    * Single-key wrapped array: ``{"shipments": [{...}, {...}]}``
      (the inner list is used as the record list)
    * JSON Lines (one JSON object per line) as a fallback.

    Args:
        path: Path to the ``.json`` file.
        encoding: Text encoding used to read the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        DatasetLoadError: If the file cannot be parsed as JSON/tabular data.
    """
    resolved = _resolve_existing_file(path)
    try:
        text = resolved.read_text(encoding=encoding)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise DatasetLoadError(
            f"Failed to read JSON dataset: {resolved} ({exc})"
        ) from exc

    if not text.strip():
        raise DatasetLoadError(f"Failed to load JSON dataset: {resolved} (empty file)")

    # First attempt: standard JSON document.
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: JSON Lines (one object per line).
        try:
            records = [
                json.loads(line)
                for line in text.splitlines()
                if line.strip()
            ]
            if not records:
                raise DatasetLoadError(
                    f"Failed to load JSON dataset: {resolved} (no valid JSON records)"
                )
            return pd.DataFrame(records)
        except DatasetLoadError:
            raise
        except Exception as exc:
            raise DatasetLoadError(
                f"Failed to load JSON dataset: {resolved} ({exc})"
            ) from exc

    try:
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, dict):
            # Single-key wrapped array, e.g. {"shipments": [{...}]}.
            if len(payload) == 1:
                sole_value = next(iter(payload.values()))
                if isinstance(sole_value, list) and (
                    not sole_value
                    or all(isinstance(item, dict) for item in sole_value)
                ):
                    return pd.DataFrame(sole_value)
            return pd.DataFrame(payload)
        raise DatasetLoadError(
            f"Failed to load JSON dataset: {resolved} "
            f"(unsupported top-level JSON type: {type(payload).__name__})"
        )
    except DatasetLoadError:
        raise
    except Exception as exc:
        raise DatasetLoadError(
            f"Failed to load JSON dataset: {resolved} ({exc})"
        ) from exc


def load_dataset(path: PathLike, encoding: str = "utf-8", **kwargs) -> pd.DataFrame:
    """Load a supported dataset file into a DataFrame.

    Dispatches on file extension:

    * ``.csv`` -> :func:`load_csv`
    * ``.json`` -> :func:`load_json`

    Args:
        path: Path to the dataset file.
        encoding: Text encoding forwarded to the format-specific loader.
        **kwargs: Forwarded to :func:`load_csv` for CSV files.

    Raises:
        FileNotFoundError: If the file does not exist.
        UnsupportedFileTypeError: If the file extension is not supported.
        DatasetLoadError: If the file cannot be parsed.
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Dataset not found: {resolved}")
    suffix = resolved.suffix.lower()
    if suffix == ".csv":
        return load_csv(resolved, encoding=encoding, **kwargs)
    if suffix == ".json":
        return load_json(resolved, encoding=encoding)
    raise UnsupportedFileTypeError(f"Unsupported dataset format: {suffix or '(none)'}")


def discover_datasets(raw_dir: PathLike = DEFAULT_RAW_DIR) -> list[Path]:
    """Discover supported dataset files inside the raw data directory.

    Only top-level ``.csv`` and ``.json`` files are returned. Unsupported
    files are ignored. Results are sorted by filename for predictability.

    Args:
        raw_dir: Directory to scan (defaults to ``data/raw``).

    Returns:
        Sorted list of dataset file paths. Empty if the directory does
        not exist or contains no supported files.
    """
    directory = Path(raw_dir)
    if not directory.is_dir():
        return []
    return sorted(
        (
            entry
            for entry in directory.iterdir()
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda entry: entry.name,
    )


def get_dataset_metadata(dataset: pd.DataFrame, path: PathLike) -> dict:
    """Return basic file-level metadata for an in-memory dataset.

    Only structural information is reported — no analytical statistics,
    KPIs, or cleaning summaries.

    Args:
        dataset: Loaded DataFrame.
        path: Original source file path (used for filename/file_type).

    Returns:
        Dict with ``filename``, ``file_type``, ``row_count``,
        ``column_count`` and ``columns``.
    """
    source = Path(path)
    return {
        "filename": source.name,
        "file_type": source.suffix.lower(),
        "row_count": int(len(dataset)),
        "column_count": int(len(dataset.columns)),
        "columns": [str(column) for column in dataset.columns],
    }
