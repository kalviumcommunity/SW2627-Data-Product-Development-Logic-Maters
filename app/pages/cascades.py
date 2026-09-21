"""Cascade analysis page: candidates, patterns, and shipment inspector."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis.cascade_analysis import (
    cascade_by_route,
    cascade_by_warehouse,
    cascade_summary_metrics,
    detect_cascade_candidates,
    get_shipment_events,
    reconstruct_shipment_journey,
    root_cause_signals,
)
from analysis.kpis import compute_shipment_kpis
from app.components.charts import depth_chart, journey_timeline


def render(filtered: pd.DataFrame, full: pd.DataFrame) -> None:
    st.header("Cascade analysis")
    st.caption(
        "Cascade candidates describe observed delay sequences "
        "(initial delay followed by downstream delay) - association, not proof of cause."
    )
    if filtered.empty:
        st.info("No records match the selected filters.")
        return
    try:
        candidates, info = detect_cascade_candidates(filtered)
    except ValueError as exc:
        st.info(f"Cascade analysis unavailable: {exc}")
        return
    total = compute_shipment_kpis(filtered)["total_shipments"]
    summary = cascade_summary_metrics(candidates, total_shipments=total)
    cols = st.columns(4)
    cols[0].metric("Cascade candidates", f"{summary['candidate_count']:,}")
    rate = summary["candidate_rate"]
    cols[1].metric("Candidate rate", f"{rate:.1f}%" if rate is not None else "n/a")
    cols[2].metric(
        "Avg cascade depth",
        f"{summary['avg_cascade_depth']:.1f}" if summary["avg_cascade_depth"] is not None else "n/a",
    )
    cols[3].metric(
        "Max cascade depth",
        f"{summary['max_cascade_depth']}" if summary["max_cascade_depth"] is not None else "n/a",
    )
    if candidates.empty:
        st.info("No cascade candidates in the current selection. A single delay is not a cascade.")
        return
    st.plotly_chart(depth_chart(candidates), width="stretch")
    st.subheader("Candidates by route")
    st.dataframe(cascade_by_route(candidates), width="stretch")
    st.subheader("Candidates by warehouse")
    st.dataframe(cascade_by_warehouse(candidates), width="stretch")
    st.subheader("Commonly observed stage signals")
    st.dataframe(root_cause_signals(candidates), width="stretch")
    _render_inspector(filtered, candidates)


def _render_inspector(filtered: pd.DataFrame, candidates: pd.DataFrame) -> None:
    st.subheader("Shipment inspector")
    choice = st.selectbox("Candidate shipment", candidates["shipment_id"].tolist())
    detail = candidates[candidates["shipment_id"] == choice].iloc[0]
    st.write(
        f"Initial delay: {detail['initial_delay_time']} "
        f"(duration {detail['initial_delay_duration']}, "
        f"reason {detail['initial_delay_reason']}, "
        f"route {detail['initial_route']}, "
        f"warehouse {detail['initial_warehouse']})"
    )
    st.write(
        f"Downstream delay observed: {detail['downstream_event_time']} "
        f"(duration {detail['downstream_delay_duration']}) - "
        f"stages: {' > '.join(str(s) for s in detail['stages'])}"
    )
    try:
        events, _ = reconstruct_shipment_journey(filtered)
    except ValueError as exc:
        st.info(f"Journey unavailable: {exc}")
        return
    st.plotly_chart(
        journey_timeline(get_shipment_events(events, str(choice)),
                         title=f"Journey timeline - {choice}"),
        width="stretch",
    )
