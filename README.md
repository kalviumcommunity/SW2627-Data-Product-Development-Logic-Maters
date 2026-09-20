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
Validation, cleaning, integration, analytics, and dashboard are not implemented yet.
```

## Data Ingestion

The ingestion layer loads supported CSV and JSON datasets from the
raw data directory while preserving the original source files.

- Supported formats: `.csv`, `.json` (via `pipeline/ingestion.py`)
- Raw datasets live in `data/raw/` and are treated as immutable
- Usage: `load_dataset(path)`, `discover_datasets()`, `get_dataset_metadata()`
- Tests: `pytest tests/test_ingestion.py`

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
