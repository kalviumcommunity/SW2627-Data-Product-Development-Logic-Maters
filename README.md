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
Multi-source integration layer implemented (validated joins to data/processed/integrated_logistics_data.csv).
Real-world showcase data integrated: LaDe Jilin pickup subset (25,934 packages, 51,868 scan events, ds 0605-0618) processed end-to-end through the existing pipeline.
Business analytics layer implemented (EDA, KPIs, route/warehouse/delay/time analysis over integrated data, UI-independent); verified on the LaDe showcase subset.
SQL analytics layer implemented (SQLite: schema, KPI/analytical queries, views, window functions, SQL/Pandas validation); 9/9 like-for-like comparisons match on the LaDe showcase subset (transfer/warehouse sections honestly unrunnable: columns absent in LaDe).
Cascading-delay analysis implemented (journey reconstruction, cascade candidates, propagation metrics by route/warehouse, stage signals; association only, no causal claims); 25,934 LaDe showcase shipments checked, 1 cascade candidate observed (reported, not tuned).
Streamlit dashboard implemented (overview, dataset, delays, routes, warehouses, cascades; Plotly charts, centralized filters, demo fallback); renders the real LaDe showcase data (verified via health check + data-path exercise); warehouse/reason sections show honest empty states where LaDe has no such data.
```

## Real-World Data — LaDe Showcase

Source: **LaDe — Large-scale Last-mile Delivery Dataset** (`Cainiao-AI/LaDe`
on Hugging Face, revision `be2cec02775cafc8d52230303f32134382bcc50b`,
accessed 2026-09-22; Hub metadata license `apache-2.0`, paper quotes
CC BY-NC 4.0 research terms). Reference: Wu et al., arXiv:2306.10675
(KDD 2024). Data type: real-world industry logistics data. Showcase subset:
reproducibly selected for local application performance (NOT synthetic).

- File used: `pickup/pickup_jl.csv` (Jilin pickup: 261,801 packages,
  665 couriers, 15 regions, 184 days; ~43 MB). Pickup — not delivery — is
  the only sub-dataset with explicit promised time windows, the sole honest
  delay anchor. Jilin pickup is the smallest pickup file.
- Showcase rule: keep rows with `ds` in [0605, 0618] (14 contiguous days,
  no sampling) → 25,934 packages → 51,868 scan events + 94 delay incidents.
- Mapping: `order_id` → `shipment_id`; `accept_time`/`pickup_time` →
  accept/pickup events; per-stage lateness vs the promised window →
  `delay_duration` (0 when early; the contract window is the threshold, none
  invented); `region_id` → `route_id` proxy (`region_<id>`); `delay_reason`,
  warehouses, and transfers are NOT in LaDe and were never fabricated
  (`warehouse_transfers.csv` does not exist; delay-reason breakdowns report
  "unavailable"). Full table: [`docs/dataset_mapping.md`](docs/dataset_mapping.md).
- Workflow (existing pipeline, unmodified except a pandas-3 dtype-robustness
  fix in `pipeline/cleaning.py`): `pipeline/lade_adapter.py` →
  `data/raw/shipment_scans.csv` + `data/raw/delay_reports.csv` → ingestion →
  validation (OK, 0 missing, 0 duplicates) → cleaning (no rows removed) →
  integration (`shipment_scans_cleaned LEFT JOIN delay_reports_cleaned`,
  51,868 rows, 188 matched, 0 temporal violations) → analytics/SQL/cascades
  → dashboard. Every derived row keeps `source_file`/`source_row_id`/
  `source_event_id`/`source_timestamp` provenance.
- Results: 25,934 shipments, 94 delayed (delay rate 0.36%, on-time 99.64%),
  avg delay 64.8 min (median 1.0, max 991.0); 25,934 journeys checked,
  1 cascade candidate (depth 1, region_90) — an observed sequence
  (accept 778 min late → pickup 959 min late), not proof of cause.
  SQL/Pandas: 9/9 match. Alerts: 25 (24 excessive-delay, 1 cascade).
- Limitations: low delay rate (~0.36%) is real, not tuned; package cascades
  need both stages late (genuinely rare); no warehouse/transfer/reason
  analysis possible; times lack a year (assumed 2022 for parsing; relative
  metrics unaffected).
- Reproduce: download `pickup/pickup_jl.csv` from the source above, then
  `python -c "from pipeline.lade_adapter import build_lade_sources;
  build_lade_sources(<path>)"` and run the pipeline stages. Raw LaDe data
  is never committed (`.gitignore`); a 1,000-row sample is versioned at
   `data/sample/lade_showcase_sample.csv`. The synthetic demo dataset
   remains available in the dashboard selector.

