"""Plotly figure builders for the dashboard (pure functions, no Streamlit).

Generates production-grade analytical charts following Datadog and Grafana
conventions: high contrast, clean gridlines, precise data points, and standard
telemetry palettes.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

# Engineering tokens
FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif'
THEME_FONT = dict(family=FONT_FAMILY, size=11, color="#7d8590")
TITLE_FONT = dict(family=FONT_FAMILY, size=12, color="#e6edf3")
GRID_COLOR = "#21262d"
BORDER_COLOR = "#30363d"

COLOR_BLUE = "#58a6ff"
COLOR_DELAYED = "#f85149"
COLOR_ON_TIME = "#3fb950"
COLOR_CASCADE = "#bc8cff"


def _base_layout(title: str) -> dict:
    return dict(
        title=dict(text=title, font=TITLE_FONT, x=0.01, y=0.96),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=THEME_FONT,
        margin=dict(l=40, r=20, t=40, b=35),
        xaxis=dict(
            showgrid=True,
            gridcolor=GRID_COLOR,
            zerolinecolor=GRID_COLOR,
            tickfont=THEME_FONT,
            title_font=dict(color="#8b949e", size=11, family=FONT_FAMILY),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=GRID_COLOR,
            zerolinecolor=GRID_COLOR,
            tickfont=THEME_FONT,
            title_font=dict(color="#8b949e", size=11, family=FONT_FAMILY),
        ),
        legend=dict(
            font=dict(color="#c9d1d9", size=11),
            bgcolor="#161b22",
            bordercolor=BORDER_COLOR,
            borderwidth=1,
        ),
        hoverlabel=dict(
            bgcolor="#161b22",
            bordercolor=BORDER_COLOR,
            font=dict(family="JetBrains Mono, monospace", size=11, color="#f0f6fc"),
        ),
    )


def _empty_figure(title: str, message: str = "No data available") -> go.Figure:
    figure = go.Figure()
    layout = _base_layout(title)
    layout["xaxis"]["visible"] = False
    layout["yaxis"]["visible"] = False
    figure.update_layout(**layout)
    figure.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(color="#6e7681", size=12, family=FONT_FAMILY),
    )
    return figure


def trend_line(
    trend: pd.DataFrame,
    x_column: str = "period",
    y_column: str = "delay_rate",
    title: str = "Delay rate over time",
) -> go.Figure:
    """Line chart of a time-series table."""
    if trend.empty or x_column not in trend.columns or y_column not in trend.columns:
        return _empty_figure(title)
    series = trend.sort_values(x_column, kind="mergesort")
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=series[x_column].astype(str),
            y=pd.to_numeric(series[y_column], errors="coerce"),
            mode="lines+markers",
            name=y_column,
            line=dict(color=COLOR_BLUE, width=1.75),
            marker=dict(size=5, color=COLOR_BLUE),
            hovertemplate="<b>%{x}</b><br>" + y_column + ": %{y:.1f}<extra></extra>",
        )
    )
    layout = _base_layout(title)
    layout["xaxis"]["title"] = "Period"
    layout["yaxis"]["title"] = y_column
    figure.update_layout(**layout)
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
    """Vertical bar chart from an aggregated table."""
    if table.empty or x_column not in table.columns or y_column not in table.columns:
        return _empty_figure(title)
    frame = table.head(top_n)
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=frame[x_column].astype(str),
            y=pd.to_numeric(frame[y_column], errors="coerce"),
            marker=dict(
                color="#1f6feb",
                line=dict(color="#388bfd", width=1),
            ),
            hovertemplate="<b>%{x}</b><br>" + (y_label or y_column) + ": %{y}<extra></extra>",
        )
    )
    layout = _base_layout(title)
    layout["xaxis"]["title"] = x_label or x_column
    layout["yaxis"]["title"] = y_label or y_column
    figure.update_layout(**layout)
    return figure


def delay_status_donut(delayed: int, on_time: int, title: str = "Delayed vs on-time") -> go.Figure:
    """Donut chart with direct numeric labels."""
    if (delayed or 0) + (on_time or 0) <= 0:
        return _empty_figure(title)
    figure = go.Figure(
        data=[
            go.Pie(
                labels=["Delayed", "On-time"],
                values=[delayed, on_time],
                hole=0.6,
                textinfo="label+value+percent",
                marker=dict(
                    colors=[COLOR_DELAYED, COLOR_ON_TIME],
                    line=dict(color="#0d1117", width=2),
                ),
                textfont=dict(family=FONT_FAMILY, size=11, color="#f0f6fc"),
                hovertemplate="<b>%{label}</b>: %{value:,} (%{percent})<extra></extra>",
            )
        ]
    )
    layout = _base_layout(title)
    figure.update_layout(**layout)
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
    figure.add_trace(
        go.Bar(
            x=counts.index.astype(str),
            y=counts.to_numpy(),
            marker=dict(
                color="#8957e5",
                line=dict(color=COLOR_CASCADE, width=1),
            ),
            hovertemplate="Depth: <b>%{x}</b><br>Count: %{y:,}<extra></extra>",
        )
    )
    layout = _base_layout(title)
    layout["xaxis"]["title"] = "Cascade depth"
    layout["yaxis"]["title"] = "Shipments"
    figure.update_layout(**layout)
    return figure


def journey_timeline(events: pd.DataFrame, title: str = "Shipment journey") -> go.Figure:
    """Timeline of one shipment's ordered events."""
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
    for flag, name, symbol, color in (
        (True, "Delayed event", "diamond", COLOR_DELAYED),
        (False, "On-time event", "circle", COLOR_ON_TIME),
    ):
        mask = delayed == flag
        if not mask.any():
            continue
        figure.add_trace(
            go.Scatter(
                x=times[mask],
                y=frame.loc[mask, "_event_seq"],
                mode="markers+text",
                name=name,
                marker=dict(size=10, symbol=symbol, color=color, line=dict(color="#ffffff", width=1)),
                text=[labels[i] for i in range(len(frame)) if mask[i]],
                textposition="top center",
                textfont=dict(family=FONT_FAMILY, size=10, color="#8b949e"),
                hoverinfo="text",
            )
        )
    layout = _base_layout(title)
    layout["xaxis"]["title"] = "Event time"
    layout["yaxis"]["title"] = "Event sequence"
    figure.update_layout(**layout)
    return figure
