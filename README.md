# Cascading Delay Intelligence

An end-to-end logistics data product for identifying delay patterns and cascading operational delays across shipment routes, warehouses, and transfers.

## Problem

A logistics company tracks **shipment scans**, **delay reports**, and **warehouse transfer records** as separate datasets. Because these sources are disconnected, it is difficult to see where operational delays originate, how they propagate through warehouse transfers and routes, and which routes or warehouses are consistently associated with cascading delivery delays.

## Solution

This project integrates those datasets into a single analytical workflow — ingestion, validation, cleaning, multi-source integration, feature engineering, KPI calculation, and SQL analytics — and exposes the insights through an interactive Streamlit application with Plotly visualizations.

The full design (architecture, data workflow, business logic, and development conventions) is documented in [`Design.md`](Design.md), which is the project's source of truth.

## Current Status

```text
Project foundation initialized.
Data ingestion layer implemented (CSV/JSON loading from data/raw/).
Data-quality validation layer implemented (profiling + quality reports, no cleaning).
Data cleaning layer implemented (standardisation to data/processed/, raw files unchanged).
Multi-source integration layer implemented (validated joins to data/processed/integrated_logistics_data.csv); no production datasets present yet, so no integrated output generated.
Analytics and dashboard are not implemented yet.
```

## Data Ingestion

The ingestion layer loads supported CSV and JSON datasets from the
raw data directory while preserving the original source files.

- Supported formats: `.csv`, `.json` (via `pipeline/ingestion.py`)
- Raw datasets live in `data/raw/` and are treated as immutable
- Usage: `load_dataset(path)`, `discover_datasets()`, `get_dataset_metadata()`
- Tests: `pytest tests/test_ingestion.py`

## Data Quality

The validation layer profiles loaded DataFrames and reports quality
issues without modifying data (via `pipeline/validation.py`).

- Profiling: `profile_dataset()` — rows, columns, dtypes, missing, uniques, duplicates, numeric/categorical summaries
- Checks: `check_missing_values()`, `check_duplicates()`, `check_required_columns()`, `check_data_types()`, `check_identifiers()`, `check_timestamps()`, `check_numeric_values()`, `check_categoricals()`
- Dataset report: `validate_dataset()` → `{dataset, valid, status, checks, issues}` with `INFO/WARNING/ERROR` severity, plus `format_report()` for human-readable output
- Raw files in `data/raw/` are never modified; cleaning is NOT part of this layer
- Tests: `pytest tests/test_validation.py`

## Data Cleaning

The cleaning layer converts loaded DataFrames into consistently
formatted outputs without touching raw files (via `pipeline/cleaning.py`).

- Entry points: `clean_dataset(df, ...)`, `clean_file(raw_path, ...)`, `save_cleaned_dataset(df, output_path)`
- Steps: `normalize_strings()`, `standardize_categoricals()`, `standardize_dates()` / `standardize_data_types()` / `standardize_numerics()`, `clean_missing_values()` (median/mean + `unknown` fill, missing IDs dropped), `handle_duplicates()` (exact only), `handle_invalid_records()` (missing IDs, caller-declared non-negative columns; outliers preserved)
- Every run returns a summary: input/output rows, columns transformed, missing handled, duplicates/invalid removed, type conversions
- Raw → `data/raw/` (read-only) → cleaned → `data/processed/<name>_cleaned.csv`; reproducible from raw input
- Tests: `pytest tests/test_cleaning.py`

## Data Integration

The integration layer connects cleaned datasets into one analytical
table without inventing keys or cascade logic (via `pipeline/integration.py`).

- Entry points: `load_processed_datasets()`, `inspect_join_keys()`, `validate_join_keys()`, `merge_datasets()`, `validate_join_result()`, `check_temporal_consistency()`, `build_integrated_dataset()`, `save_integrated_dataset()`, `format_integration_report()`
- Default primary key `shipment_id` (Design.md §13 candidate) is verified in every dataset before joining; missing keys skip the join with a documented reason
- Strategy: scans (base, or first dataset as deterministic fallback) `LEFT JOIN` delays, then `LEFT JOIN` transfers on `shipment_id`; unmatched rows preserved and counted; many-to-many output flagged, never silently resolved; timestamps checked read-only
- Traceability per row: `_record_source`, `_source_datasets`, `_delay_match`, `_transfer_match`, `_integration_key`; source columns preserved with suffixes only on collision
- Output: `data/processed/integrated_logistics_data.csv` (only written when cleaned inputs exist; with the current empty `data/processed/`, no output is generated)
- Tests: `pytest tests/test_integration.py` (synthetic frames only)

## Technology Stack

- **Python** — core implementation language
- **Pandas / NumPy** — data processing and analysis
- **SQL** — business-oriented analytical queries
- **Streamlit** — interactive application
- **Plotly** — visualizations
- **Git / GitHub** — version control and collaboration
- **GitHub Actions** — automated validation

## Project Structure

```text
cascading-delay-intelligence/
├── app/       # Streamlit application (entry point; pages come later)
├── analysis/  # EDA, KPIs, route/warehouse/cascade analysis
├── data/      # raw/ (source files), processed/ (pipeline output), sample/ (committed samples)
├── pipeline/  # Ingestion, validation, cleaning, transformation, feature engineering
├── sql/       # Analytical SQL queries
├── reports/   # Generated reports
├── tests/     # Unit and pipeline tests
└── .github/   # GitHub Actions workflows
```

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

See `.env.example` for placeholder environment configuration used by future features.