## Synthetic Showcase Data

LaDe honestly covers no warehouses, transfers, delay reasons, or cascades,
so those views stay empty on LaDe data. The deterministic synthetic
showcase (`pipeline/synthetic_showcase.py`, seed 42) is the complement:
3,000 shipments across 6 routes and 5 warehouses with all three sources,
genuine cascade chains, and full page/SQL/alert coverage. Run
`python pipeline/synthetic_showcase.py`, then pick
`integrated_logistics_showcase.csv` in the dashboard dataset selector.

- Output: `data/processed/integrated_logistics_showcase.csv` (8,870 events,
  990 delayed shipments at 33.0%, 602 cascade candidates at 20.1% with
  depths 1–3, worst lane R2/W2, 1,277 alerts with zero unavailable checks,
  20/20 SQL-vs-Pandas comparisons match).
- Every row carries `source_file = synthetic_showcase`; raw/processed
  files are gitignored, the generator plus a 1,016-row sample
  (`data/sample/showcase_sample.csv`) are versioned.
- Full design, metrics, and limitations: [`docs/synthetic_showcase.md`](docs/synthetic_showcase.md).

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
- Output: `data/processed/integrated_logistics_data.csv` (currently the LaDe showcase output: 51,868 rows from `shipment_scans_cleaned LEFT JOIN delay_reports_cleaned`; no warehouse source exists in LaDe, so no transfer join is attempted)
- Tests: `pytest tests/test_integration.py` (synthetic frames only)

## Unified Pipeline Runner

One command runs the whole product path with a validation gate and a
machine-readable run record (via `pipeline/run_pipeline.py`; orchestration
only — every calculation still lives in its own module).

```bash
python -m pipeline.run_pipeline --dataset showcase
python -m pipeline.run_pipeline --dataset lade --input path/to/pickup_jl.csv
```

- Stages: source build → ingestion → validation → **gate** → cleaning → integration → analytics → SQL cross-check → cascade → route risk → alerts → manifest
- Gate: validation `ERROR` stops the run (downstream `SKIPPED`, overall `FAILED`, exit 1, manifest still written); `WARNING` continues as `SUCCESS_WITH_WARNINGS`; clean pass is `SUCCESS`
- Manifests: `data/processed/runs/run_<timestamp>.json` (gitignored) with run/dataset/timestamps, per-stage status + timings + row counts, validation summary, warnings/errors, and parameters — no secrets, no embedded datasets
- LaDe needs its source file passed explicitly (`--input`); nothing is downloaded automatically, and warehouse transfers / delay reasons are never invented (honest-empty behavior preserved)
- Raw inputs are never mutated; working dirs and the integrated destination are overridable (`--raw-dir`, `--processed-dir`, `--runs-dir`, `--output`)
- Tests: `pytest tests/test_pipeline_runner.py` (tmp dirs only)

## Analytics Engine

The analytics layer turns the integrated dataset into reusable,
UI-independent facts (via `analysis/`). It never modifies source data and
creates no cascade flags, scores, or thresholds.

