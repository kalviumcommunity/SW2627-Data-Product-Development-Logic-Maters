"""Multi-source data integration layer.

Responsibility (feature/data-integration branch only)::

    data/processed/ (*_cleaned.csv)
        -> load_processed_datasets (DataFrames, read-only)
        -> inspect_join_keys / validate_join_keys (relationship discovery)
        -> merge_datasets + validate_join_result (validated joins)
        -> build_integrated_dataset (integrated analytical dataset)
        -> data/processed/integrated_logistics_data.csv

Rules:

* Never modifies files under ``data/raw/`` and never overwrites cleaned
  source datasets. Only the integrated output file is written.
* Never fabricates identifiers or invents relationships. Joins use only
  keys actually present in the datasets (default primary key
  ``shipment_id`` comes from Design.md section 13 as a *candidate* and is
  verified before every join; missing keys skip the join with a reason).
* Unmatched records are reported, never silently dropped (default
  ``how="left"`` preserves the base dataset; match rates are tracked).
* Many-to-many joins are reported, never silently resolved.
* Timestamps are never altered to make relationships work; temporal checks
  are read-only.
* Deterministic and reproducible: same inputs produce the same output.
* This module does NOT implement cascade detection, KPIs, scoring,
  feature engineering, anomaly detection, SQL, dashboard, alerts,
  reporting, or ML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

from pipeline.ingestion import load_dataset

PathLike = Union[str, Path]

DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_OUTPUT_FILENAME = "integrated_logistics_data.csv"
DEFAULT_OUTPUT_PATH = DEFAULT_PROCESSED_DIR / DEFAULT_OUTPUT_FILENAME

# Candidate primary key documented in Design.md section 13 ("Potential keys").
# It is only a default: every join verifies the key actually exists in both
# frames before merging. No relationship is assumed.
DEFAULT_PRIMARY_KEY = "shipment_id"

# Secondary keys / timestamps are inspected when present, never required.
SECONDARY_KEY_CANDIDATES = ("route_id", "warehouse_id")
TIMESTAMP_CANDIDATES = (
    "timestamp",
    "reported_at",
    "transfer_time",
    "expected_transfer_time",
    "actual_transfer_time",
)

SUPPORTED_JOIN_TYPES = {"left", "right", "inner", "outer"}


def _normalize_key(value: Any) -> Any:
    """Normalize a join-key value for comparison (strip strings, keep nulls)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped != "" else None
    return value


def _normalized_key_series(series: pd.Series) -> pd.Series:
    """Return a normalized copy of a key column (strings stripped)."""
    return series.map(_normalize_key)


def _key_stats(frame: pd.DataFrame, key: str) -> dict[str, Any]:
    """Inspect a single join-key column inside one dataset."""
    if key not in frame.columns:
        return {
            "exists": False,
            "dtype": None,
            "row_count": int(len(frame)),
            "missing": int(len(frame)),
            "missing_pct": 100.0 if len(frame) else 0.0,
            "unique_count": 0,
            "duplicate_count": 0,
            "sample_values": [],
            "whitespace_variants": 0,
        }
    series = frame[key]
    normalized = _normalized_key_series(series)
    missing = int(normalized.isna().sum())
    row_count = int(len(frame))
    non_null = normalized.dropna()
    unique_count = int(non_null.nunique())
    duplicate_count = int(max(len(non_null) - unique_count, 0))
    # Values whose stripped form differs (leading/trailing whitespace).
    whitespace_variants = 0
    str_mask = series.dropna().astype(str)
    if not str_mask.empty:
        whitespace_variants = int((str_mask != str_mask.str.strip()).sum())
    return {
        "exists": True,
        "dtype": str(series.dtype),
        "row_count": row_count,
        "missing": missing,
        "missing_pct": missing / row_count * 100.0 if row_count else 0.0,
        "unique_count": unique_count,
        "duplicate_count": duplicate_count,
        "sample_values": [str(v) for v in non_null.drop_duplicates().head(5).tolist()],
        "whitespace_variants": whitespace_variants,
    }


