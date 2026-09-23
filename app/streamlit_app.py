"""Cascading Delay Intelligence - Streamlit application entry point.

Presentation only: navigation, dataset selection, global filters, and page
dispatch. All calculations come from analysis/; all queries from sql/.
Filtered data is never written back to disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `app`, `analysis`, `config`, and `pipeline` importable no matter how
# the app is launched. `streamlit run app/streamlit_app.py` puts only the
# script's folder (app/) on sys.path, while `python -m pytest` and
# `python -m streamlit` provide the repo root - without this bootstrap the
# browser shows ModuleNotFoundError even though tests pass.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from app.components.data_loader import (
    build_demo_dataset,
    discover_processed_datasets,
    load_processed_csv,
)
from app.components.filters import apply_filters, render_sidebar_filters
from app.components.theme import apply_theme
from app.pages import alerts, cascades, dataset, delays, overview, prediction, reports, routes, warehouses

PROJECT_NAME = "Cascading Delay Intelligence"

PAGES = {
    "Overview": overview.render,
    "Dataset explorer": dataset.render,
    "Delay analysis": delays.render,
    "Routes": routes.render,
    "Warehouses": warehouses.render,
    "Cascades": cascades.render,
    "Prediction": prediction.render,
    "Alerts": alerts.render,
    "Reports": reports.render,
}


@st.cache_data(show_spinner=False)
def _cached_load(path_str: str) -> pd.DataFrame:
    """Load a processed CSV once per session (callers must not mutate it)."""
    return load_processed_csv(path_str)


@st.cache_data(show_spinner=False)
def _cached_demo() -> pd.DataFrame:
    return build_demo_dataset()


def _select_dataset() -> tuple[pd.DataFrame, str, bool]:
    """Return (frame, label, is_demo) from processed data or demo fallback."""
    st.sidebar.markdown(
        """
        <div style="font-size: 0.72rem; font-weight: 700; color: #6e7681; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
            Data Source
        </div>
        """,
        unsafe_allow_html=True,
    )
    available = discover_processed_datasets()
    options = [p.name for p in available] + ["Demo dataset (synthetic)"]
    choice = st.sidebar.selectbox("Dataset", options, key="dataset_choice", label_visibility="collapsed")
    if choice == "Demo dataset (synthetic)":
        return _cached_demo(), "demo", True
    try:
        frame = _cached_load(str(next(p for p in available if p.name == choice)))
    except (StopIteration, FileNotFoundError, OSError) as exc:
        st.error(f"Could not load dataset: {exc}")
        return pd.DataFrame(), choice, False
    # No copy here: the cached frame is shared read-only. apply_filters()
    # copies internally, and pages must treat `full` as immutable.
    return frame, choice, False


def main() -> None:
    st.set_page_config(
        page_title=PROJECT_NAME,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()

    st.sidebar.markdown(
        """
        <div style="padding: 4px 0 14px 0; border-bottom: 1px solid #21262d; margin-bottom: 12px;">
            <div style="font-size: 0.95rem; font-weight: 700; color: #f0f6fc; letter-spacing: -0.01em;">
                Logistics Analytics
            </div>
            <div style="font-size: 0.75rem; color: #7d8590; margin-top: 2px;">
                Cascading Delay Intelligence
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown(
        """
        <div style="font-size: 0.72rem; font-weight: 700; color: #6e7681; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
            Navigation
        </div>
        """,
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio("Page", list(PAGES.keys()), key="nav_page", label_visibility="collapsed")

    full, label, is_demo = _select_dataset()
    if full.empty:
        st.info(
            "No integrated dataset available. Run the data pipeline "
            "(ingestion to integration) or select the demo dataset."
        )
        return

    st.markdown(
        f"""
        <div class="app-header-bar">
            <div class="app-breadcrumb">
                <span>{PROJECT_NAME}</span>
                <span>/</span>
                <span class="active-section">{page}</span>
            </div>
            <div>
                {'<span class="status-pill warning">SYNTHETIC DEMO</span>' if is_demo else '<span class="status-pill success">INTEGRATED DATA</span>'}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selections = render_sidebar_filters(full)
    try:
        filtered = apply_filters(
            full,
            routes=selections["routes"],
            warehouses=selections["warehouses"],
            reasons=selections["reasons"],
            start_date=selections["start_date"],
            end_date=selections["end_date"],
            delay_status=selections["delay_status"],
        )
    except ValueError as exc:
        st.error(f"Filter error: {exc}")
        return

    st.sidebar.markdown(
        f"""
        <div style="margin-top: 16px; padding: 8px 12px; background: #131822; border-radius: 6px; border: 1px solid #21262d; display: flex; justify-content: space-between; align-items: center; font-size: 0.78rem;">
            <span style="color: #7d8590; font-weight: 500;">Records</span>
            <span style="color: #58a6ff; font-weight: 600; font-family: 'JetBrains Mono', monospace;">
                {len(filtered):,} / {len(full):,}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if page == "Dataset explorer":
        PAGES[page](filtered, full, dataset_name=label)
    else:
        PAGES[page](filtered, full)


if __name__ == "__main__":
    main()
