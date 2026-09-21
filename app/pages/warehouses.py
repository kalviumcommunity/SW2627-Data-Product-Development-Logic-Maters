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
    st.dataframe(top_delayed_warehouses(metrics, n=10), width="stretch")
    st.plotly_chart(
        bar_chart(metrics, "warehouse", "delay_rate",
                  "Observed delay rate by warehouse", y_label="Delay rate (%)"),
        width="stretch",
    )
    st.subheader("Warehouse detail")
    choice = st.selectbox("Warehouse", metrics["warehouse"].tolist())
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
        trend_line(warehouse_trend, y_column="shipments",
                   title=f"Shipments over time - {choice}"),
        width="stretch",
    )


def _render_transfers(filtered: pd.DataFrame) -> None:
    st.subheader("Transfer activity")
    activity = transfer_activity(filtered)
    shown = False
    for endpoint in ("source_warehouse", "destination_warehouse"):
        detail = activity.get(endpoint, {})
        if detail.get("available"):
            shown = True
            st.write(f"By {endpoint.replace('_', ' ')}")
            st.dataframe(detail["activity"].head(10), width="stretch")
    if not shown:
        st.info("No transfer endpoint columns present in this dataset.")
