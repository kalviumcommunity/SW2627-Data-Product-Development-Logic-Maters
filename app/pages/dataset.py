"""Dataset explorer page: structure, samples, and missingness (read-only)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis.eda import (
    get_dataset_summary,
    get_delay_flag_summary,
    get_missingness_summary,
)


@st.cache_data(show_spinner=False)
def _cached_filtered_csv(filtered: pd.DataFrame) -> bytes:
    """CSV export bytes for the current filter selection.

    Cached so the (potentially large) export is not re-serialized on every
    unrelated rerun while the selection is unchanged.
    """
    return filtered.to_csv(index=False).encode("utf-8")


def render(filtered: pd.DataFrame, full: pd.DataFrame, dataset_name: str = "") -> None:
    st.header("Dataset explorer")
    if dataset_name:
        st.caption(f"Source: `{dataset_name}` (read-only; the dashboard never writes data).")
    if full.empty:
        st.info("No dataset loaded. Load the integrated dataset or use demo data.")
        return
    summary = get_dataset_summary(full)
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Rows", f"{summary['row_count']:,}")
    col_b.metric("Total Columns", f"{summary['column_count']:,}")
    col_c.metric(
        "Total shipments",
        f"{summary['total_shipments']:,}" if summary["total_shipments"] is not None else "n/a",
    )

    st.subheader("Sample records (current filters applied)")
    if filtered.empty:
        st.info("No records match the selected filters.")
    else:
        st.dataframe(filtered.head(100), width="stretch")
        st.download_button(
            label="Export Filtered CSV",
            data=_cached_filtered_csv(filtered),
            file_name="filtered_logistics_data.csv",
            mime="text/csv",
        )

    col_cols, col_missing = st.columns(2)
    with col_cols:
        st.subheader("Schema definition")
        st.dataframe(
            pd.DataFrame(
                {
                    "column": summary["columns"],
                    "dtype": [summary["dtypes"][c] for c in summary["columns"]],
                }
            ),
            width="stretch",
        )

    with col_missing:
        st.subheader("Missing values")
        st.dataframe(get_missingness_summary(full), width="stretch")

    st.subheader("Delay signal configuration")
    flag_summary = get_delay_flag_summary(full)
    if flag_summary["available"]:
        st.markdown(
            f"""
            <div class="detail-panel">
                Resolution: <code>{flag_summary['info'].get('method')}</code> &bull; Column: <code>{flag_summary['info'].get('source_column')}</code> &bull; 
                Delayed records: <span class="mono" style="color: #f0f6fc; font-weight: 600;">{flag_summary['delayed_records']:,}</span> (<span class="mono" style="color: #f85149;">{flag_summary['delayed_records_pct']:.1f}%</span>)
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("No delay signal column present in this dataset.")


if __name__ == "__main__":
    from app.components.standalone import bootstrap_standalone_page

    bootstrap_standalone_page("Dataset explorer", render)
