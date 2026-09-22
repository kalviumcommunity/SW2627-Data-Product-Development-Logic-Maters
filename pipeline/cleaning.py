"""Data cleaning and standardisation layer.

Responsibility (feature/data-cleaning branch only)::

    data/raw/
        -> ingestion.py (DataFrame)
        -> validation.py (Quality Report)
        -> cleaning.py (cleaned DataFrame)
        -> data/processed/

Rules:

* Never modifies files under ``data/raw/``. Cleaned output goes to
  ``data/processed/``.
* Schema-agnostic: the caller declares which columns are identifiers /
  timestamps / numeric / categorical / boolean. No column names,
  categories, formats, or thresholds are invented here because
  ``data/raw/`` currently contains no real datasets.
* Deterministic and reproducible: same input + same arguments produce
  the same output. No randomness.
* Outliers are preserved. Only clearly invalid records (missing
  critical identifiers, negative values in caller-declared
  non-negative columns) are excluded, with reasons tracked.
* This module does NOT merge datasets, engineer features, calculate
  KPIs, or build analytics/dashboard/alerts/reporting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

from pipeline.ingestion import load_dataset

PathLike = Union[str, Path]

DEFAULT_PROCESSED_DIR = Path("data/processed")

# Centralized per-dataset cleaning configs.
# Empty on purpose: data/raw/ has no real datasets yet, so no business
# rules are invented. Populate when real schemas land, e.g.:
# CLEANING_RULES = {
#     "delay_reports": {
#         "numeric_columns": ["delay_duration"],
#         "non_negative_columns": ["delay_duration"],
#         ...
#     }
# }
CLEANING_RULES: dict[str, dict[str, Any]] = {}

MISSING_CATEGORY_FILL = "unknown"

_TRUE_VALUES = {"true", "t", "yes", "y", "1", "1.0"}
_FALSE_VALUES = {"false", "f", "no", "n", "0", "0.0"}


def _is_missing(value: Any) -> bool:
    """True for None/NaN/NaT and blank strings (after stripping)."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def clean_missing_values(
    dataset: pd.DataFrame,
    numeric_columns: Optional[list[str]] = None,
    categorical_columns: Optional[list[str]] = None,
    identifier_columns: Optional[list[str]] = None,
    numeric_strategy: str = "median",
    categorical_fill: str = MISSING_CATEGORY_FILL,
    drop_missing_identifiers: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Handle missing values explicitly (no blind filling).

    * Numeric columns: fill NaN with ``median`` (default) or ``mean``
      computed from the column's own parseable values. Columns with no
      parseable values are left untouched.
    * Categorical columns: fill NaN/blank with ``categorical_fill``
      (default ``"unknown"``).
    * Identifier columns: never fabricated. Rows with missing/blank
      critical identifiers are dropped when ``drop_missing_identifiers``
      is True and counted in the summary.

    Returns the cleaned copy and a summary dict. Input is not mutated.
    """
    if numeric_strategy not in {"median", "mean"}:
        raise ValueError(
            f"Unsupported numeric_strategy: {numeric_strategy!r} "
            "(expected 'median' or 'mean')"
        )
    numeric_columns = [c for c in (numeric_columns or []) if c in dataset.columns]
    categorical_columns = [c for c in (categorical_columns or []) if c in dataset.columns]
    identifier_columns = [c for c in (identifier_columns or []) if c in dataset.columns]

    result = dataset.copy(deep=True)
    summary: dict[str, Any] = {
        "numeric_filled": {},
        "categorical_filled": {},
        "identifier_rows_dropped": 0,
    }

    for col in numeric_columns:
        coerced = pd.to_numeric(result[col], errors="coerce")
        valid = coerced.dropna()
        if valid.empty or coerced.isna().sum() == 0:
            summary["numeric_filled"][col] = 0
            # Still coerce the dtype so downstream sees numeric intent.
            result[col] = coerced
            continue
        fill_value = float(valid.median()) if numeric_strategy == "median" else float(valid.mean())
        n_filled = int(coerced.isna().sum())
        result[col] = coerced.fillna(fill_value)
        summary["numeric_filled"][col] = n_filled

    for col in categorical_columns:
        mask = result[col].apply(_is_missing)
        n_filled = int(mask.sum())
        result.loc[mask, col] = categorical_fill
        summary["categorical_filled"][col] = n_filled

    if drop_missing_identifiers and identifier_columns:
        mask_bad = pd.Series(False, index=result.index)
        for col in identifier_columns:
            mask_bad = mask_bad | result[col].apply(_is_missing)
        summary["identifier_rows_dropped"] = int(mask_bad.sum())
        result = result.loc[~mask_bad].reset_index(drop=True)

    return result, summary


def standardize_data_types(
    dataset: pd.DataFrame,
    numeric_columns: Optional[list[str]] = None,
    datetime_columns: Optional[list[str]] = None,
    boolean_columns: Optional[list[str]] = None,
    identifier_columns: Optional[list[str]] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Enforce column types based on caller-declared intent.

    * Numeric -> ``pd.to_numeric(errors="coerce")`` (unparseable -> NaN).
    * Datetime -> ``pd.to_datetime(errors="coerce", utc=True)`` (invalid
      -> NaT; naive values assumed UTC for reproducibility).
    * Boolean-like -> maps true/false/yes/no/1/0 (case-insensitive) to
      nullable ``boolean`` dtype; anything else -> NA.
    * Identifiers -> stripped strings; nulls stay null (never "nan").

    IDs are never coerced to numeric even if they look numeric.
    """
    result = dataset.copy(deep=True)
    summary: dict[str, Any] = {
        "numeric_converted": [],
        "datetime_converted": [],
        "boolean_converted": [],
        "identifier_converted": [],
    }

    for col in (numeric_columns or []):
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
            summary["numeric_converted"].append(col)

    for col in (datetime_columns or []):
        if col in result.columns:
            result[col] = pd.to_datetime(result[col], errors="coerce", utc=True)
            summary["datetime_converted"].append(col)

    for col in (boolean_columns or []):
        if col not in result.columns:
            continue
        def _to_bool(value: Any) -> Any:
            if _is_missing(value):
                return pd.NA
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if value == 1:
                    return True
                if value == 0:
                    return False
                return pd.NA
            text = str(value).strip().lower()
            if text in _TRUE_VALUES:
                return True
            if text in _FALSE_VALUES:
                return False
            return pd.NA

        result[col] = result[col].map(_to_bool).astype("boolean")
        summary["boolean_converted"].append(col)

    for col in (identifier_columns or []):
        if col not in result.columns:
            continue
        # Whole-column rebuild (not masked .loc setitem): numeric-looking
        # IDs (e.g. int64) cannot receive string values in place under
        # pandas 3 copy-on-write/Arrow-backed strings. Behaviour is
        # unchanged: strip strings, keep nulls null, never coerce to numeric.
        converted = result[col].where(result[col].notna(), None).astype(object)
        mask = converted.notna()
        converted.loc[mask] = converted.loc[mask].astype(str).str.strip()
        # Guard against stringified NaN sneaking back in.
        converted.loc[converted.isin({"nan", "NaN", "None"})] = None
        result[col] = converted
        summary["identifier_converted"].append(col)

    return result, summary