- EDA (`eda.py`): `get_dataset_summary()`, distributions for delays / reasons / routes / warehouses / events / time, `get_missingness_summary()` — metrics only for columns actually present
- KPIs (`kpis.py`): `compute_kpis()` → `{shipment, delay, operational}`; `delay_rate = delayed_shipments / total_shipments × 100`, `on_time_rate = 100 − delay_rate`; duration stats over delayed records with non-null duration; match rates from integration traceability columns; unresolvable KPIs return `None` with a reason
- Routes (`route_analysis.py`): `route_metrics()` (shipments, delay rate, avg/median/total delay per route), `top_delayed_routes()`, `route_trends()` — factual metrics only, no scores
- Route cascade risk (`route_risk.py`, thresholds in `config/route_risk_config.py`): historical empirical indicators per route — `cascade_rate` (cascade/delayed shipments × 100), `downstream_delay_rate`, `cascade_probability` (empirical P(downstream | initial delay), 0..1), `cascade_recurrence` (weeks with cascades / weeks with delays), depth avg/max/distribution, period-rate mean/std/CV consistency, observed stage-transition probabilities, and configurable LOW/MEDIUM/HIGH/INSUFFICIENT_DATA classes with metrics alongside. Descriptive only — **not an ML prediction** (see Design.md §18.1)
- Warehouses (`warehouse_analysis.py`): `warehouse_metrics()`, `top_delayed_warehouses()`, `warehouse_trends()`, `transfer_activity()` — associations for investigation, never causal claims
- Delays & time (`delay_analysis.py`): `delay_reason_breakdown()`, `delay_by_segment()`, `derive_time_features()`, `delay_over_time()`, `rolling_delay_rate()` (full-window averages; `sparse_warning` on thin data)
- Column detection (`_schema.py`, internal): resolves `shipment_id`, `delay_duration`, `delay_reason`, `route_id`, warehouse/timestamp columns; delay flag from explicit flag → duration > 0 → status values (caller-overridable)
- Verified end-to-end against real `build_integrated_dataset()` output, including the LaDe showcase subset (delay reasons and warehouses honestly report as unavailable)
- Tests: `pytest tests/test_kpis.py tests/test_route_analysis.py tests/test_warehouse_analysis.py tests/test_analytics.py tests/test_route_risk.py` (synthetic frames only)

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
- Verified on the LaDe showcase subset: 9/9 like-for-like SQL-vs-Pandas comparisons match; transfer/warehouse sections are unrunnable there because LaDe has no such columns (reported, never invented)
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

- Pages: Overview (KPI cards, delay trend, route summary), Dataset explorer (structure, samples, missingness), Delay analysis (distribution, reasons, trends, segments), Routes (factual metrics, detail, trends, **route cascade risk with rate/recurrence charts, period trend, stage transitions**), Warehouses (metrics, transfer activity, trends), Cascades (candidates, depth, route/warehouse patterns, shipment journey inspector), Alerts (threshold-breach summary, alert table, per-alert evidence)
- Filters (sidebar, only for columns actually present): date range, route, warehouse, delay reason, delayed/on-time status — centralized in `apply_filters()`, never written back to disk
- Charts: Plotly trend lines, bar comparisons, delay-status donut (numeric labels), cascade-depth bars, per-shipment journey timelines
- Data: processed CSVs (integrated first) via cached loading — currently the real LaDe showcase output — or a clearly badged synthetic demo dataset when no processed data exists
- Known limitation: LaDe contains no warehouse, transfer, or delay-reason data, so those views intentionally show empty states on the showcase dataset
- Tests: `pytest tests/test_dashboard.py` (filter logic, chart builders, KPI prep, demo data, loader, full-app render smoke test)

## Alerts & Risk Detection

Threshold-breach alerts over observed metrics — not predictions, not risk
scores (`analysis/alerts.py`, thresholds in `config/alert_config.py`).

- Categories: route/warehouse delay-rate breaches (from existing route/warehouse metrics), per-shipment excessive delay (worst duration vs threshold), cascade candidates (reused `detect_cascade_candidates` output, one alert per shipment)
- Output per alert: id, type, severity (INFO near-miss watch / WARNING breach / CRITICAL escalation), entity, metric, observed value, threshold, factual message, detection time, JSON evidence
- Configuration: centralized `DEFAULT_ALERT_CONFIG`, caller-overridable, `None` disables a type; documented as demonstration parameters, NOT learned from production data
- Summary: `summarize_alerts()` (counts by severity/type, affected entities, top exceedances)
- Dashboard: Alerts page with summary cards, severity/type/entity filters, evidence expanders; verified on the demo dataset (31 alerts: 4 critical, 22 warning, 5 info)
- Tests: `pytest tests/test_alerts.py` (15 spec cases: detection, silence, severity, overrides, empty/missing/dupes, immutability, determinism)

