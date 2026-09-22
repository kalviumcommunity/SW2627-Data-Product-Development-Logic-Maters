"""Warehouse analysis page: associations for investigation (never causal claims)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis.warehouse_analysis import (
    top_delayed_warehouses,
    transfer_activity,
    warehouse_metrics,
    warehouse_trends,
)
from app.components.charts import bar_chart, trend_line


def render(filtered: pd.DataFrame, full: pd.DataFrame) -> None:
    st.header("Warehouse analysis")
    st.caption("High delay rates flag patterns for investigation - not proof of cause.")
    if filtered.empty:
        st.info("No records match the selected filters.")
        return
    try:
        metrics = warehouse_metrics(filtered)
    except ValueError as exc:
        st.info(f"Warehouse metrics unavailable: {exc}")
        return
    if metrics.empty:
        st.info("No warehouse data in the current selection.")
        return

    st.subheader("Warehouses with the highest observed delay rates")
    col_chart, col_table = st.columns([3, 2])
    with col_chart:
        st.plotly_chart(
            bar_chart(
                metrics,
                "warehouse",
                "delay_rate",
                "Observed delay rate by warehouse",
                y_label="Delay rate (%)",
            ),
            width="stretch",
        )
    with col_table:
        st.dataframe(top_delayed_warehouses(metrics, n=10), width="stretch")

    st.subheader("Warehouse detail")
    choice = st.selectbox("Select warehouse for deep dive", metrics["warehouse"].tolist())
    st.dataframe(metrics[metrics["warehouse"] == choice], width="stretch")

    _render_transfers(filtered)

    st.subheader("Warehouse volume over time")
    try:
        trends = warehouse_trends(filtered, freq="D")
    except ValueError as exc:
        st.info(f"Warehouse trends unavailable: {exc}")
        return
    warehouse_trend = trends[trends["warehouse"] == choice]
    if warehouse_trend.empty:
        st.info(f"No timestamped records for warehouse {choice}.")
        return
    st.plotly_chart(
        trend_line(
            warehouse_trend,
            y_column="shipments",
            title=f"Shipments over time - {choice}",
        ),
        width="stretch",
    )


def _render_transfers(filtered: pd.DataFrame) -> None:
    st.subheader("Transfer activity")
    activity = transfer_activity(filtered)
    shown = False
    col1, col2 = st.columns(2)
    cols = [col1, col2]
    for idx, endpoint in enumerate(("source_warehouse", "destination_warehouse")):
        detail = activity.get(endpoint, {})
        if detail.get("available"):
            shown = True
            with cols[idx]:
                st.markdown(f"**By {endpoint.replace('_', ' ').title()}**")
                st.dataframe(detail["activity"].head(10), width="stretch")
    if not shown:
        st.info("No transfer endpoint columns present in this dataset.")


if __name__ == "__main__":
    from app.components.standalone import bootstrap_standalone_page

    bootstrap_standalone_page("Warehouses", render)
