"""Route analysis page: factual per-route metrics (no scores, no rankings as best/worst)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis.route_analysis import route_metrics, route_trends, top_delayed_routes
from app.components.charts import bar_chart, trend_line


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


if __name__ == "__main__":
    from app.components.standalone import bootstrap_standalone_page

    bootstrap_standalone_page("Routes", render)
