"""Cascade Intelligence - analytical charts (Plotly builders).

Every chart answers one operational question in a clean, restrained light palette.
No 3D, no gradients, minimal clutter.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import plotly.graph_objects as go

FONT = '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
THEME_FONT = dict(family=FONT, size=11, color="#64748B")
TITLE_FONT = dict(family=FONT, size=13, color="#0F172A")
GRID = "#F1F5F9"
ZEROLINE = "#E2E8F0"
HOVER = dict(
    bgcolor="#FFFFFF",
    bordercolor="#CBD5E1",
    font=dict(family="JetBrains Mono, monospace", size=11, color="#0F172A"),
)


def _layout(title: str) -> dict:
    return dict(
        title=dict(text=title, font=TITLE_FONT, x=0.01, y=0.96),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=THEME_FONT,
        margin=dict(l=45, r=20, t=44, b=40),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor=ZEROLINE, tickfont=THEME_FONT),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor=ZEROLINE, tickfont=THEME_FONT),
        hoverlabel=HOVER,
    )


def _empty(title: str, message: str = "No data available") -> go.Figure:
    fig = go.Figure()
    layout = _layout(title)
    layout["xaxis"]["visible"] = False
    layout["yaxis"]["visible"] = False
    fig.update_layout(**layout)
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(color="#94A3B8", size=12, family=FONT),
    )
    return fig


def severity_mix(cascades: List[Dict[str, Any]], title: str = "Cascade impact — how large are active cascades?") -> go.Figure:
    """Horizontal bars of affected shipments per cascade, coloured by severity."""
    if not cascades:
        return _empty(title)
    colour = {"CRITICAL": "#DC2626", "HIGH": "#EA580C", "MEDIUM": "#D97706", "LOW": "#16A34A"}
    rows = sorted(cascades, key=lambda c: c.get("affected_shipments", 0))[-15:]
    fig = go.Figure()
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        subset = [c for c in rows if str(c.get("severity", "")).upper() == sev]
        if not subset:
            continue
        fig.add_trace(go.Bar(
            y=[c.get("cascade_id") for c in subset],
            x=[c.get("affected_shipments", 0) for c in subset],
            orientation="h",
            name=sev,
            marker=dict(color=colour[sev], line=dict(color="#FFFFFF", width=0.5)),
            hovertemplate="<b>%{y}</b><br>Shipments: %{x}<extra>" + sev + "</extra>",
        ))
    layout = _layout(title)
    layout["xaxis"]["title"] = "Affected shipments"
    layout["barmode"] = "stack"
    layout["legend"] = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    fig.update_layout(**layout)
    return fig


def delay_causes(disruptions: List[Dict[str, Any]], title: str = "Delay causes — what types of disruptions are occurring?") -> go.Figure:
    """Bar chart of disruption counts by type."""
    if not disruptions:
        return _empty(title)
    df = pd.DataFrame(disruptions)
    if "disruption_type" not in df.columns:
        return _empty(title)
    counts = df["disruption_type"].value_counts().head(10)
    fig = go.Figure(go.Bar(
        x=counts.index.astype(str),
        y=counts.to_numpy(),
        marker=dict(color="#2563EB", line=dict(color="#1D4ED8", width=0.5)),
        hovertemplate="<b>%{x}</b><br>Occurrences: %{y}<extra></extra>",
    ))
    layout = _layout(title)
    layout["xaxis"]["title"] = "Disruption type"
    layout["yaxis"]["title"] = "Occurrences"
    fig.update_layout(**layout)
    return fig


def delay_by_location(locations: List[Dict[str, Any]], title: str = "Delay by location — which facilities experience the most delay?") -> go.Figure:
    """Top locations by average delay, highlighting bottlenecks."""
    if not locations:
        return _empty(title)
    rows = sorted(locations, key=lambda l: l.get("average_delay_minutes", 0) or 0, reverse=True)[:10]
    fig = go.Figure(go.Bar(
        x=[l.get("location_name", l.get("location_id")) for l in rows],
        y=[l.get("average_delay_minutes", 0) for l in rows],
        marker=dict(color=["#DC2626" if l.get("is_bottleneck") else "#2563EB" for l in rows]),
        hovertemplate="<b>%{x}</b><br>Avg delay: %{y:.1f} min<extra></extra>",
    ))
    layout = _layout(title)
    layout["xaxis"]["title"] = "Facility"
    layout["yaxis"]["title"] = "Average delay (min)"
    fig.update_layout(**layout)
    return fig


def depth_distribution(cascades: List[Dict[str, Any]], title: str = "Cascade depth — how far do delays propagate?") -> go.Figure:
    """Histogram of cascade depths derived from detail payloads."""
    depths = []
    for c in cascades:
        d = c.get("cascade_depth", c.get("depth"))
        if d is not None:
            try:
                depths.append(int(d))
            except (TypeError, ValueError):
                continue
    if not depths:
        return _empty(title, "Depth detail loads per-cascade — open a cascade for its propagation depth.")
    counts = pd.Series(depths).value_counts().sort_index()
    fig = go.Figure(go.Bar(
        x=counts.index.astype(str),
        y=counts.to_numpy(),
        marker=dict(color="#4F46E5"),
        hovertemplate="Depth %{x}: %{y} cascades<extra></extra>",
    ))
    layout = _layout(title)
    layout["xaxis"]["title"] = "Propagation depth (levels)"
    layout["yaxis"]["title"] = "Cascades"
    fig.update_layout(**layout)
    return fig


def sla_impact(deliveries_at_risk: int, total_deliveries: int, title: str = "Delivery SLA impact — how much customer impact is being created?") -> go.Figure:
    """Clean donut chart of at-risk vs protected deliveries."""
    safe = max((total_deliveries or 0) - (deliveries_at_risk or 0), 0)
    if (deliveries_at_risk or 0) + safe <= 0:
        return _empty(title)
    fig = go.Figure(go.Pie(
        labels=["SLA breached / at risk", "Within SLA"],
        values=[deliveries_at_risk, safe],
        hole=0.65,
        textinfo="label+value",
        marker=dict(colors=["#DC2626", "#16A34A"], line=dict(color="#FFFFFF", width=2)),
        textfont=dict(family=FONT, size=11, color="#0F172A"),
        hovertemplate="<b>%{label}</b>: %{value:,} (%{percent})<extra></extra>",
    ))
    fig.update_layout(**_layout(title))
    return fig


def risk_factor_bars(risk: Dict[str, Any], title: str = "Deterministic risk drivers") -> go.Figure:
    """Factor breakdown of one shipment's deterministic risk score."""
    factors = (risk or {}).get("factors", {}) or {}
    labels = {
        "buffer_erosion_score": "Delivery buffer erosion",
        "downstream_dependency_score": "Downstream dependencies",
        "cascade_propagation_score": "Cascade propagation",
        "priority_and_hub_congestion_score": "Priority + hub congestion",
    }
    names, vals = [], []
    for key, label in labels.items():
        try:
            names.append(label)
            vals.append(float(factors.get(key, 0) or 0))
        except (TypeError, ValueError):
            continue
    if not names:
        return _empty(title)
    fig = go.Figure(go.Bar(
        y=names,
        x=vals,
        orientation="h",
        marker=dict(color=["#DC2626" if v >= 0.7 else ("#D97706" if v >= 0.4 else "#16A34A") for v in vals]),
        hovertemplate="<b>%{y}</b>: %{x:.2f}<extra></extra>",
    ))
    layout = _layout(title)
    layout["xaxis"] = dict(range=[0, 1.05], title="Factor score (0–1)", showgrid=True, gridcolor=GRID, tickfont=THEME_FONT)
    fig.update_layout(**layout)
    return fig
