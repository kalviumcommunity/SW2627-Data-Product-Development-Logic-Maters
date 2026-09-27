"""Cascade Intelligence - network + propagation graph builders (Plotly only).

Light, clean directed graphs for network flow and cascade propagation.
Nodes use semantic states:
- Healthy: #16A34A (Green)
- Warning / Elevated delay: #D97706 (Amber)
- Disrupted / Root cause / Bottleneck: #DC2626 (Red)
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Tuple

import plotly.graph_objects as go

FONT = '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
MONO = '"JetBrains Mono", Consolas, monospace'


def _fig(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=dict(text=title, font=dict(family=FONT, size=13, color="#0F172A"), x=0.01, y=0.96),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=11, color="#64748B"),
        margin=dict(l=20, r=20, t=45, b=20),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor="#CBD5E1",
            font=dict(family=MONO, size=11, color="#0F172A"),
        ),
        showlegend=False,
    )
    return fig


def _layout_by_depth(nodes: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]]:
    """Layered layout: x = position within depth level, y = -depth."""
    levels: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for n in nodes:
        try:
            depth = int(n.get("depth", 0) or 0)
        except (TypeError, ValueError):
            depth = 0
        levels[depth].append(n)
    pos: Dict[str, Tuple[float, float]] = {}
    for depth in sorted(levels):
        members = sorted(levels[depth], key=lambda m: str(m.get("shipmentId", "")))
        for i, m in enumerate(members):
            x = (i - (len(members) - 1) / 2.0) * 2.2
            pos[str(m.get("shipmentId"))] = (x, -depth * 1.6)
    return pos


def cascade_graph(story: Dict[str, Any]) -> go.Figure:
    """Interactive directed propagation graph for one cascade story."""
    nodes: List[Dict[str, Any]] = story.get("propagation", []) or []
    title = f"Delay propagation chain — {story.get('cascadeId', 'cascade')} (root → downstream)"
    if not nodes:
        fig = _fig(title)
        fig.add_annotation(
            text="No propagation data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color="#94A3B8", size=12, family=FONT),
        )
        return fig

    pos = _layout_by_depth(nodes)
    fig = _fig(title)

    # Edges (parent → child)
    for n in nodes:
        parent = n.get("parentShipmentId")
        child = str(n.get("shipmentId"))
        if not parent or str(parent) not in pos or child not in pos:
            continue
        x0, y0 = pos[str(parent)]
        x1, y1 = pos[child]
        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[y0, y1],
            mode="lines",
            line=dict(color="#CBD5E1", width=1.8),
            hovertemplate=f"{parent} → {child}<br>+{n.get('propagatedDelayMinutes', 0)}m propagated<extra></extra>",
            showlegend=False,
        ))
        fig.add_annotation(
            x=x1,
            y=y1,
            ax=x0,
            ay=y0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=2,
            arrowsize=1.1,
            arrowwidth=1.5,
            arrowcolor="#94A3B8",
            standoff=14,
        )

    # Nodes
    xs, ys, texts, hovers, colours, sizes = [], [], [], [], [], []
    for n in nodes:
        sid = str(n.get("shipmentId"))
        x, y = pos[sid]
        depth = int(n.get("depth", 0) or 0)
        total = n.get("totalDelayMinutes", 0)
        prop = n.get("propagatedDelayMinutes", 0)
        xs.append(x)
        ys.append(y)
        texts.append(f"{'● ROOT<br>' if depth == 0 else ''}{sid}<br>+{total}m")
        hovers.append(
            f"<b>{sid}</b> (Level {depth})<br>"
            f"Total delay: +{total}m · Propagated: +{prop}m<br>"
            f"Route: {n.get('originLocation', '')} → {n.get('destinationLocation', '')}<br>"
            f"Dependency: {n.get('dependencyType', 'Direct transfer')}<extra></extra>"
        )
        colours.append("#DC2626" if depth == 0 else ("#EA580C" if depth == 1 else "#2563EB"))
        sizes.append(32 if depth == 0 else 24)

    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        mode="markers+text",
        text=texts,
        textposition="bottom center",
        textfont=dict(family=MONO, size=10, color="#0F172A"),
        marker=dict(size=sizes, color=colours, line=dict(color="#FFFFFF", width=2.5)),
        hovertemplate="%{hovertext}",
        hovertext=hovers,
        showlegend=False,
    ))
    max_depth = max(int(n.get("depth", 0) or 0) for n in nodes)
    fig.update_layout(height=max(360, 240 + max_depth * 110))
    return fig


def network_flow(
    locations: List[Dict[str, Any]],
    cascades: List[Dict[str, Any]],
    title: str = "Network flow — facility operational health",
) -> go.Figure:
    """Facility nodes coloured by health; links derived from cascade co-occurrence."""
    if not locations:
        fig = _fig(title)
        fig.add_annotation(
            text="No location data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color="#94A3B8", size=12, family=FONT),
        )
        return fig

    top = sorted(locations, key=lambda l: l.get("bottleneck_score", 0) or 0, reverse=True)[:16]
    n = len(top)
    pos = {}
    for i, loc in enumerate(top):
        angle = 2 * math.pi * i / max(n, 1)
        pos[loc.get("location_id")] = (math.cos(angle) * 4, math.sin(angle) * 2.8)

    # Co-occurrence edges from cascade affected_location_ids
    edges = set()
    for c in cascades[:25]:
        locs = c.get("affected_location_ids") or []
        locs = [l for l in locs if l in pos]
        for i in range(len(locs)):
            for j in range(i + 1, len(locs)):
                edges.add(tuple(sorted((locs[i], locs[j]))))

    fig = _fig(f"{title} ({len(edges)} active transfer corridors)")

    # Render edges
    for a, b in edges:
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[y0, y1],
            mode="lines",
            line=dict(color="#E2E8F0", width=1.2),
            hoverinfo="skip",
            showlegend=False,
        ))

    # Render nodes
    xs, ys, texts, hovers, colours = [], [], [], [], []
    for loc in top:
        lid = loc.get("location_id")
        x, y = pos[lid]
        xs.append(x)
        ys.append(y)
        texts.append(loc.get("city", lid))
        rate = (loc.get("delay_rate", 0) or 0) * 100
        is_bn = loc.get("is_bottleneck")
        if is_bn:
            colour = "#DC2626"
            status_text = "Bottleneck Disruption"
        elif rate >= 25:
            colour = "#D97706"
            status_text = "Elevated Delay"
        else:
            colour = "#16A34A"
            status_text = "Operating Normally"

        colours.append(colour)
        hovers.append(
            f"<b>{loc.get('location_name', lid)}</b> ({loc.get('city', '')})<br>"
            f"Status: {status_text}<br>"
            f"Delay rate: {rate:.1f}% · Mean delay: +{loc.get('average_delay_minutes', 0):.0f}m<br>"
            f"Cascades touched: {loc.get('cascade_count', 0)} · Score: {loc.get('bottleneck_score', '—')}<extra></extra>"
        )

    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        mode="markers+text",
        text=texts,
        textposition="top center",
        textfont=dict(family=FONT, size=10, color="#1E293B"),
        marker=dict(size=18, color=colours, line=dict(color="#FFFFFF", width=2.5)),
        hovertemplate="%{hovertext}",
        hovertext=hovers,
        showlegend=False,
    ))
    fig.update_layout(height=420)
    return fig