## Reporting

Stakeholder reports generated from recorded pipeline runs — presentation
only, every figure reused from existing analytics over the run's own
integrated output (`reports/report_generator.py`). The generator does not
duplicate analytics logic: the manifest records only summary context
(status, timings, row counts, validation), so full tables are recomputed
deterministically by calling the existing analysis functions
(`compute_kpis`, `route_metrics`, `detect_cascade_candidates`,
`route_cascade_risk`, `generate_alerts`, …) over the run's own integrated
CSV. Identical inputs always yield identical reports.

```bash
python -m pipeline.run_pipeline --dataset showcase
python -m reports.report_generator --run data/processed/runs/run_<id>.json --format markdown
python -m reports.report_generator --run data/processed/runs/run_<id>.json --format html
```

- Sections: executive summary, run/dataset info, data quality (warnings shown, never hidden), KPIs, delay analysis, route intelligence, cascade intelligence, warehouses, alerts with evidence, risk interpretation, investigation areas, limitations
- Honest empty states: missing warehouses/reasons render as "Not available for this dataset"; synthetic runs are badged synthetic, LaDe runs labeled real; empirical risk is described as historical observation, never ML prediction
- Outputs: `data/processed/runs/report_<run_id>.md|.html` beside the manifest (gitignored runtime artifacts); the dashboard Reports page lists runs with downloads
- Tests: `pytest tests/test_reporting.py` (generation, sections, empty states, labeling, determinism, secrets, CLI-adjacent failures, Streamlit smoke test)

## Email Reports

Optional SMTP delivery of a generated report (`reports/email_report.py`,
stdlib only). The analytics system works without email configuration; the
email layer only presents figures already computed by the report generator.

```bash
copy .env.example .env   # then fill in real values locally; never commit .env
python -m reports.email_report --run data/processed/runs/run_<id>.json --to ops@example.com
python -m reports.email_report --run data/processed/runs/run_<id>.json --dry-run   # validate only, send nothing
```

- Required environment variables (`REPORT_*` canonical; legacy `EMAIL_*`
  accepted as fallback): `REPORT_SMTP_HOST`, `REPORT_SMTP_PORT` (default
  587), `REPORT_SMTP_USERNAME`, `REPORT_SMTP_PASSWORD`, `REPORT_EMAIL_FROM`,
  `REPORT_EMAIL_TO` (comma-separated; `--to` overrides it). See
  `.env.example` for safe placeholders.
- Subject: `Cascading Delay Intelligence Report — <dataset> — <run_id>`.
  Body: concise summary (dataset, run status, shipment count, delay rate,
  cascade count/rate, route-risk summary, alert count, validation warnings)
  plus the full Markdown/HTML report as attachments
  (`--no-attachments` sends the summary only). No recommendations are
  invented; risk is worded as historical observation, never prediction.
- Missing configuration fails clearly (exit 1); SMTP delivery failure
  exits 2. Credentials are never hardcoded, committed, or logged.
- Tests (`pytest tests/test_email_report.py`) use a mocked SMTP transport
  only — no real email is ever sent during testing.

## CI

GitHub Actions workflow (`.github/workflows/ci.yml`) triggers on `push`
and `pull_request` with no secrets required:

- supported Python (3.12) + `pip install -r requirements.txt` + `pytest`
- module import checks (`pipeline.run_pipeline`, `reports.report_generator`,
  `reports.email_report`, cascade/route-risk/alerts)
- full `pytest -q` suite (fails the build on any failure)
- showcase pipeline smoke test (`--dataset showcase --seed 42
  --n-shipments 200`)
- Tests: `pytest tests/test_ci.py` validates the workflow structure
  (triggers, install/test steps, smoke test, no secret references).

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
