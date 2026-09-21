"""Cascading Delay Intelligence - Streamlit application entry point.

Presentation only: navigation, dataset selection, global filters, and page
dispatch. All calculations come from analysis/; all queries from sql/.
Filtered data is never written back to disk.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.data_loader import (
    build_demo_dataset,
    discover_processed_datasets,
    load_processed_csv,
)
from app.components.filters import apply_filters, render_sidebar_filters
from app.pages import alerts, cascades, dataset, delays, overview, routes, warehouses

PROJECT_NAME = "Cascading Delay Intelligence"

PAGES = {
    "Overview": overview.render,
    "Dataset explorer": dataset.render,
    "Delay analysis": delays.render,
    "Routes": routes.render,
    "Warehouses": warehouses.render,
    "Cascades": cascades.render,
    "Alerts": alerts.render,
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
    st.sidebar.header("Data source")
    available = discover_processed_datasets()
    options = [p.name for p in available] + ["Demo dataset (synthetic)"]
    choice = st.sidebar.selectbox("Dataset", options, key="dataset_choice")
    if choice == "Demo dataset (synthetic)":
        st.sidebar.warning("Demo data: synthetic, for UI exploration only.")
        return _cached_demo().copy(deep=True), "demo", True
    try:
        frame = _cached_load(str(next(p for p in available if p.name == choice)))
    except (StopIteration, FileNotFoundError, OSError) as exc:
        st.error(f"Could not load dataset: {exc}")
        return pd.DataFrame(), choice, False
    return frame.copy(deep=True), choice, False


def main() -> None:
    st.set_page_config(page_title=PROJECT_NAME, page_icon=":truck:", layout="wide")
    st.title(PROJECT_NAME)
    st.sidebar.header("Navigation")
    page = st.sidebar.radio("Page", list(PAGES.keys()), key="nav_page")

    full, label, is_demo = _select_dataset()
    if full.empty:
        st.info(
            "No integrated dataset available. Run the data pipeline "
            "(ingestion to integration) or explore the demo dataset."
        )
        return
    if is_demo:
        st.info("Viewing DEMO data - synthetic records for UI exploration only.")

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
    st.sidebar.caption(f"{len(filtered):,} of {len(full):,} records selected.")
    if page == "Dataset explorer":
        PAGES[page](filtered, full, dataset_name=label)
    else:
        PAGES[page](filtered, full)


if __name__ == "__main__":
    main()
