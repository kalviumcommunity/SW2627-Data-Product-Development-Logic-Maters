"""Dataset profiling and data-quality validation layer.

Responsibility (feature/data-quality branch only)::

    data/raw/
        -> ingestion.py (DataFrame)
        -> validation.py (Quality Report)

This module only detects and reports problems. It never cleans data:
no filling missing values, no deduplication, no string normalization,
no type conversion, no outlier removal, no merging, no feature creation,
and never modifies files under ``data/raw/``.

All checks are reusable and schema-agnostic. Caller supplies which
columns are identifiers / timestamps / numeric / categorical, because
``data/raw/`` currently contains no real datasets to derive rules from.
"""

from __future__ import annotations

from typing import Any, Optional, Union

import pandas as pd

# Centralized dataset-specific rules.
# Empty on purpose: data/raw/ currently has no real datasets, so no
# business rules are invented here. Populate per dataset when real
# schemas are available, e.g.:
# VALIDATION_RULES = {
#     "shipment_scans": {"required_columns": ["shipment_id", "timestamp"]},
# }
VALIDATION_RULES: dict[str, dict[str, Any]] = {}


def profile_dataset(dataset: pd.DataFrame, dataset_name: str = "dataset") -> dict[str, Any]:
    """Return structural profile of a DataFrame (no business analytics).

    Reports row/column counts, columns, dtypes, missing values,
    uniqueness, duplicates, plus numeric and categorical summaries.
    """
    row_count = int(len(dataset))
    columns = [str(col) for col in dataset.columns]

    dtypes = {str(col): str(dataset[col].dtype) for col in dataset.columns}

    missing_counts = {str(col): int(dataset[col].isna().sum()) for col in dataset.columns}
    missing_pct = {
        col: (count / row_count * 100.0 if row_count else 0.0)
        for col, count in missing_counts.items()
    }
    unique_counts = {str(col): int(dataset[col].nunique(dropna=True)) for col in dataset.columns}

    duplicate_row_count = int(dataset.duplicated().sum()) if row_count else 0
    duplicate_pct = duplicate_row_count / row_count * 100.0 if row_count else 0.0

    numeric_summary: dict[str, dict[str, Any]] = {}
    for col in dataset.select_dtypes(include="number").columns:
        series = dataset[col].dropna()
        key = str(col)
        if series.empty:
            numeric_summary[key] = {
                "min": None,
                "max": None,
                "mean": None,
                "median": None,
            }
        else:
            numeric_summary[key] = {
                "min": float(series.min()),
                "max": float(series.max()),
                "mean": float(series.mean()),
                "median": float(series.median()),
            }

    categorical_summary: dict[str, dict[str, Any]] = {}
    for col in dataset.select_dtypes(include=["object", "category", "string"]).columns:
        key = str(col)
        non_null = dataset[col].dropna()
        top_values = non_null.value_counts().head(5).to_dict()
        categorical_summary[key] = {
            "unique_count": int(dataset[col].nunique(dropna=True)),
            "most_frequent": {str(k): int(v) for k, v in top_values.items()},
        }

    return {
        "dataset": dataset_name,
        "row_count": row_count,
        "column_count": int(len(dataset.columns)),
        "columns": columns,
        "dtypes": dtypes,
        "missing": missing_counts,
        "missing_pct": missing_pct,
        "unique_counts": unique_counts,
        "duplicate_row_count": duplicate_row_count,
        "duplicate_pct": duplicate_pct,
        "numeric_summary": numeric_summary,
        "categorical_summary": categorical_summary,
    }


def check_missing_values(dataset: pd.DataFrame) -> pd.DataFrame:
    """Report missing values per column (detection only, no filling)."""
    row_count = len(dataset)
    rows = []
    for col in dataset.columns:
        missing = int(dataset[col].isna().sum())
        pct = missing / row_count * 100.0 if row_count else 0.0
        rows.append({"column": str(col), "missing": missing, "missing_pct": pct})
    result = pd.DataFrame(rows, columns=["column", "missing", "missing_pct"])
    return result


def check_duplicates(
    dataset: pd.DataFrame, subset: Optional[list[str]] = None
) -> dict[str, Any]:
    """Report duplicate rows (detection only, no removal)."""
    row_count = len(dataset)
    if subset:
        existing = [col for col in subset if col in dataset.columns]
        dup_count = int(dataset.duplicated(subset=existing).sum()) if existing else 0
    else:
        dup_count = int(dataset.duplicated().sum()) if row_count else 0
    return {
        "subset": list(subset) if subset else None,
        "duplicate_rows": dup_count,
        "duplicate_pct": dup_count / row_count * 100.0 if row_count else 0.0,
        "row_count": int(row_count),
    }