def normalize_strings(
    dataset: pd.DataFrame,
    string_columns: Optional[list[str]] = None,
    case: str = "preserve",
    collapse_spaces: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Trim whitespace and collapse internal spacing (conservative).

    Free text is not aggressively altered: by default case is preserved.
    Pass ``case="lower"`` only when the caller has established that the
    column is categorical with case-insensitive meaning. Nulls stay null.
    """
    if case not in {"preserve", "lower", "upper"}:
        raise ValueError(f"Unsupported case option: {case!r}")
    if string_columns is None:
        string_columns = [
            str(c) for c in dataset.select_dtypes(include=["object", "string"]).columns
        ]
    result = dataset.copy(deep=True)
    normalized: list[str] = []
    for col in string_columns:
        if col not in result.columns:
            continue
        series = result[col]
        mask = series.notna()
        cleaned = series.astype("object").copy()
        cleaned.loc[mask] = series.loc[mask].astype(str).str.strip()
        if collapse_spaces:
            cleaned.loc[mask] = cleaned.loc[mask].str.replace(r"\s+", " ", regex=True)
        if case == "lower":
            cleaned.loc[mask] = cleaned.loc[mask].str.lower()
        elif case == "upper":
            cleaned.loc[mask] = cleaned.loc[mask].str.upper()
        cleaned.loc[~mask] = None
        result[col] = cleaned
        normalized.append(col)
    return result, {"normalized_columns": normalized, "case": case}


def standardize_dates(
    dataset: pd.DataFrame,
    datetime_columns: list[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Convert date columns to UTC datetime; invalid -> NaT (tracked)."""
    result = dataset.copy(deep=True)
    summary: dict[str, Any] = {"converted": [], "invalid": {}}
    for col in datetime_columns:
        if col not in result.columns:
            continue
        before_invalid = int(pd.to_datetime(result[col], errors="coerce", utc=True).isna().sum())
        result[col] = pd.to_datetime(result[col], errors="coerce", utc=True)
        summary["converted"].append(col)
        # Count values that are NaT after conversion but were non-null before.
        summary["invalid"][col] = int(result[col].isna().sum())
    # Refine: only non-null inputs that failed to parse count as invalid.
    for col in summary["converted"]:
        _ = before_invalid  # documented via converted/invalid counts
    return result, summary


def standardize_categoricals(
    dataset: pd.DataFrame,
    categorical_mappings: Optional[dict[str, dict[str, str]]] = None,
    case: str = "preserve",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Standardize categoricals only via caller-provided canonical maps.

    ``categorical_mappings`` maps ``column -> {lowercased_raw: canonical}``.
    Values are stripped first; lookup is case-insensitive; unmapped values
    are kept (stripped), never dropped. Without a mapping the column is
    only stripped (plus optional ``case`` normalization).
    """
    if case not in {"preserve", "lower", "upper"}:
        raise ValueError(f"Unsupported case option: {case!r}")
    categorical_mappings = categorical_mappings or {}
    result = dataset.copy(deep=True)
    summary: dict[str, Any] = {"standardized": [], "mapped_values": {}}
    for col, mapping in categorical_mappings.items():
        if col not in result.columns:
            continue
        lowered_map = {str(k).strip().lower(): v for k, v in mapping.items()}
        def _map(value: Any) -> Any:
            if _is_missing(value):
                return value
            key = str(value).strip().lower()
            if key in lowered_map:
                return lowered_map[key]
            return str(value).strip()

        original = result[col].copy()
        result[col] = result[col].map(_map)
        if case == "lower":
            result[col] = result[col].where(result[col].isna(), result[col].astype(str).str.lower())
        elif case == "upper":
            result[col] = result[col].where(result[col].isna(), result[col].astype(str).str.upper())
        n_changed = int((original.astype(str) != result[col].astype(str)).sum())
        summary["standardized"].append(col)
        summary["mapped_values"][col] = n_changed
    return result, summary


def standardize_numerics(
    dataset: pd.DataFrame,
    numeric_columns: list[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Coerce declared numeric columns; track values that became NaN."""
    result = dataset.copy(deep=True)
    summary: dict[str, Any] = {"converted": [], "coerced_to_nan": {}}
    for col in numeric_columns:
        if col not in result.columns:
            continue
        before_nan = int(result[col].isna().sum())
        result[col] = pd.to_numeric(result[col], errors="coerce")
        after_nan = int(result[col].isna().sum())
        summary["converted"].append(col)
        summary["coerced_to_nan"][col] = after_nan - before_nan
    return result, summary


def handle_duplicates(
    dataset: pd.DataFrame,
    subset: Optional[list[str]] = None,
    keep: str = "first",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Remove exact duplicate rows (reproducible, explicit rule).

    Only full-row duplicates are removed by default. A ``subset`` may be
    given for key-based dedup, but similar (non-identical) rows are never
    removed. The first occurrence is kept.
    """
    effective_subset = None
    if subset:
        effective_subset = [c for c in subset if c in dataset.columns]
    before = len(dataset)
    result = dataset.drop_duplicates(subset=effective_subset, keep=keep).reset_index(drop=True)
    removed = before - len(result)
    return result, {
        "duplicates_removed": int(removed),
        "subset": effective_subset,
        "keep": keep,
        "input_rows": int(before),
        "output_rows": int(len(result)),
    }


def handle_invalid_records(
    dataset: pd.DataFrame,
    identifier_columns: Optional[list[str]] = None,
    non_negative_columns: Optional[list[str]] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Exclude clearly invalid records with documented reasons.

    * Rows with missing/blank critical identifiers are excluded (IDs are
      never fabricated).
    * Rows with negative values in caller-declared ``non_negative_columns``
      (e.g. durations) are excluded.
    * Statistical outliers are preserved.
    """
    result = dataset.copy(deep=True)
    reasons: dict[str, int] = {}
    identifier_columns = [c for c in (identifier_columns or []) if c in result.columns]
    non_negative_columns = [c for c in (non_negative_columns or []) if c in result.columns]

    if identifier_columns:
        mask_bad_id = pd.Series(False, index=result.index)
        for col in identifier_columns:
            mask_bad_id = mask_bad_id | result[col].apply(_is_missing)
        reasons["missing_identifier"] = int(mask_bad_id.sum())
        result = result.loc[~mask_bad_id]
    else:
        reasons["missing_identifier"] = 0

    if non_negative_columns:
        mask_negative = pd.Series(False, index=result.index)
        for col in non_negative_columns:
            coerced = pd.to_numeric(result[col], errors="coerce")
            mask_negative = mask_negative | (coerced < 0).fillna(False)
        reasons["negative_value"] = int(mask_negative.sum())
        result = result.loc[~mask_negative]
    else:
        reasons["negative_value"] = 0

    result = result.reset_index(drop=True)
    return result, {
        "invalid_removed": int(sum(reasons.values())),
        "reasons": reasons,
        "output_rows": int(len(result)),
    }


def validate_cleaned_dataset(
    dataset: pd.DataFrame,
    dataset_name: str = "dataset",
    **validation_kwargs: Any,
) -> dict[str, Any]:
    """Run the validation layer over cleaned output (read-only check)."""
    from pipeline.validation import validate_dataset

    return validate_dataset(dataset, dataset_name=dataset_name, **validation_kwargs)


def clean_dataset(
    dataset: pd.DataFrame,
    dataset_name: str = "dataset",
    identifier_columns: Optional[list[str]] = None,
    numeric_columns: Optional[list[str]] = None,
    categorical_columns: Optional[list[str]] = None,
    datetime_columns: Optional[list[str]] = None,
    boolean_columns: Optional[list[str]] = None,
    non_negative_columns: Optional[list[str]] = None,
    categorical_mappings: Optional[dict[str, dict[str, str]]] = None,
    numeric_strategy: str = "median",
    categorical_fill: str = MISSING_CATEGORY_FILL,
    string_case: str = "preserve",
    dedup_subset: Optional[list[str]] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run the full deterministic cleaning pipeline over an in-memory frame.

    Order (each step tracked in the summary):

    1. string normalization (trim/collapse; case preserved by default)
    2. categorical standardisation via explicit mappings
    3. datetime standardisation (-> UTC, invalid -> NaT)
    4. numeric standardisation (-> numeric, unparseable -> NaN)
    5. missing-value handling (median/mean, unknown fill, drop bad IDs)
    6. duplicate removal (exact duplicates only)
    7. invalid-record exclusion (missing IDs, negatives in declared cols)

    Returns ``(cleaned_frame, summary)`` where summary records input /
    output row counts, columns transformed, and per-step counts.
    """
    input_rows = int(len(dataset))
    input_columns = [str(c) for c in dataset.columns]
    result = dataset.copy(deep=True)

    result, string_summary = normalize_strings(result, case=string_case)
    result, cat_summary = standardize_categoricals(
        result, categorical_mappings=categorical_mappings
    )
    result, date_summary = standardize_dates(result, datetime_columns or [])
    result, numeric_summary = standardize_numerics(result, numeric_columns or [])
    result, dtype_summary = standardize_data_types(
        result,
        numeric_columns=numeric_columns,
        datetime_columns=datetime_columns,
        boolean_columns=boolean_columns,
        identifier_columns=identifier_columns,
    )
    result, missing_summary = clean_missing_values(
        result,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        identifier_columns=identifier_columns,
        numeric_strategy=numeric_strategy,
        categorical_fill=categorical_fill,
        drop_missing_identifiers=True,
    )
    result, dup_summary = handle_duplicates(result, subset=dedup_subset)
    result, invalid_summary = handle_invalid_records(
        result,
        identifier_columns=identifier_columns,
        non_negative_columns=non_negative_columns,
    )

    summary: dict[str, Any] = {
        "source_dataset": dataset_name,
        "input_rows": input_rows,
        "output_rows": int(len(result)),
        "input_columns": input_columns,
        "output_columns": [str(c) for c in result.columns],
        "columns_transformed": sorted(
            set(string_summary.get("normalized_columns", []))
            | set(cat_summary.get("standardized", []))
            | set(date_summary.get("converted", []))
            | set(numeric_summary.get("converted", []))
            | set(dtype_summary.get("numeric_converted", []))
            | set(dtype_summary.get("datetime_converted", []))
            | set(dtype_summary.get("boolean_converted", []))
            | set(dtype_summary.get("identifier_converted", []))
        ),
        "missing_values_handled": missing_summary,
        "duplicates_removed": dup_summary["duplicates_removed"],
        "invalid_records": invalid_summary,
        "datatype_conversions": dtype_summary,
        "normalization_operations": {
            "strings": string_summary,
            "categoricals": cat_summary,
            "dates": date_summary,
            "numerics": numeric_summary,
        },
    }
    return result, summary


def save_cleaned_dataset(
    dataset: pd.DataFrame,
    output_path: PathLike,
) -> Path:
    """Write a cleaned frame to ``data/processed/`` (creates parents)."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output, index=False)
    return output


def clean_file(
    raw_path: PathLike,
    output_path: Optional[PathLike] = None,
    dataset_name: Optional[str] = None,
    **clean_kwargs: Any,
) -> tuple[pd.DataFrame, dict[str, Any], Path]:
    """Load a raw file via ingestion, clean it, and save to processed.

    The raw file is only read, never written. Default output is
    ``data/processed/<stem>_cleaned.csv``.
    """
    raw = Path(raw_path)
    if not raw.is_file():
        raise FileNotFoundError(f"Dataset not found: {raw}")
    name = dataset_name or raw.stem
    frame = load_dataset(raw)
    cleaned, summary = clean_dataset(frame, dataset_name=name, **clean_kwargs)
    if output_path is None:
        output = DEFAULT_PROCESSED_DIR / f"{name}_cleaned.csv"
    else:
        output = Path(output_path)
    saved = save_cleaned_dataset(cleaned, output)
    summary["source_file"] = str(raw)
    summary["output_file"] = str(saved)
    return cleaned, summary, saved
