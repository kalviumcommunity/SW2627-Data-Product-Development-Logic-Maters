"""Dataset explorer page: structure, samples, and missingness (read-only)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis.eda import (
    get_dataset_summary,
    get_delay_flag_summary,
    get_missingness_summary,
)


def render(filtered: pd.DataFrame, full: pd.DataFrame, dataset_name: str = "") -> None:
    st.header("Dataset explorer")
    if dataset_name:
        st.caption(f"Source: `{dataset_name}` (read-only; the dashboard never writes data).")
    if full.empty:
        st.info("No dataset loaded. Load the integrated dataset or use demo data.")
        return
    summary = get_dataset_summary(full)
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Rows", f"{summary['row_count']:,}")
    col_b.metric("Columns", f"{summary['column_count']:,}")
    col_c.metric(
        "Total shipments",
        f"{summary['total_shipments']:,}" if summary["total_shipments"] is not None else "n/a",
    )
    st.subheader("Columns and types")
    st.dataframe(
        pd.DataFrame(
            {"column": summary["columns"],
             "dtype": [summary["dtypes"][c] for c in summary["columns"]]}
        ),
        width="stretch",
    )
    st.subheader("Sample records (current filters applied)")
    if filtered.empty:
        st.info("No records match the selected filters.")
    else:
        st.dataframe(filtered.head(100), width="stretch")
    st.subheader("Missing values")
    st.dataframe(get_missingness_summary(full), width="stretch")
    st.subheader("Delay signal")
    flag_summary = get_delay_flag_summary(full)
    if flag_summary["available"]:
        st.write(
            f"Method: `{flag_summary['info'].get('method')}` on "
            f"`{flag_summary['info'].get('source_column')}` - "
            f"{flag_summary['delayed_records']:,} delayed records "
            f"({flag_summary['delayed_records_pct']:.1f}%)."
        )
    else:
        st.info("No delay signal column present in this dataset.")