def check_required_columns(
    dataset: pd.DataFrame, required_columns: list[str]
) -> dict[str, Any]:
    """Check that required columns are present (no invention of schema)."""
    present = set(str(col) for col in dataset.columns)
    missing = [col for col in required_columns if col not in present]
    return {
        "required": list(required_columns),
        "missing": missing,
        "present": len(missing) == 0,
    }


def check_data_types(
    dataset: pd.DataFrame, expected_types: dict[str, str]
) -> dict[str, Any]:
    """Flag columns whose dtype does not match the expected kind.

    ``expected_types`` maps column name to one of
    ``{"numeric", "datetime", "string", "bool"}``. Columns absent from
    the DataFrame are reported as missing, not coerced.
    """
    mismatches: list[dict[str, str]] = []
    missing: list[str] = []
    for col, expected in expected_types.items():
        if col not in dataset.columns:
            missing.append(col)
            continue
        series = dataset[col]
        actual = str(series.dtype)
        ok = False
        if expected == "numeric":
            ok = pd.api.types.is_numeric_dtype(series)
        elif expected == "datetime":
            ok = pd.api.types.is_datetime64_any_dtype(series)
        elif expected == "bool":
            ok = pd.api.types.is_bool_dtype(series)
        elif expected == "string":
            ok = pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)
        else:
            ok = expected.lower() in actual.lower()
        if not ok:
            mismatches.append({"column": col, "expected": expected, "actual": actual})
    return {"mismatches": mismatches, "missing_columns": missing, "passed": not mismatches and not missing}


def check_identifiers(
    dataset: pd.DataFrame, identifier_columns: list[str]
) -> dict[str, dict[str, Any]]:
    """Check identifier columns for nulls / empty strings (no format invention)."""
    result: dict[str, dict[str, Any]] = {}
    row_count = len(dataset)
    for col in identifier_columns:
        if col not in dataset.columns:
            result[col] = {
                "exists": False,
                "missing": row_count,
                "missing_pct": 100.0 if row_count else 0.0,
                "empty_strings": 0,
                "completely_empty": True,
            }
            continue
        series = dataset[col]
        missing = int(series.isna().sum())
        empty_strings = int((series.astype(str) == "").sum() - series.isna().sum()) if row_count else 0
        # Above: count "" only among non-null; astype(str) turns NaN into "nan"/"",
        # so subtract nulls defensively and clamp at 0.
        empty_strings = max(empty_strings, 0)
        # A column of all "" (non-null) is also effectively empty.
        non_null = series.dropna()
        all_blank = bool(row_count) and (missing == row_count or (not non_null.empty and (non_null.astype(str).str.strip() == "").all()))
        result[col] = {
            "exists": True,
            "missing": missing,
            "missing_pct": missing / row_count * 100.0 if row_count else 0.0,
            "empty_strings": empty_strings,
            "completely_empty": all_blank,
        }
    return result


def check_timestamps(
    dataset: pd.DataFrame, timestamp_columns: list[str]
) -> dict[str, dict[str, Any]]:
    """Check timestamp columns for missing / unparsable values (no conversion)."""
    result: dict[str, dict[str, Any]] = {}
    for col in timestamp_columns:
        if col not in dataset.columns:
            result[col] = {
                "exists": False,
                "missing": int(len(dataset)),
                "unparsable": 0,
                "unparsable_pct": 0.0,
                "examples": [],
            }
            continue
        series = dataset[col]
        missing = int(series.isna().sum())
        non_null = series.dropna()
        if non_null.empty:
            result[col] = {
                "exists": True,
                "missing": missing,
                "unparsable": 0,
                "unparsable_pct": 0.0,
                "examples": [],
            }
            continue
        if pd.api.types.is_datetime64_any_dtype(series):
            unparsable = 0
            examples: list[str] = []
        else:
            parsed = pd.to_datetime(non_null, errors="coerce")
            mask_bad = parsed.isna()
            unparsable = int(mask_bad.sum())
            examples = [str(v) for v in non_null[mask_bad].head(5).tolist()]
        result[col] = {
            "exists": True,
            "missing": missing,
            "unparsable": unparsable,
            "unparsable_pct": unparsable / len(non_null) * 100.0 if len(non_null) else 0.0,
            "examples": examples,
        }
    return result


