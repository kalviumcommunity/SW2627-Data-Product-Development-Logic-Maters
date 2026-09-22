"""Runner helper for standalone page execution in Streamlit.

When a user visits a page directly (e.g. /alerts, /cascades) or Streamlit executes
a page file as the primary script, this helper bootstraps dataset loading,
sidebar filters, and invokes the page's render function.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

# Ensure repository root is on sys.path
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd
import streamlit as st

from app.components.data_loader import (
    build_demo_dataset,
    discover_processed_datasets,
    load_processed_csv,
)
from app.components.filters import apply_filters, render_sidebar_filters
from app.components.theme import apply_theme

PROJECT_NAME = "Cascading Delay Intelligence"


@st.cache_data(show_spinner=False)
def _cached_load(path_str: str) -> pd.DataFrame:
    return load_processed_csv(path_str)


@st.cache_data(show_spinner=False)
def _cached_demo() -> pd.DataFrame:
    return build_demo_dataset()


def _select_dataset() -> tuple[pd.DataFrame, str, bool]:
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
    choice = st.sidebar.selectbox("Dataset", options, key="standalone_dataset_choice", label_visibility="collapsed")
    if choice == "Demo dataset (synthetic)":
        return _cached_demo().copy(deep=True), "demo", True
    try:
        frame = _cached_load(str(next(p for p in available if p.name == choice)))
    except (StopIteration, FileNotFoundError, OSError) as exc:
        st.error(f"Could not load dataset: {exc}")
        return pd.DataFrame(), choice, False
    return frame.copy(deep=True), choice, False


def bootstrap_standalone_page(page_name: str, render_func: Callable[..., None]) -> None:
    """Bootstrap and render a page when executed directly by Streamlit."""
    try:
        st.set_page_config(page_title=f"{page_name} - {PROJECT_NAME}", layout="wide")
    except Exception:
        pass

    apply_theme()
    st.markdown(
        f"""
        <div class="app-header-bar">
            <div class="app-breadcrumb">
                <span>{PROJECT_NAME}</span>
                <span>/</span>
                <span class="active-section">{page_name}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    full, label, is_demo = _select_dataset()
    if full.empty:
        st.info(
            "No integrated dataset available. Run the data pipeline "
            "(ingestion to integration) or explore the demo dataset."
        )
        return

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

    if page_name == "Dataset explorer":
        render_func(filtered, full, dataset_name=label)
    else:
        render_func(filtered, full)
