"""Delay analysis page: distributions, reasons, trends, segments."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis.delay_analysis import (
    available_dimensions,
    delay_by_segment,
    delay_over_time,
    delay_reason_breakdown,
    rolling_delay_rate,
)
from analysis.eda import get_delay_distribution
from app.components.charts import bar_chart, trend_line


def render(filtered: pd.DataFrame, full: pd.DataFrame) -> None:
    st.header("Delay analysis")
    if filtered.empty:
        st.info("No records match the selected filters.")
        return
    _render_distribution(filtered)
    _render_reasons(filtered)
    _render_trend(filtered)
    _render_segments(filtered)


def _render_distribution(filtered: pd.DataFrame) -> None:
    st.subheader("Delay duration distribution")
    result = get_delay_distribution(filtered)
    if not result["available"]:
        st.info("No delay duration column present.")
        return
    if result["delayed_records"] == 0:
        st.info("No delayed records in the current selection.")
        return
    stats = result["stats"]
    cols = st.columns(4)
    cols[0].metric("Delayed records", f"{result['delayed_records']:,}")
    cols[1].metric("Mean", f"{stats['mean']:.1f}")
    cols[2].metric("Median", f"{stats['median']:.1f}")
    cols[3].metric("Max", f"{stats['max']:.1f}")
    st.plotly_chart(
        bar_chart(result["histogram"], "bin_start", "count",
                  "Delayed records by duration bin",
                  x_label="Duration bin start", y_label="Records"),
        width="stretch",
    )


def _render_reasons(filtered: pd.DataFrame) -> None:
    st.subheader("Delay reasons")
    try:
        breakdown = delay_reason_breakdown(filtered)
    except ValueError as exc:
        st.info(f"Reason analysis unavailable: {exc}")
        return
    if breakdown.empty:
        st.info("No delay reasons in the current selection.")
        return
    st.plotly_chart(
        bar_chart(breakdown, "delay_reason", "records", "Records by delay reason"),
        width="stretch",
    )
    st.dataframe(breakdown, width="stretch")


def _render_trend(filtered: pd.DataFrame) -> None:
    st.subheader("Delays over time")
    try:
        trend = delay_over_time(filtered, freq="D")
    except ValueError as exc:
        st.info(f"Time analysis unavailable: {exc}")
        return
    if trend.empty:
        st.info("No timestamped records in the current selection.")
        return
    st.plotly_chart(trend_line(trend, y_column="delayed_shipments",
                               title="Delayed shipments over time"),
                    width="stretch")
    if len(trend) >= 2:
        rolled = rolling_delay_rate(trend, window=7)
        st.plotly_chart(
            trend_line(rolled.dropna(subset=["rolling_avg_delay_rate_7"]),
                       y_column="rolling_avg_delay_rate_7",
                       title="7-day rolling average delay rate"),
            width="stretch",
        )
        if bool(rolled.attrs.get("sparse_warning")):
            st.caption("Fewer than 7 periods: rolling values are partial.")


def _render_segments(filtered: pd.DataFrame) -> None:
    st.subheader("Delay by segment")
    dims = available_dimensions(filtered)
    options = [d for d in (dims["route"], *dims["warehouses"], dims["delay_reason"]) if d]
    if not options:
        st.info("No segment dimensions (route/warehouse/reason) present.")
        return
    choice = st.selectbox("Segment dimension", options)
    st.dataframe(delay_by_segment(filtered, choice), width="stretch")
