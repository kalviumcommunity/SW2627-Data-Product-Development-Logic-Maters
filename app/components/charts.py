"""Plotly figure builders for the dashboard (pure functions, no Streamlit).

Every builder accepts analysis-layer outputs and returns a
``plotly.graph_objects.Figure``. Empty inputs yield a blank figure with a
"No data" annotation instead of raising, so pages stay robust under
restrictive filters.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go


def _empty_figure(title: str, message: str = "No data to display") -> go.Figure:
    figure = go.Figure()
    figure.update_layout(title=title, xaxis={"visible": False}, yaxis={"visible": False})
    figure.add_annotation(
        text=message, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False
    )
    return figure


def trend_line(
    trend: pd.DataFrame,
    x_column: str = "period",
    y_column: str = "delay_rate",
    title: str = "Delay rate over time",
) -> go.Figure:
    """Line chart of a time-series table (e.g. delay_over_time output)."""
    if trend.empty or x_column not in trend.columns or y_column not in trend.columns:
        return _empty_figure(title)
    series = trend.sort_values(x_column, kind="mergesort")
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=series[x_column].astype(str), y=pd.to_numeric(series[y_column], errors="coerce"),
            mode="lines+markers", name=y_column,
        )
    )
    figure.update_layout(title=title, xaxis_title="Period", yaxis_title=y_column)
    return figure


def bar_chart(
    table: pd.DataFrame,
    x_column: str,
    y_column: str,
    title: str,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
    top_n: int = 15,
) -> go.Figure:
    """Vertical bar chart from an aggregated table (top_n rows kept)."""
    if table.empty or x_column not in table.columns or y_column not in table.columns:
        return _empty_figure(title)
    frame = table.head(top_n)
    figure = go.Figure()
    figure.add_trace(
        go.Bar(x=frame[x_column].astype(str), y=pd.to_numeric(frame[y_column], errors="coerce"))
    )
    figure.update_layout(
        title=title, xaxis_title=x_label or x_column, yaxis_title=y_label or y_column
    )
    return figure


def delay_status_donut(delayed: int, on_time: int, title: str = "Delayed vs on-time") -> go.Figure:
    """Donut chart with direct numeric labels (not color-only)."""
    if (delayed or 0) + (on_time or 0) <= 0:
        return _empty_figure(title)
    figure = go.Figure(
        data=[
            go.Pie(
                labels=["Delayed", "On-time"],
                values=[delayed, on_time],
                hole=0.5,
                textinfo="label+value+percent",
            )
        ]
    )
    figure.update_layout(title=title)
    return figure


def depth_chart(candidates: pd.DataFrame, title: str = "Cascade depth distribution") -> go.Figure:
    """Bar chart of cascade_depth value counts."""
    if candidates.empty or "cascade_depth" not in candidates.columns:
        return _empty_figure(title)
    counts = (
        pd.to_numeric(candidates["cascade_depth"], errors="coerce")
        .value_counts()
        .sort_index()
    )
    figure = go.Figure()
    figure.add_trace(go.Bar(x=counts.index.astype(str), y=counts.to_numpy()))
    figure.update_layout(title=title, xaxis_title="Cascade depth", yaxis_title="Shipments")
    return figure


def journey_timeline(events: pd.DataFrame, title: str = "Shipment journey") -> go.Figure:
    """Timeline of one shipment's ordered events.

    Expects ``reconstruct_shipment_journey()`` output: ``_event_time``,
    ``_event_seq``, ``_is_delayed`` plus ``src_*`` context columns. Delayed
    events are marked by shape as well as color, with text details on hover
    and in the marker label.
    """
    needed = {"_event_time", "_event_seq", "_is_delayed"}
    if events.empty or not needed.issubset(events.columns):
        return _empty_figure(title)
    frame = events.sort_values("_event_seq", kind="mergesort").reset_index(drop=True)
    times = pd.to_datetime(frame["_event_time"], errors="coerce", utc=True).dt.tz_convert(None)
    delayed = frame["_is_delayed"].astype(bool).to_numpy()
    labels = []
    for _, row in frame.iterrows():
        parts = [f"Event {int(row['_event_seq'])}"]
        for key in ("src_delay_duration", "src_delay_reason", "src_route_id",
                    "src_warehouse_id", "src_status"):
            if key in frame.columns and pd.notna(row[key]):
                parts.append(f"{key[4:]}={row[key]}")
        labels.append("<br>".join(parts))
    figure = go.Figure()
    for flag, name, symbol in ((True, "Delayed event", "diamond"), (False, "Event", "circle")):
        mask = delayed == flag
        if not mask.any():
            continue
        figure.add_trace(
            go.Scatter(
                x=times[mask], y=frame.loc[mask, "_event_seq"],
                mode="markers+text",
                name=name,
                marker={"size": 14, "symbol": symbol},
                text=[labels[i] for i in range(len(frame)) if mask[i]],
                textposition="top center",
                hoverinfo="text",
            )
        )
    figure.update_layout(title=title, xaxis_title="Event time", yaxis_title="Event sequence")
    return figure
