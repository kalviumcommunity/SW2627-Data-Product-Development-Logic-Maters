"""Overview page: operational summary KPI cards, trend, and top routes."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis.cascade_analysis import cascade_summary_metrics, detect_cascade_candidates
from analysis.delay_analysis import delay_over_time
from analysis.kpis import compute_kpis
from analysis.route_analysis import route_metrics
from app.components.charts import bar_chart, delay_status_donut, trend_line
from app.components.metrics import prepare_kpi_cards


def render(filtered: pd.DataFrame, full: pd.DataFrame) -> None:
    st.header("Overview")
    if filtered.empty:
        st.info("No records match the selected filters.")
        return
    bundle = compute_kpis(filtered)
    try:
        candidates, _ = detect_cascade_candidates(filtered)
        cascade_summary = cascade_summary_metrics(
            candidates, total_shipments=bundle["shipment"]["total_shipments"]
        )
    except ValueError as exc:
        cascade_summary = {"candidate_count": None}
        st.warning(f"Cascade candidates unavailable: {exc}")
    for card in prepare_kpi_cards(bundle["shipment"], bundle["delay"], cascade_summary):
        st.metric(card["label"], card["value"])
    st.caption("KPIs reflect the current filter selection.")
    _render_trend(filtered)
    _render_routes(filtered)


def _render_trend(filtered: pd.DataFrame) -> None:
    st.subheader("Delay trend")
    try:
        trend = delay_over_time(filtered, freq="D")
    except ValueError as exc:
        st.info(f"Trend unavailable: {exc}")
        return
    if trend.empty:
        st.info("No timestamped records to trend.")
        return
    st.plotly_chart(trend_line(trend), width="stretch")


def _render_routes(filtered: pd.DataFrame) -> None:
    st.subheader("Routes by delayed shipments")
    try:
        metrics = route_metrics(filtered)
    except ValueError as exc:
        st.info(f"Route metrics unavailable: {exc}")
        return
    if metrics.empty:
        st.info("No route data available.")
        return
    st.plotly_chart(
        bar_chart(metrics, "route", "delayed_shipments",
                  "Delayed shipments by route"),
        width="stretch",
    )
    bundle = compute_kpis(filtered)
    delayed = bundle["shipment"]["delayed_shipments"] or 0
    on_time = bundle["shipment"]["on_time_shipments"] or 0
    st.plotly_chart(delay_status_donut(delayed, on_time), width="stretch")