def load_processed_datasets(
    processed_dir: PathLike = DEFAULT_PROCESSED_DIR,
    pattern: str = "*.csv",
    include_integrated: bool = False,
) -> dict[str, pd.DataFrame]:
    """Load cleaned datasets from the processed directory (read-only).

    Args:
        processed_dir: Directory holding cleaned ``*.csv`` files.
        pattern: Glob pattern for dataset discovery.
        include_integrated: When False (default), the integrated output file
            itself is excluded so repeated runs do not feed back into input.

    Returns:
        Mapping of dataset stem (filename without suffix) to DataFrame,
        sorted by name for determinism. Empty when the directory is missing
        or holds no matching files.
    """
    directory = Path(processed_dir)
    if not directory.is_dir():
        return {}
    datasets: dict[str, pd.DataFrame] = {}
    for path in sorted(directory.glob(pattern), key=lambda p: p.name):
        if not path.is_file():
            continue
        if not include_integrated and path.name == DEFAULT_OUTPUT_FILENAME:
            continue
        datasets[path.stem] = load_dataset(path)
    return datasets


def inspect_join_keys(
    datasets: dict[str, pd.DataFrame],
    candidate_keys: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Inspect potential join keys across cleaned datasets (read-only).

    When ``candidate_keys`` is None, inspection covers the default primary
    key, secondary candidates actually observed, plus any column shared by
    two or more datasets.

    Returns a dict with ``common_columns``, per-key ``keys`` detail, and a
    human-oriented ``notes`` list. Nothing is merged here.
    """
    if candidate_keys is None:
        shared: dict[str, int] = {}
        for frame in datasets.values():
            for col in frame.columns:
                name = str(col)
                shared[name] = shared.get(name, 0) + 1
        auto_common = sorted([c for c, n in shared.items() if n >= 2])
        ordered = [DEFAULT_PRIMARY_KEY]
        ordered += [c for c in SECONDARY_KEY_CANDIDATES if c not in ordered]
        ordered += [c for c in auto_common if c not in ordered]
        candidate_keys = ordered

    keys: dict[str, dict[str, Any]] = {}
    for key in candidate_keys:
        present_in = sorted([n for n, f in datasets.items() if key in f.columns])
        per_dataset = {n: _key_stats(f, key) for n, f in datasets.items()}
        keys[key] = {"present_in": present_in, "per_dataset": per_dataset}

    # Columns shared by >= 2 datasets are extra join candidates worth review.
    col_counts: dict[str, int] = {}
    for frame in datasets.values():
        for col in frame.columns:
            col_counts[str(col)] = col_counts.get(str(col), 0) + 1
    common_columns = sorted([c for c, n in col_counts.items() if n >= 2])

    notes: list[str] = []
    if not datasets:
        notes.append("No processed datasets found; nothing to inspect.")
    for key, detail in keys.items():
        present = detail["present_in"]
        if not present:
            notes.append(f"Key '{key}' is absent from every dataset.")
        elif len(present) < len(datasets):
            missing_from = sorted(set(datasets) - set(present))
            notes.append(f"Key '{key}' present in {present}; missing from {missing_from}.")
        for name in present:
            stats = detail["per_dataset"][name]
            if stats["missing"]:
                notes.append(
                    f"Key '{key}' in '{name}': {stats['missing']} missing "
                    f"({stats['missing_pct']:.2f}%)."
                )
            if stats["duplicate_count"]:
                notes.append(
                    f"Key '{key}' in '{name}': {stats['duplicate_count']} duplicate "
                    "key occurrences (one-to-many or many-to-many risk)."
                )
            if stats["whitespace_variants"]:
                notes.append(
                    f"Key '{key}' in '{name}': {stats['whitespace_variants']} values "
                    "with leading/trailing whitespace (normalized for comparison)."
                )
    return {"candidate_keys": list(candidate_keys), "common_columns": common_columns, "keys": keys, "notes": notes}


def validate_join_keys(
    left: pd.DataFrame,
    right: pd.DataFrame,
    key: str,
    left_name: str = "left",
    right_name: str = "right",
) -> dict[str, Any]:
    """Validate a join key between two frames without merging.

    Checks key presence, missing keys, normalized format consistency,
    identifier overlap, uniqueness on each side, and the expected
    relationship (one-to-one / one-to-many / many-to-one / many-to-many).

    Returns a report dict with ``valid`` (key usable), ``relationship``,
    ``is_many_to_many``, overlap counts, and ``warnings``.
    """
    warnings: list[str] = []
    left_stats = _key_stats(left, key)
    right_stats = _key_stats(right, key)

    if not left_stats["exists"] or not right_stats["exists"]:
        missing_side = left_name if not left_stats["exists"] else right_name
        warnings.append(f"Join key '{key}' missing from {missing_side}; join must be skipped.")
        return {
            "left": left_name,
            "right": right_name,
            "key": key,
            "valid": False,
            "relationship": "unknown",
            "is_many_to_many": False,
            "left_stats": left_stats,
            "right_stats": right_stats,
            "left_only": 0,
            "right_only": 0,
            "overlap": 0,
            "left_coverage_pct": 0.0,
            "right_coverage_pct": 0.0,
            "warnings": warnings,
        }

    left_keys = _normalized_key_series(left[key]).dropna()
    right_keys = _normalized_key_series(right[key]).dropna()
    left_unique = set(left_keys.unique().tolist())
    right_unique = set(right_keys.unique().tolist())
    overlap = left_unique & right_unique
    left_only = left_unique - right_unique
    right_only = right_unique - left_unique

    left_dups = int(len(left_keys) - len(left_unique))
    right_dups = int(len(right_keys) - len(right_unique))
    left_is_unique = left_dups == 0
    right_is_unique = right_dups == 0
    if left_is_unique and right_is_unique:
        relationship = "one-to-one"
    elif left_is_unique:
        relationship = "one-to-many"
    elif right_is_unique:
        relationship = "many-to-one"
    else:
        relationship = "many-to-many"

    left_cov = len(overlap) / len(left_unique) * 100.0 if left_unique else 0.0
    right_cov = len(overlap) / len(right_unique) * 100.0 if right_unique else 0.0

    if left_stats["missing"]:
        warnings.append(f"{left_name}: {left_stats['missing']} rows have missing join key '{key}'.")
    if right_stats["missing"]:
        warnings.append(f"{right_name}: {right_stats['missing']} rows have missing join key '{key}'.")
    if not overlap:
        warnings.append(f"No overlapping '{key}' values between {left_name} and {right_name}.")
    if relationship == "many-to-many":
        warnings.append(
            f"Many-to-many on '{key}': {left_name} has {left_dups} duplicate key rows, "
            f"{right_name} has {right_dups}; output rows will multiply. Investigate before accepting."
        )
    elif left_dups or right_dups:
        warnings.append(
            f"One-to-many on '{key}' ({relationship}): output rows will exceed base rows; "
            "expected for repeated shipment events, but verify counts."
        )

    return {
        "left": left_name,
        "right": right_name,
        "key": key,
        "valid": True,
        "relationship": relationship,
        "is_many_to_many": relationship == "many-to-many",
        "left_stats": left_stats,
        "right_stats": right_stats,
        "left_only": len(left_only),
        "right_only": len(right_only),
        "overlap": len(overlap),
        "left_coverage_pct": left_cov,
        "right_coverage_pct": right_cov,
        "warnings": warnings,
    }


def merge_datasets(
    left: pd.DataFrame,
    right: pd.DataFrame,
    key: str,
    how: str = "left",
    left_name: str = "left",
    right_name: str = "right",
    suffixes: tuple[str, str] = ("_left", "_right"),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Merge two frames on a validated key and report coverage/duplication.

    Args:
        left: Base (left) DataFrame; never mutated.
        right: Right DataFrame; never mutated.
        key: Join column present in both frames.
        how: One of ``left`` / ``right`` / ``inner`` / ``outer``.
        left_name: Label for the left dataset (used in reports/columns).
        right_name: Label for the right dataset.
        suffixes: Suffixes for overlapping non-key columns.

    Raises:
        ValueError: If ``how`` is unsupported or ``key`` is absent.

    Returns:
        ``(merged, report)`` where report records left/right dataset names,
        join key/type, expected relationship, matching record counts,
        unmatched counts and percentages, row multiplication, and warnings.
    """
    if how not in SUPPORTED_JOIN_TYPES:
        raise ValueError(f"Unsupported join type: {how!r} (expected one of {sorted(SUPPORTED_JOIN_TYPES)})")
    if key not in left.columns:
        raise ValueError(f"Join key '{key}' not found in {left_name} columns.")
    if key not in right.columns:
        raise ValueError(f"Join key '{key}' not found in {right_name} columns.")

    pre_validation = validate_join_keys(left, right, key, left_name, right_name)
    left_rows = int(len(left))
    right_rows = int(len(right))

    merged = left.merge(right, on=key, how=how, suffixes=suffixes, indicator=True)
    indicator = merged["_merge"].value_counts()
    matched = int(indicator.get("both", 0))
    left_only = int(indicator.get("left_only", 0))
    right_only = int(indicator.get("right_only", 0))
    output_rows = int(len(merged))
    merged = merged.drop(columns=["_merge"])

    if how == "left":
        base_rows = left_rows
        unmatched = left_only
    elif how == "right":
        base_rows = right_rows
        unmatched = right_only
    elif how == "inner":
        base_rows = min(left_rows, right_rows) or 1
        unmatched = left_only + right_only
    else:  # outer
        base_rows = output_rows or 1
        unmatched = 0

    matched_pct = matched / output_rows * 100.0 if output_rows else 0.0
    unmatched_pct = unmatched / base_rows * 100.0 if base_rows else 0.0
    expansion_factor = output_rows / base_rows if base_rows else 0.0

    warnings = list(pre_validation["warnings"])
    if expansion_factor > 1.0 and pre_validation["is_many_to_many"]:
        warnings.append(
            f"Row multiplication: {base_rows} base rows -> {output_rows} output rows "
            f"(x{expansion_factor:.2f}) via many-to-many on '{key}'. Review grouping before analytics."
        )
    elif expansion_factor > 1.0:
        warnings.append(
            f"Row growth: {base_rows} base rows -> {output_rows} output rows "
            f"(x{expansion_factor:.2f}) via {pre_validation['relationship']} on '{key}'."
        )

    report: dict[str, Any] = {
        "left": left_name,
        "right": right_name,
        "key": key,
        "how": how,
        "relationship": pre_validation["relationship"],
        "is_many_to_many": pre_validation["is_many_to_many"],
        "left_rows": left_rows,
        "right_rows": right_rows,
        "output_rows": output_rows,
        "matched": matched,
        "matched_pct": matched_pct,
        "unmatched": unmatched,
        "unmatched_pct": unmatched_pct,
        "left_only": left_only,
        "right_only": right_only,
        "expansion_factor": expansion_factor,
        "warnings": warnings,
    }
    return merged, report


def validate_join_result(
    merged: pd.DataFrame,
    report: dict[str, Any],
    key: Optional[str] = None,
) -> dict[str, Any]:
    """Validate an already-performed join result (read-only checks).

    Verifies record coverage, duplicate multiplication, and identifier
    integrity of the merged output.
    """
    join_key = key or str(report.get("key", ""))
    checks: dict[str, Any] = {}
    warnings: list[str] = []

    left_rows = int(report.get("left_rows", 0))
    right_rows = int(report.get("right_rows", 0))
    output_rows = int(report.get("output_rows", len(merged)))
    matched = int(report.get("matched", 0))

    checks["left_rows"] = left_rows
    checks["right_rows"] = right_rows
    checks["output_rows"] = output_rows
    checks["actual_output_rows"] = int(len(merged))
    checks["row_count_consistent"] = checks["actual_output_rows"] == output_rows
    if not checks["row_count_consistent"]:
        warnings.append("Reported output rows differ from actual merged rows.")

    checks["matched"] = matched
    checks["matched_pct_of_output"] = matched / output_rows * 100.0 if output_rows else 0.0

    how = str(report.get("how", "left"))
    if how in {"left", "inner"} and output_rows < matched:
        warnings.append("Output has fewer rows than matched records; unexpected row loss.")
    if report.get("is_many_to_many"):
        warnings.append(
            f"Many-to-many join on '{join_key}' accepted: {left_rows} + {right_rows} -> "
            f"{output_rows} rows. Downstream analytics must aggregate per shipment."
        )

    if join_key and join_key in merged.columns:
        missing_keys = int(merged[join_key].apply(_normalize_key).isna().sum())
        checks["missing_join_keys"] = missing_keys
        checks["missing_join_key_pct"] = missing_keys / output_rows * 100.0 if output_rows else 0.0
        if missing_keys:
            warnings.append(f"{missing_keys} merged rows have missing join key '{join_key}'.")
        checks["duplicate_join_keys"] = int(
            max(len(merged) - merged[join_key].map(_normalize_key).dropna().nunique(), 0)
        )
    else:
        checks["missing_join_keys"] = None
        warnings.append(f"Join key '{join_key}' not present in merged output; integrity unchecked.")

    return {"checks": checks, "warnings": warnings, "passed": not warnings}


def check_temporal_consistency(
    dataset: pd.DataFrame,
    timestamp_pairs: Optional[list[tuple[str, str]]] = None,
) -> dict[str, Any]:
    """Check chronological relationships between timestamp columns (read-only).

    For each ``(early, late)`` pair present in the frame, reports comparable
    rows, null rows, violations where early > late, and examples. Timestamps
    are coerced with ``errors="coerce"`` for comparison only; the input frame
    is never modified.
    """
    if timestamp_pairs is None:
        present = [c for c in TIMESTAMP_CANDIDATES if c in dataset.columns]
        timestamp_pairs = [(present[i], present[j]) for i in range(len(present)) for j in range(i + 1, len(present))]
    results: dict[str, dict[str, Any]] = {}
    for early, late in timestamp_pairs:
        label = f"{early} <= {late}"
        if early not in dataset.columns or late not in dataset.columns:
            results[label] = {"checked": False, "reason": "column(s) absent"}
            continue
        early_ts = pd.to_datetime(dataset[early], errors="coerce", utc=True)
        late_ts = pd.to_datetime(dataset[late], errors="coerce", utc=True)
        comparable = bool((early_ts.notna() & late_ts.notna()).sum())
        mask = early_ts.notna() & late_ts.notna()
        n = int(mask.sum())
        violations = int((early_ts[mask] > late_ts[mask]).sum()) if n else 0
        examples: list[str] = []
        if violations:
            bad = dataset.loc[mask][early_ts[mask] > late_ts[mask]].head(3)
            for _, row in bad.iterrows():
                examples.append(f"{early}={row[early]} > {late}={row[late]}")
        results[label] = {
            "checked": True,
            "comparable_rows": n,
            "null_rows": int(len(dataset) - n),
            "violations": violations,
            "violation_pct": violations / n * 100.0 if n else 0.0,
            "examples": examples,
        }
    void_note = "No timestamp pairs available." if not results else ""
    return {"pairs": results, "note": void_note}


def _classify_datasets(datasets: dict[str, pd.DataFrame]) -> dict[str, str]:
    """Map role (scans/delays/transfers) to dataset name via filename hints."""
    roles: dict[str, str] = {}
    for name in datasets:
        lowered = name.lower()
        if "scan" in lowered and "scans" not in roles:
            roles["scans"] = name
        elif "delay" in lowered and "delays" not in roles:
            roles["delays"] = name
        elif "transfer" in lowered and "transfers" not in roles:
            roles["transfers"] = name
    return roles


def build_integrated_dataset(
    datasets: dict[str, pd.DataFrame],
    primary_key: str = DEFAULT_PRIMARY_KEY,
    how: str = "left",
    timestamp_pairs: Optional[list[tuple[str, str]]] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build the integrated shipment-journey dataset from cleaned sources.

    Strategy (validated, never assumed):

    * Base = shipment scans when identifiable by filename, else the
      alphabetically first dataset (deterministic fallback).
    * ``base LEFT JOIN delays`` on ``primary_key``, then
      ``result LEFT JOIN transfers`` on ``primary_key``.
    * A join is skipped with a documented reason when the key is absent
      from either side. Unmatched records are preserved and counted.
    * One-to-many growth (repeated scans/delays/transfers per shipment) is
      expected and reported; many-to-many output is flagged for review.
    * Source columns are preserved with suffixes only where names collide;
      traceability columns (``_record_source``, ``_source_datasets``,
      ``_delay_match``, ``_transfer_match``) record provenance per row.

    Raises:
        ValueError: If ``datasets`` is empty or the primary key is missing
            from the base dataset.

    Returns:
        ``(integrated, report)`` with per-join statistics, skipped joins,
        temporal checks, and final shape/column inventory.
    """
    if not datasets:
        raise ValueError("No processed datasets provided; cannot build integrated output.")
    if how not in SUPPORTED_JOIN_TYPES:
        raise ValueError(f"Unsupported join type: {how!r}.")

    roles = _classify_datasets(datasets)
    ordered_names = sorted(datasets)
    base_name = roles.get("scans", ordered_names[0])
    base = datasets[base_name].copy(deep=True)
    if primary_key not in base.columns:
        raise ValueError(
            f"Primary key '{primary_key}' not found in base dataset '{base_name}'. "
            f"Available columns: {list(base.columns)}. Inspect join keys before integrating."
        )

    joins: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    integrated = base
    current_name = base_name
    sources_used = [base_name]

    # Deterministic join order: delays first, then transfers, then any other
    # dataset holding the primary key (alphabetical).
    planned: list[str] = []
    for role in ("delays", "transfers"):
        candidate = roles.get(role)
        if candidate and candidate != base_name and candidate not in planned:
            planned.append(candidate)
    for name in ordered_names:
        if name not in (base_name, *planned) and primary_key in datasets[name].columns:
            planned.append(name)

    for other_name in planned:
        other = datasets[other_name]
        if primary_key not in other.columns:
            skipped.append({"dataset": other_name, "reason": f"missing key '{primary_key}'"})
            continue
        tag = other_name.replace("_cleaned", "").replace("_", "-")
        right_label = "delays" if other_name == roles.get("delays") else (
            "transfers" if other_name == roles.get("transfers") else other_name
        )
        merged, join_report = merge_datasets(
            integrated,
            other,
            primary_key,
            how=how,
            left_name=current_name,
            right_name=other_name,
            suffixes=("", f"_{tag}"),
        )
        # Provenance: recompute match flags from the right side's columns.
        right_cols = [c for c in merged.columns if c.endswith(f"_{tag}")]
        if right_cols:
            has_match = merged[right_cols].notna().any(axis=1)
        else:
            # Right side contributed only the key (fully overlapping names).
            has_match = merged[primary_key].isin(
                _normalized_key_series(other[primary_key]).dropna().tolist()
            )
        match_col = "_delay_match" if right_label == "delays" else (
            "_transfer_match" if right_label == "transfers" else f"_{tag}_match"
        )
        merged[match_col] = has_match.map({True: "both", False: f"{how}-only"})
        validation = validate_join_result(merged, join_report, primary_key)
        join_report["validation"] = validation
        join_report["match_column"] = match_col
        join_report["role"] = right_label
        joins.append(join_report)
        integrated = merged
        current_name = f"{current_name}+{other_name}"
        sources_used.append(other_name)

    # Datasets skipped because the key is absent (surfaced, not hidden).
    for name in ordered_names:
        if name in sources_used or name in planned:
            continue
        skipped.append({"dataset": name, "reason": f"missing key '{primary_key}'"})

    integrated["_record_source"] = base_name
    integrated["_source_datasets"] = ",".join(sources_used)
    integrated["_integration_key"] = integrated[primary_key].map(_normalize_key)

    temporal = check_temporal_consistency(integrated, timestamp_pairs)

    # Deterministic ordering: shipment first, then available timestamps.
    sort_cols = [c for c in [primary_key, *TIMESTAMP_CANDIDATES] if c in integrated.columns]
    if sort_cols:
        integrated = integrated.sort_values(by=sort_cols, kind="mergesort", na_position="last").reset_index(drop=True)

    report: dict[str, Any] = {
        "base_dataset": base_name,
        "primary_key": primary_key,
        "join_type": how,
        "roles": roles,
        "sources_used": sources_used,
        "joins": joins,
        "skipped": skipped,
        "temporal_consistency": temporal,
        "row_count": int(len(integrated)),
        "column_count": int(len(integrated.columns)),
        "columns": [str(c) for c in integrated.columns],
        "unresolved": [
            "Cascade detection is out of scope; output exposes events only.",
            *([f"Many-to-many on '{primary_key}' observed; aggregate per shipment downstream."]
              if any(j.get("is_many_to_many") for j in joins) else []),
            *([f"No overlapping '{primary_key}' values found in a join; check source extracts."]
              if any(j.get("matched", 0) == 0 for j in joins) else []),
        ],
    }
    return integrated, report


def save_integrated_dataset(
    dataset: pd.DataFrame,
    output_path: PathLike = DEFAULT_OUTPUT_PATH,
) -> Path:
    """Write the integrated dataset to ``data/processed/`` (creates parents).

    Raises:
        ValueError: If the dataset is empty (refuses to write a vacuous file).
    """
    if len(dataset) == 0:
        raise ValueError("Refusing to save an empty integrated dataset.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output, index=False)
    return output


def format_integration_report(report: dict[str, Any]) -> str:
    """Render a human-readable integration summary (no data modification)."""
    lines = [
        "DATA INTEGRATION REPORT",
        "=======================",
        "",
        f"Base dataset: {report.get('base_dataset')}",
        f"Primary key: {report.get('primary_key')} (join type: {report.get('join_type')})",
        f"Sources used: {report.get('sources_used')}",
        f"Output rows: {report.get('row_count')} x cols: {report.get('column_count')}",
        "",
        "Joins:",
    ]
    for join in report.get("joins", []):
        lines.append(
            f"  {join.get('left')} + {join.get('right')} on '{join.get('key')}' "
            f"[{join.get('how')}, {join.get('relationship')}] "
            f"rows {join.get('left_rows')}+{join.get('right_rows')} -> {join.get('output_rows')} "
            f"| matched {join.get('matched')} ({join.get('matched_pct', 0.0):.2f}%), "
            f"unmatched {join.get('unmatched')} ({join.get('unmatched_pct', 0.0):.2f}%), "
            f"x{join.get('expansion_factor', 0.0):.2f}"
        )
        for warning in join.get("warnings", []):
            lines.append(f"    ! {warning}")
    if report.get("skipped"):
        lines.append("Skipped:")
        for skipped in report["skipped"]:
            lines.append(f"  - {skipped.get('dataset')}: {skipped.get('reason')}")
    temporal = report.get("temporal_consistency", {}).get("pairs", {})
    if temporal:
        lines.append("Temporal consistency:")
        for label, detail in temporal.items():
            if not detail.get("checked"):
                lines.append(f"  - {label}: not checked ({detail.get('reason')})")
            else:
                lines.append(
                    f"  - {label}: {detail.get('comparable_rows')} comparable, "
                    f"{detail.get('violations')} violations "
                    f"({detail.get('violation_pct', 0.0):.2f}%)"
                )
    if report.get("unresolved"):
        lines.append("Unresolved / follow-ups:")
        for item in report["unresolved"]:
            lines.append(f"  - {item}")
    return "\n".join(lines)
