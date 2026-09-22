"""Route analysis page: factual per-route metrics (no scores, no rankings as best/worst)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis.route_analysis import route_metrics, route_trends, top_delayed_routes
from analysis.route_risk import (
    route_cascade_risk,
    route_period_cascade_rates,
    build_shipment_risk_table,
    stage_transition_matrix,
)
from analysis.cascade_analysis import detect_cascade_candidates
from app.components.charts import bar_chart, trend_line


@st.cache_data(show_spinner=False)
def _cached_route_risk(filtered: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Route cascade risk for the current filter selection (cached)."""
    return route_cascade_risk(filtered)


@st.cache_data(show_spinner=False)
def _cached_transitions(filtered: pd.DataFrame) -> pd.DataFrame:
    """Observed stage-transition matrix for the selection (cached)."""
    candidates, _ = detect_cascade_candidates(filtered)
    return stage_transition_matrix(candidates)


@st.cache_data(show_spinner=False)
def _cached_shipment_table(filtered: pd.DataFrame) -> pd.DataFrame:
    """Shipment-grain risk rows for the selection (cached)."""
    shipments, _ = build_shipment_risk_table(filtered)
    return shipments


def render(filtered: pd.DataFrame, full: pd.DataFrame) -> None:
    st.header("Route analysis")
    if filtered.empty:
        st.info("No records match the selected filters.")
        return
    try:
        metrics = route_metrics(filtered)
    except ValueError as exc:
        st.info(f"Route metrics unavailable: {exc}")
        return
    if metrics.empty:
        st.info("No route data in the current selection.")
        return

    st.subheader("Routes with the highest observed delay rates")
    col_chart, col_table = st.columns([3, 2])
    with col_chart:
        st.plotly_chart(
            bar_chart(
                metrics,
                "route",
                "delay_rate",
                "Observed delay rate by route",
                y_label="Delay rate (%)",
            ),
            width="stretch",
        )
    with col_table:
        st.dataframe(top_delayed_routes(metrics, n=10), width="stretch")

    st.subheader("Route detail")
    choice = st.selectbox("Select route for deep dive", metrics["route"].tolist())
    detail = metrics[metrics["route"] == choice]
    st.dataframe(detail, width="stretch")

    st.subheader("Route volume over time")
    try:
        trends = route_trends(filtered, freq="D")
    except ValueError as exc:
        st.info(f"Route trends unavailable: {exc}")
        return
    route_trend = trends[trends["route"] == choice]
    if route_trend.empty:
        st.info(f"No timestamped records for route {choice}.")
        return
    st.plotly_chart(
        trend_line(
            route_trend,
            y_column="shipments",
            title=f"Shipments over time - {choice}",
        ),
        width="stretch",
    )

    _render_cascade_risk(filtered)


def _render_cascade_risk(filtered: pd.DataFrame) -> None:
    st.subheader("Route cascade risk")
    st.caption(
        "Historical empirical indicators: how often an initial delay on a "
        "route was followed by a downstream delay. Descriptive only — not "
        "an ML prediction of future delays."
    )
    try:
        risk, _ = _cached_route_risk(filtered)
    except ValueError as exc:
        st.info(f"Cascade risk unavailable: {exc}")
        return
    if risk.empty:
        st.info("No delayed shipments in the current selection.")
        return

    st.dataframe(
        risk[
            [
                "route", "risk_class", "cascade_rate", "cascade_probability",
                "cascade_recurrence", "average_cascade_depth",
                "max_cascade_depth", "delayed_shipments", "cascade_shipments",
                "observed_periods",
            ]
        ],
        width="stretch",
    )

    col_rate, col_rec = st.columns(2)
    with col_rate:
        st.plotly_chart(
            bar_chart(
                risk, "route", "cascade_rate",
                "Observed cascade rate by route",
                y_label="Cascade rate (%)",
            ),
            width="stretch",
        )
    with col_rec:
        st.plotly_chart(
            bar_chart(
                risk, "route", "cascade_recurrence",
                "Cascade recurrence by route",
                y_label="Share of delay weeks with a cascade",
            ),
            width="stretch",
        )

    st.subheader("Period cascade rate - route deep dive")
    shipments = _cached_shipment_table(filtered)
    period_rates = route_period_cascade_rates(shipments)
    choice = st.selectbox(
        "Select route for risk trend", risk["route"].tolist(), key="risk_route"
    )
    route_periods = period_rates[period_rates["route"] == choice]
    if route_periods.empty:
        st.info(f"No timestamped delays for route {choice}.")
    else:
        st.plotly_chart(
            trend_line(
                route_periods.assign(period=route_periods["period"].astype(str)),
                x_column="period",
                y_column="cascade_rate",
                title=f"Weekly cascade rate - {choice}",
            ),
            width="stretch",
        )

    st.subheader("Observed stage transitions")
    transitions = _cached_transitions(filtered)
    if transitions.empty:
        st.info("No stage transitions observed in the current selection.")
    else:
        st.dataframe(transitions, width="stretch")


if __name__ == "__main__":
    from app.components.standalone import bootstrap_standalone_page

    bootstrap_standalone_page("Routes", render)
