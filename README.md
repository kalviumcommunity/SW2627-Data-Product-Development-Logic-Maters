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
Business analytics layer implemented (EDA, KPIs, route/warehouse/delay/time analysis over integrated data, UI-independent); production verification pending real datasets.
SQL analytics layer implemented (SQLite: schema, KPI/analytical queries, views, window functions, SQL/Pandas validation); verified on realistic fixtures, production verification pending real datasets.
Cascading-delay analysis implemented (journey reconstruction, cascade candidates, propagation metrics by route/warehouse, stage signals; association only, no causal claims); verified on synthetic journeys and real integration output, production verification pending real datasets.
Streamlit dashboard implemented (overview, dataset, delays, routes, warehouses, cascades; Plotly charts, centralized filters, demo fallback); all pages render-verified, production data pending.
Dashboard is not implemented yet.
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

## Analytics Engine

The analytics layer turns the integrated dataset into reusable,
UI-independent facts (via `analysis/`). It never modifies source data and
creates no cascade flags, scores, or thresholds.

- EDA (`eda.py`): `get_dataset_summary()`, distributions for delays / reasons / routes / warehouses / events / time, `get_missingness_summary()` — metrics only for columns actually present
- KPIs (`kpis.py`): `compute_kpis()` → `{shipment, delay, operational}`; `delay_rate = delayed_shipments / total_shipments × 100`, `on_time_rate = 100 − delay_rate`; duration stats over delayed records with non-null duration; match rates from integration traceability columns; unresolvable KPIs return `None` with a reason
- Routes (`route_analysis.py`): `route_metrics()` (shipments, delay rate, avg/median/total delay per route), `top_delayed_routes()`, `route_trends()` — factual metrics only, no scores
- Warehouses (`warehouse_analysis.py`): `warehouse_metrics()`, `top_delayed_warehouses()`, `warehouse_trends()`, `transfer_activity()` — associations for investigation, never causal claims
- Delays & time (`delay_analysis.py`): `delay_reason_breakdown()`, `delay_by_segment()`, `derive_time_features()`, `delay_over_time()`, `rolling_delay_rate()` (full-window averages; `sparse_warning` on thin data)
- Column detection (`_schema.py`, internal): resolves `shipment_id`, `delay_duration`, `delay_reason`, `route_id`, warehouse/timestamp columns; delay flag from explicit flag → duration > 0 → status values (caller-overridable)
- Verified end-to-end against real `build_integrated_dataset()` output; with the current empty `data/processed/`, production verification is pending real datasets
- Tests: `pytest tests/test_kpis.py tests/test_route_analysis.py tests/test_warehouse_analysis.py tests/test_analytics.py` (synthetic frames only)

## SQL Analytics

SQLite (stdlib only, no server or credentials) stores the integrated
dataset and answers the same business metrics as the Pandas engine
for cross-validation. SQL stays in `sql/*.sql`; `pipeline/sql_database.py`
only loads data, runs queries, and compares results.

- Schema (`sql/schema.sql`): canonical `integrated_logistics` table from Design.md §8 fields + integration traceability columns, with indexes on `shipment_id`, `route_id`, `warehouse_id`, `timestamp`; the loader creates tables from actual DataFrame columns, so absent columns are never invented
- Loading: `load_integrated_dataset(df)` (type mapping, ISO timestamps, row-count validation, source frame untouched)
- KPIs (`sql/metrics.sql`): shipment/delay/operational rates with `NULLIF` zero-guards; median via window functions; record-level vs shipment-level (`MAX` per shipment) aggregation kept explicit — never `SUM(delay_duration)` across duplicated rows
- Analysis (`sql/analysis.sql`): grouping/ranking (routes, warehouses, reasons, daily trends), `RANK`/`DENSE_RANK`/`ROW_NUMBER`/`LAG`/rolling 7-day average (full-window, like Pandas)
- Views (`sql/views.sql`): `shipment_delay_summary` (one row per shipment), `route_delay_metrics`, `warehouse_delay_metrics`, `daily_delay_metrics`
- Validation: `validate_sql_vs_pandas()` compares like-for-like values with tolerance and reports mismatches instead of forcing agreement
- Production verification pending real integrated data; all checks pass on realistic fixtures
- Tests: `pytest tests/test_sql_analytics.py` (temporary SQLite databases only)

## Cascading-Delay Analysis

Deterministic journey reconstruction and cascade-candidate detection
(via `analysis/cascade_analysis.py`). A candidate is an initial delay
followed by later downstream delay(s) in one shipment's ordered journey;
a single delay is never a cascade. Language is associational
("downstream delay observed"), never causal.

- Journeys: `reconstruct_shipment_journey()` (timestamp ordering, tie-break by extra timestamps then stable input order, exact-duplicate removal, explicit skip counts), `get_shipment_events()`, `sort_shipment_events()`
- Rule: `detect_cascade_candidates()` with no hidden thresholds — `min_delay_duration` and `max_downstream_gap` default to `None` (any later delay qualifies) and are echoed in every output
- Stages: `initial_delay`, `transfer_disruption`, `warehouse_delay`, `downstream_route_delay`, `final_delivery_delay` (last event + delivery status, caller-overridable), `downstream_delay` fallback — assigned by documented precedence from available columns only
- Metrics: `cascade_summary_metrics()` (counts, rate, depth, downstream delay), `cascade_by_route()` / `cascade_by_warehouse()` (factual, no scores), `root_cause_signals()` (presence share per stage, never over 100%)
- Levels: event rows preserved; shipment-level output via `save_cascade_candidates()` → `data/processed/cascade_candidates.csv` (stages serialized `>`-joined); durations compared per event, never blindly summed
- Known grain effect: one-to-many integration rows repeat delay values, so cascade depth counts delayed integrated rows — interpret alongside `event_count`/`delayed_event_count`
- Tests: `pytest tests/test_cascade_analysis.py` (no-cascade, simple/multi-stage propagation, isolation, ties, gaps, duplicates, edge cases, immutability)

## Streamlit Dashboard

Interactive presentation layer (`app/`). All calculations come from
`analysis/` and SQL stays in `sql/` — the dashboard renders, filters, and
charts only. Start with `streamlit run app/streamlit_app.py`.

- Pages: Overview (KPI cards, delay trend, route summary), Dataset explorer (structure, samples, missingness), Delay analysis (distribution, reasons, trends, segments), Routes (factual metrics, detail, trends), Warehouses (metrics, transfer activity, trends), Cascades (candidates, depth, route/warehouse patterns, shipment journey inspector)
- Filters (sidebar, only for columns actually present): date range, route, warehouse, delay reason, delayed/on-time status — centralized in `apply_filters()`, never written back to disk
- Charts: Plotly trend lines, bar comparisons, delay-status donut (numeric labels), cascade-depth bars, per-shipment journey timelines
- Data: processed CSVs (integrated first) via cached loading, or a clearly badged synthetic demo dataset when no processed data exists; graceful empty states everywhere ("No records match the selected filters")
- Known limitation: `data/processed/` is currently empty, so live views show demo data until the pipeline produces real integrated output
- Tests: `pytest tests/test_dashboard.py` (filter logic, chart builders, KPI prep, demo data, loader, full-app render smoke test)

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