def check_numeric_values(
    dataset: pd.DataFrame, numeric_columns: list[str]
) -> dict[str, dict[str, Any]]:
    """Check expected-numeric columns for non-numeric / negative values.

    Statistical extremes are NOT flagged as invalid; only clearly
    non-numeric entries and negative values (impossible for durations)
    are reported for caller review.
    """
    result: dict[str, dict[str, Any]] = {}
    for col in numeric_columns:
        if col not in dataset.columns:
            result[col] = {
                "exists": False,
                "non_numeric": 0,
                "negative": 0,
            }
            continue
        series = dataset[col]
        coerced = pd.to_numeric(series, errors="coerce")
        non_null = series.dropna()
        non_numeric = int(coerced.isna().sum() - series.isna().sum())
        non_numeric = max(non_numeric, 0)
        negative = int((coerced.dropna() < 0).sum())
        void_note = ""
        if not non_null.empty and coerced.dropna().empty:
            void_note = "no parseable numeric values"
        result[col] = {
            "exists": True,
            "non_numeric": non_numeric,
            "negative": negative,
            "note": void_note,
        }
    return result


def check_categoricals(
    dataset: pd.DataFrame,
    categorical_columns: list[str],
    allowed_values: Optional[dict[str, list[str]]] = None,
) -> dict[str, dict[str, Any]]:
    """Inspect categorical columns without normalizing them.

    Reports unique values, nulls, case inconsistencies (e.g. Delayed /
    delayed / DELAYED collapsing to one key), and unexpected categories
    only when an explicit allowed set is provided.
    """
    allowed_values = allowed_values or {}
    result: dict[str, dict[str, Any]] = {}
    for col in categorical_columns:
        if col not in dataset.columns:
            result[col] = {
                "exists": False,
                "unique_values": [],
                "unique_count": 0,
                "nulls": int(len(dataset)),
                "case_inconsistencies": {},
                "unexpected": [],
            }
            continue
        series = dataset[col]
        nulls = int(series.isna().sum())
        uniques = series.dropna().astype(str).unique().tolist()
        # Case-insensitive collisions indicate inconsistent capitalization.
        lowered: dict[str, list[str]] = {}
        for value in uniques:
            lowered.setdefault(value.strip().lower(), []).append(value)
        inconsistencies = {
            key: variants for key, variants in lowered.items() if len(variants) > 1
        }
        unexpected: list[str] = []
        if col in allowed_values:
            allowed = set(allowed_values[col])
            unexpected = [v for v in uniques if v not in allowed]
        result[col] = {
            "exists": True,
            "unique_values": sorted(str(v) for v in uniques),
            "unique_count": len(uniques),
            "nulls": nulls,
            "case_inconsistencies": inconsistencies,
            "unexpected": unexpected,
        }
    return result


def validate_dataset(
    dataset: pd.DataFrame,
    dataset_name: str = "dataset",
    required_columns: Optional[list[str]] = None,
    identifier_columns: Optional[list[str]] = None,
    timestamp_columns: Optional[list[str]] = None,
    numeric_columns: Optional[list[str]] = None,
    categorical_columns: Optional[list[str]] = None,
    expected_types: Optional[dict[str, str]] = None,
    allowed_values: Optional[dict[str, list[str]]] = None,
) -> dict[str, Any]:
    """Run dataset-level validation and return a structured quality report.

    Severity policy (simple, documented):
    - ERROR: required columns missing, dataset has 0 rows, or a declared
      identifier column is completely empty/missing.
    - WARNING: missing values, duplicates, unparsable timestamps,
      non-numeric/negative numerics, case inconsistencies, unexpected
      categories, or dtype mismatches.
    - INFO: checks that passed.
    - Overall status is the highest severity observed
      (ERROR > WARNING > OK).
    """
    required_columns = required_columns or []
    identifier_columns = identifier_columns or []
    timestamp_columns = timestamp_columns or []
    numeric_columns = numeric_columns or []
    categorical_columns = categorical_columns or []
    expected_types = expected_types or {}
    allowed_values = allowed_values or {}

    checks: dict[str, Any] = {}
    issues: list[dict[str, str]] = []

    def add_issue(severity: str, check: str, message: str) -> None:
        issues.append({"severity": severity, "check": check, "message": message})

    # file_readable: reaching here with a DataFrame means ingestion succeeded.
    checks["file_readable"] = True

    # Required columns.
    req = check_required_columns(dataset, required_columns)
    checks["required_columns"] = req
    if req["missing"]:
        add_issue("ERROR", "required_columns", f"Missing required columns: {req['missing']}.")
    else:
        add_issue("INFO", "required_columns", "Required columns present.")

    # Empty dataset.
    if len(dataset) == 0:
        add_issue("ERROR", "row_count", "Dataset has 0 rows.")

    # Missing values.
    missing_df = check_missing_values(dataset)
    checks["missing_values"] = missing_df.to_dict(orient="records")
    total_missing = int(missing_df["missing"].sum()) if not missing_df.empty else 0
    if total_missing:
        worst = missing_df.sort_values("missing", ascending=False).iloc[0]
        add_issue(
            "WARNING",
            "missing_values",
            f"Missing values detected ({total_missing} cells; "
            f"worst: {worst['column']} {worst['missing']} / {worst['missing_pct']:.2f}%).",
        )
    else:
        add_issue("INFO", "missing_values", "No missing values detected.")

    # Duplicates.
    dup = check_duplicates(dataset)
    checks["duplicates"] = dup
    if dup["duplicate_rows"]:
        add_issue(
            "WARNING",
            "duplicates",
            f"{dup['duplicate_rows']} duplicate rows detected ({dup['duplicate_pct']:.2f}%).",
        )
    else:
        add_issue("INFO", "duplicates", "No duplicate rows detected.")

    # Data types.
    if expected_types:
        dtype_check = check_data_types(dataset, expected_types)
        checks["data_types"] = dtype_check
        if not dtype_check["passed"]:
            add_issue("WARNING", "data_types", f"Data-type issues: {dtype_check['mismatches']}.")
        else:
            add_issue("INFO", "data_types", "Data types inspectable.")
    else:
        checks["data_types"] = {"mismatches": [], "missing_columns": [], "passed": True}
        add_issue("INFO", "data_types", "Data types inspectable.")

    # Identifiers.
    if identifier_columns:
        ident = check_identifiers(dataset, identifier_columns)
        checks["identifiers"] = ident
        for col, detail in ident.items():
            if not detail["exists"] or detail["completely_empty"]:
                add_issue("ERROR", "identifiers", f"Identifier column '{col}' is missing or completely empty.")
            elif detail["missing"]:
                add_issue(
                    "WARNING",
                    "identifiers",
                    f"{detail['missing']} missing values in identifier '{col}' "
                    f"({detail['missing_pct']:.2f}%).",
                )

    # Timestamps.
    if timestamp_columns:
        ts = check_timestamps(dataset, timestamp_columns)
        checks["timestamps"] = ts
        for col, detail in ts.items():
            if not detail["exists"]:
                add_issue("WARNING", "timestamps", f"Timestamp column '{col}' not found.")
            elif detail["unparsable"]:
                add_issue(
                    "WARNING",
                    "timestamps",
                    f"{detail['unparsable']} unparsable values in '{col}' "
                    f"(e.g. {detail['examples']}).",
                )

    # Numerics.
    if numeric_columns:
        nums = check_numeric_values(dataset, numeric_columns)
        checks["numerics"] = nums
        for col, detail in nums.items():
            if not detail["exists"]:
                add_issue("WARNING", "numerics", f"Numeric column '{col}' not found.")
            else:
                if detail["non_numeric"]:
                    add_issue(
                        "WARNING",
                        "numerics",
                        f"{detail['non_numeric']} non-numeric values in '{col}'.",
                    )
                if detail["negative"]:
                    add_issue(
                        "WARNING",
                        "numerics",
                        f"{detail['negative']} negative values in '{col}'.",
                    )

    # Categoricals.
    if categorical_columns:
        cats = check_categoricals(dataset, categorical_columns, allowed_values)
        checks["categoricals"] = cats
        for col, detail in cats.items():
            if detail["case_inconsistencies"]:
                add_issue(
                    "WARNING",
                    "categoricals",
                    f"Case inconsistencies in '{col}': {detail['case_inconsistencies']}.",
                )
            if detail["unexpected"]:
                add_issue(
                    "WARNING",
                    "categoricals",
                    f"Unexpected categories in '{col}': {detail['unexpected']}.",
                )

    severities = {issue["severity"] for issue in issues}
    if "ERROR" in severities:
        status = "ERROR"
        valid = False
    elif "WARNING" in severities:
        status = "WARNING"
        valid = False
    else:
        status = "OK"
        valid = True

    return {
        "dataset": dataset_name,
        "valid": valid,
        "status": status,
        "checks": checks,
        "issues": issues,
    }


def format_report(result: dict[str, Any], profile: Optional[dict[str, Any]] = None) -> str:
    """Render a human-readable data-quality summary (no data modification)."""
    lines = [
        "DATA QUALITY REPORT",
        "===================",
        "",
        f"Dataset: {result.get('dataset', 'dataset')}",
        "",
    ]
    if profile is not None:
        lines.append(f"Rows: {profile.get('row_count', 0)}")
        lines.append(f"Columns: {profile.get('column_count', 0)}")
        lines.append("")
    lines.append("Checks:")
    symbol = {"INFO": "\u2713", "WARNING": "\u26a0", "ERROR": "\u2717"}
    for issue in result.get("issues", []):
        mark = symbol.get(issue.get("severity", "INFO"), "-")
        lines.append(f"{mark} [{issue.get('severity')}] {issue.get('check')}: {issue.get('message')}")
    lines.append("")
    lines.append(f"Overall Status: {result.get('status', 'UNKNOWN')}")
    return "\n".join(lines)
