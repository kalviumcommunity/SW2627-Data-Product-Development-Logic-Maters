"""Cascade Intelligence - shared UI primitives (Streamlit rendering).

Restrained, modern operations intelligence UI components.
Colours communicate operational meaning only:
- Green  → healthy / on time (#16A34A)
- Amber  → warning / medium risk (#D97706)
- Red    → disruption / high risk (#DC2626)
- Blue   → information / active selection (#2563EB)
- Gray   → neutral / supporting information (#64748B)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

# --- Semantic design tokens (single source of truth for Python side) --------
TOKENS = {
    "primary": "#2563EB",
    "green": "#16A34A",
    "amber": "#D97706",
    "red": "#DC2626",
    "blue": "#2563EB",
    "gray": "#64748B",
    "border": "#E2E8F0",
    "card_bg": "#FFFFFF",
    "panel_bg": "#F8FAFC",
}

SEVERITY_STYLE = {
    "CRITICAL": "critical",
    "HIGH": "critical",
    "MEDIUM": "warning",
    "LOW": "success",
    "ACTIVE": "critical",
    "RESOLVED": "neutral",
    "STABLE": "success",
    "ELEVATED_RISK": "warning",
}

RISK_STYLE = {
    "CRITICAL": "critical",
    "HIGH": "critical",
    "MEDIUM": "warning",
    "LOW": "success",
}

GLOSSARY: Dict[str, str] = {
    "Shipment": "A physical movement of goods through the logistics network.",
    "Event": "A recorded milestone in a shipment's journey (pickup, departure, transfer, delivery).",
    "Dependency": "A relationship where one logistics operation relies on another completing first.",
    "Root Delay": "The initial delay introduced by a disruption at the origin of a cascade.",
    "Propagated Delay": "Delay that occurs downstream because an operation waited on an upstream dependency.",
    "Cascade": "A chain of related delays spreading through dependent operations.",
    "Blast Radius": "The number of downstream operations affected by a disruption.",
    "Risk Score": "A deterministic indicator (0–1) of operational vulnerability from delay and dependency signals. Not a machine-learning probability.",
}


# --- Formatting helpers (never invent data; render "Not available") ----------

def fmt_minutes(mins: Any) -> str:
    try:
        m = int(float(mins))
    except (TypeError, ValueError):
        return "Not available"
    if m < 0:
        return "Not available"
    if m < 60:
        return f"{m}m"
    return f"{m // 60}h {m % 60:02d}m"


def fmt_hours(hours: Any) -> str:
    try:
        h = float(hours)
    except (TypeError, ValueError):
        return "Not available"
    return f"{h:.1f}h"


def fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "Not available"


def badge(text: str, kind: str = "neutral") -> str:
    """HTML status pill. Kinds: critical, warning, info, success, neutral."""
    return f'<span class="status-pill {kind}">{text}</span>'


def severity_badge(severity: Optional[str]) -> str:
    s = (severity or "Unknown").upper()
    kind = SEVERITY_STYLE.get(s, "neutral")
    label = {"ELEVATED_RISK": "ELEVATED RISK"}.get(s, s.replace("_", " "))
    return badge(label, kind)


def risk_badge(level: Optional[str]) -> str:
    lvl = (level or "Unknown").upper()
    return badge(f"{lvl} RISK" if lvl in RISK_STYLE else lvl, RISK_STYLE.get(lvl, "neutral"))


def status_badge(status: Optional[str]) -> str:
    s = (status or "Unknown").upper()
    return badge(s, SEVERITY_STYLE.get(s, "neutral"))


# --- Clean HTML Safe Rendering Primitives -----------------------------------

def clean_html(markup: str) -> str:
    """Strip leading/trailing indentation from each line to prevent markdown code block detection."""
    if not markup:
        return ""
    return " ".join(line.strip() for line in markup.strip().splitlines() if line.strip())


def html(markup: str) -> None:
    """Render HTML safely in the main view without markdown code-block triggers."""
    st.markdown(clean_html(markup), unsafe_allow_html=True)


def sidebar_html(markup: str) -> None:
    """Render HTML safely in the sidebar without markdown code-block triggers."""
    st.sidebar.markdown(clean_html(markup), unsafe_allow_html=True)


# --- Structural Layout & Component Primitives --------------------------------

def page_header(title: str, context: Optional[str] = None) -> None:
    """Clean operational page title and one-sentence context."""
    html(
        f"""
        <div class="ci-page-header">
            <div class="ci-page-title">{title}</div>
            {f'<div class="ci-page-context">{context}</div>' if context else ''}
        </div>
        """
    )


def section_title(title: str, subtitle: Optional[str] = None) -> None:
    """Consistent section title with optional subtitle."""
    html(
        f"""
        <div class="ci-section-title">{title}</div>
        {f'<div class="ci-section-sub">{subtitle}</div>' if subtitle else ''}
        """
    )


def kpi_row(cards: List[Dict[str, str]]) -> None:
    """Render KPI cards as ONE responsive grid (equal heights, no column squeeze)."""
    cells = "".join(
        f"""
        <div class="ci-kpi-card">
            <div class="ci-kpi-label">{card.get('label', '')}</div>
            <div class="ci-kpi-value">{card.get('value', '—')}</div>
            <div class="ci-kpi-context">{card.get('context', '')}</div>
        </div>
        """
        for card in cards
    )
    html(f'<div class="ci-kpi-grid">{cells}</div>')


def hero_section(headline: str, detail: Optional[str] = None, lead: str = "Network Overview") -> None:
    """Dashboard hero section providing context before raw metrics."""
    html(
        f"""
        <div class="ci-hero-box">
            <div class="ci-hero-lead">{lead}</div>
            <div class="ci-hero-title">{headline}</div>
            {f'<div class="ci-hero-detail">{detail}</div>' if detail else ''}
        </div>
        """
    )


def active_cascade_card(
    cascade: Dict[str, Any],
    navigate,
    flow_steps: Optional[List[str]] = None,
) -> None:
    """Visual centerpiece for the active cascading disruption."""
    cid = cascade.get("cascade_id") or cascade.get("cascadeId") or ""
    sev = str(cascade.get("severity", "HIGH")).upper()
    rc_type = cascade.get("root_cause") or cascade.get("rootCause", {}).get("type", "Disruption")
    origin = cascade.get("origin_location") or cascade.get("rootCause", {}).get("locationName", "Network Location")
    initial_delay = cascade.get("initial_delay_formatted") or cascade.get("rootCause", {}).get("initialDelayFormatted")
    if not initial_delay:
        mins = cascade.get("initial_delay_minutes") or cascade.get("rootCause", {}).get("initialDelayMinutes", 0)
        initial_delay = fmt_minutes(mins)

    affected_ships = cascade.get("affected_shipments") or cascade.get("impact", {}).get("affectedShipments", 0)
    sla_breaches = cascade.get("deliveries_at_risk") or cascade.get("impact", {}).get("deliveriesAtRisk", 0)
    prop_hours = cascade.get("propagated_delay_hours") or cascade.get("summary", {}).get("propagatedDelayHours", 0)

    # Build flow chain HTML
    flow_html = ""
    if flow_steps:
        flow_items = []
        for i, step in enumerate(flow_steps):
            is_first = (i == 0)
            node_class = "ci-flow-node root" if is_first else "ci-flow-node"
            flow_items.append(f'<span class="{node_class}">{step}</span>')
            if i < len(flow_steps) - 1:
                flow_items.append('<span class="ci-flow-arrow-down">↓</span>')
        flow_html = f'<div class="ci-flow-container">{"".join(flow_items)}</div>'

    html(
        f"""
        <div class="ci-centerpiece">
            <div class="ci-centerpiece-header">
                <div>
                    <span style="font-size:0.72rem; font-weight:700; color:#DC2626; letter-spacing:0.06em; text-transform:uppercase;">
                        ACTIVE CASCADE
                    </span>
                    <span style="margin-left:8px;">{severity_badge(sev)}</span>
                </div>
                <span class="mono" style="font-size:0.8rem; color:#64748B;">{cid}</span>
            </div>
            <div class="ci-centerpiece-title">{rc_type}</div>
            <div class="ci-centerpiece-sub">{origin}</div>
            <div class="ci-centerpiece-stats">
                <div class="ci-stat-item">
                    <span class="ci-stat-num">{initial_delay}</span>
                    <span class="ci-stat-lbl">Initial delay</span>
                </div>
                <div class="ci-stat-item">
                    <span class="ci-stat-num">{fmt_int(affected_ships)}</span>
                    <span class="ci-stat-lbl">Shipments affected</span>
                </div>
                <div class="ci-stat-item">
                    <span class="ci-stat-num">{fmt_int(sla_breaches)}</span>
                    <span class="ci-stat-lbl">SLA breaches</span>
                </div>
                <div class="ci-stat-item">
                    <span class="ci-stat-num">+{fmt_hours(prop_hours)}</span>
                    <span class="ci-stat-lbl">Propagated delay</span>
                </div>
            </div>
            {flow_html}
        </div>
        """
    )
    if st.button("View cascade details →", key=f"btn_centerpiece_{cid}", type="primary", use_container_width=True):
        navigate("cascade_detail", cascade_id=cid)


def network_health_card(score: Any, status: str = "STABLE", ships_at_risk: int = 0) -> None:
    """Network health card aligned beside the active cascade."""
    try:
        v = max(0, min(100, float(score)))
    except (TypeError, ValueError):
        v = 100.0
    colour = TOKENS["green"] if v >= 80 else (TOKENS["amber"] if v >= 55 else TOKENS["red"])
    html(
        f"""
        <div class="ci-health-card">
            <div>
                <div class="ci-kpi-label">NETWORK HEALTH</div>
                <div class="ci-health-num" style="color:{colour}; margin:12px 0 4px 0;">
                    {v:.0f}<span> / 100</span>
                </div>
                <div class="ci-health-progress-bg">
                    <div class="ci-health-progress-fill" style="width:{v:.0f}%; background:{colour};"></div>
                </div>
                <div style="font-size:0.82rem; font-weight:600; color:#1E293B; margin-top:8px;">
                    {status_badge(status)}
                </div>
            </div>
            <div style="margin-top:16px; border-top:1px solid #E2E8F0; padding-top:12px; font-size:0.78rem; color:#64748B; line-height:1.45;">
                <b>{fmt_int(ships_at_risk)}</b> shipments currently exposed to operational risk thresholds.
            </div>
        </div>
        """
    )


def network_health(value: Any) -> None:
    """Compact network health indicator."""
    network_health_card(value, "ELEVATED_RISK" if value < 80 else "STABLE")


def info_card(title: str, body: str, accent: str = "blue") -> None:
    """Standard container card with subtle semantic left accent."""
    html(
        f"""
        <div class="ci-card ci-accent-{accent}">
            <div class="ci-card-title">{title}</div>
            <div class="ci-card-body">{body}</div>
        </div>
        """
    )


def explanation_block(what_happened: str, why_it_matters: str, current_impact: str) -> None:
    """Structured human-readable explanation with clear operational typography."""
    html(
        f"""
        <div class="ci-explanation-block">
            <div class="ci-explanation-q">What happened?</div>
            <div class="ci-explanation-a">{what_happened}</div>
            <div class="ci-explanation-q">Why does it matter?</div>
            <div class="ci-explanation-a">{why_it_matters}</div>
            <div class="ci-explanation-q">Current impact</div>
            <div class="ci-explanation-a">{current_impact}</div>
        </div>
        """
    )


def risk_item(
    shipment_id: str,
    risk_level: str,
    delay_minutes: Any,
    dependencies: Any,
    reasons: List[str],
    navigate,
    key_prefix: str = "risk",
) -> None:
    """Clean risk component focusing on the explanation rather than heavy colors."""
    reasons_html = "".join(f'<div class="ci-risk-bullet">{r}</div>' for r in reasons[:3])
    html(
        f"""
        <div class="ci-risk-item">
            <div class="ci-risk-title">
                <div>
                    {risk_badge(risk_level)}
                    <b class="mono" style="margin-left:6px; font-size:0.88rem;">{shipment_id}</b>
                </div>
                <span class="mono" style="font-size:0.78rem; color:#64748B;">
                    +{fmt_int(delay_minutes)}m delay · {fmt_int(dependencies)} deps
                </span>
            </div>
            <div style="font-size:0.75rem; font-weight:700; color:#64748B; text-transform:uppercase; margin-top:8px; letter-spacing:0.04em;">
                Why?
            </div>
            <div style="margin-top:2px;">
                {reasons_html if reasons_html else '<div class="ci-risk-bullet">Operational delay exceeds buffer</div>'}
            </div>
        </div>
        """
    )
    if st.button("Inspect shipment →", key=f"{key_prefix}_{shipment_id}", use_container_width=True):
        navigate("shipment_detail", shipment_id=shipment_id)


def render_timeline(items: List[Dict[str, Any]], max_items: int = 30) -> None:
    """Clear visual vertical path for event timeline with connecting line."""
    if not items:
        empty_state("No timeline records", "Timeline reconstruction is unavailable for this cascade.")
        return

    # Deduplicate identical (timestamp, shipment, type) rows for readability.
    seen, deduped = set(), []
    for t in items:
        key = (t.get("timestamp"), t.get("shipmentId"), t.get("eventType"))
        if key not in seen:
            seen.add(key)
            deduped.append(t)

    html_rows = []
    for t in deduped[:max_items]:
        is_root = "root" in str(t.get("eventType", "")).lower()
        bullet_class = "ci-timeline-bullet root" if is_root else "ci-timeline-bullet"
        delay_str = f"+{fmt_minutes(t.get('delayMinutes'))}" if t.get('delayMinutes') else ""
        root_tag = '<span class="status-pill critical" style="margin-right:6px;">ROOT DISRUPTION</span>' if is_root else ""

        html_rows.append(
            f"""
            <div class="ci-timeline-row">
                <div class="{bullet_class}"></div>
                <div class="ci-timeline-content">
                    <div class="ci-timeline-time">{t.get('timestamp', '')}</div>
                    <div class="ci-timeline-event">
                        {root_tag}{t.get('eventType', '')} · <span class="mono">{t.get('shipmentId', '')}</span>
                        {f' · <span style="color:#DC2626; font-weight:600;">{delay_str}</span>' if delay_str else ''}
                    </div>
                    <div class="ci-timeline-desc">
                        {t.get('locationName', '')} — {t.get('description', '')}
                    </div>
                </div>
            </div>
            """
        )

    html(f'<div class="ci-timeline-container">{"".join(html_rows)}</div>')
    if len(deduped) > max_items:
        st.caption(f"Showing {max_items} of {len(deduped)} timeline events.")


def glossary_box(items: Optional[List[str]] = None) -> None:
    """'Understanding the data' clean expandable definitions."""
    with st.expander("Understanding the data — what does this mean?"):
        for term in (items or list(GLOSSARY.keys())):
            if term in GLOSSARY:
                st.markdown(f"**{term}** — {GLOSSARY[term]}")


def empty_state(title: str, message: str) -> None:
    """Intentional, clean empty state."""
    html(
        f"""
        <div class="ci-state">
            <div class="ci-state-title">{title}</div>
            <div class="ci-state-body">{message}</div>
        </div>
        """
    )


def error_state(title: str, message: str, retry_label: str = "Retry") -> bool:
    """Clean operational error state."""
    html(
        f"""
        <div class="ci-state ci-state-error">
            <div class="ci-state-title">{title}</div>
            <div class="ci-state-body">{message}</div>
        </div>
        """
    )
    return st.button(retry_label, key=f"retry_{title}")


def skeleton_block(lines: int = 3) -> None:
    """Skeleton loader matching component shape."""
    html(
        "".join('<div class="ci-skeleton" style="height:20px; border-radius:6px; background:#F1F5F9; margin:8px 0;"></div>' for _ in range(lines))
    )


def definition_tip(term: str) -> None:
    """Small inline info note."""
    if term in GLOSSARY:
        st.caption(f"ⓘ {term}: {GLOSSARY[term]}")


def story_step(n: int, title: str, body: str) -> None:
    html(
        f"""
        <div style="display:flex; gap:12px; margin-bottom:12px;">
            <div style="width:26px; height:26px; border-radius:50%; background:#EFF6FF; border:1px solid #BFDBFE; color:#2563EB; font-size:0.75rem; font-weight:700; display:flex; align-items:center; justify-content:center; flex-shrink:0;">
                {n}
            </div>
            <div>
                <div style="font-size:0.88rem; font-weight:600; color:#0F172A;">{title}</div>
                <div style="font-size:0.82rem; color:#64748B; line-height:1.55; margin-top:2px;">{body}</div>
            </div>
        </div>
        """
    )


# --- Operational intelligence primitives -------------------------------------

def network_status_banner(status: str, summary: str = "") -> None:
    """Concise network condition banner: WHAT IS HAPPENING first."""
    s = (status or "UNKNOWN").upper()
    label = s.replace("_", " ")
    if s == "STABLE":
        bg, border, dot, text = "#F0FDF4", "#BBF7D0", "#16A34A", "#166534"
    elif s in ("CRITICAL", "HIGH"):
        bg, border, dot, text = "#FEF2F2", "#FECACA", "#DC2626", "#991B1B"
    else:
        bg, border, dot, text = "#FFFBEB", "#FDE68A", "#D97706", "#92400E"
    html(
        f"""
        <div style="background:{bg}; border:1px solid {border}; border-radius:12px;
                    padding:14px 18px; margin-bottom:16px; display:flex; gap:12px; align-items:flex-start; box-sizing:border-box;">
            <div style="width:10px; height:10px; border-radius:50%; background:{dot};
                        margin-top:5px; flex-shrink:0;"></div>
            <div>
                <div style="font-size:0.72rem; font-weight:700; letter-spacing:0.06em;
                            text-transform:uppercase; color:{text};">Network condition: {label}</div>
                {f'<div style="font-size:0.86rem; color:#334155; margin-top:4px; line-height:1.5;">{summary}</div>' if summary else ''}
            </div>
        </div>
        """
    )


def attention_card(
    kind: str,
    eyebrow: str,
    title: str,
    metrics_line: str,
    detail: str,
    button_label: str,
    navigate,
    nav_page: str,
    nav_id: str,
    key: str,
) -> None:
    """One item in the 'What needs attention?' queue."""
    accent = {"cascade": "#DC2626", "bottleneck": "#D97706", "risk": "#2563EB"}.get(kind, "#2563EB")
    html(
        f"""
        <div class="ci-card ci-attention-card" style="border-left:3px solid {accent}; padding:14px 16px;">
            <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.06em;
                        text-transform:uppercase; color:{accent}; margin-bottom:3px;">{eyebrow}</div>
            <div style="font-size:0.92rem; font-weight:700; color:#0F172A; line-height:1.3;">{title}</div>
            <div style="font-size:0.78rem; font-weight:600; color:#334155; margin-top:5px; line-height:1.4;">{metrics_line}</div>
            <div class="ci-attention-detail" style="font-size:0.78rem; color:#64748B; margin-top:4px; line-height:1.45;">{detail}</div>
        </div>
        """
    )
    if st.button(button_label, key=key, use_container_width=True):
        if nav_page == "cascade_detail":
            navigate(nav_page, cascade_id=nav_id)
        elif nav_page == "shipment_detail":
            navigate(nav_page, shipment_id=nav_id)
        elif nav_page == "location_detail":
            navigate(nav_page, location_id=nav_id)
        else:
            navigate(nav_page)


def bottleneck_compact_card(loc: dict, navigate, key_prefix: str = "bn") -> None:
    """Compact facility bottleneck card for dashboard + locations list."""
    lid = loc.get("location_id", "")
    name = loc.get("location_name", lid)
    city = loc.get("city", "")
    score = loc.get("bottleneck_score", "—")
    avg_d = loc.get("average_delay_minutes", 0) or 0
    aff = loc.get("affected_shipments", loc.get("total_shipments", 0))
    casc_n = loc.get("cascade_count", 0)
    is_bn = loc.get("is_bottleneck", False)
    pill = '<span class="status-pill critical">HIGH BOTTLENECK</span>' if is_bn else '<span class="status-pill success">STABLE</span>'
    html(
        f"""
        <div class="ci-card">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
                <div style="font-size:0.95rem; font-weight:700; color:#0F172A;">{name}</div>
                {pill}
            </div>
            <div style="font-size:0.78rem; color:#64748B; margin-top:2px;">{city} · <span class="mono">{lid}</span> · score <b class="mono">{score}</b></div>
            <div style="display:flex; gap:16px; margin-top:10px; font-size:0.8rem; color:#334155; flex-wrap:wrap;">
                <div>Affected shipments<br><b class="mono">{fmt_int(aff)}</b></div>
                <div>Cascade involvement<br><b class="mono">{fmt_int(casc_n)}</b></div>
                <div>Current delay<br><b class="mono">+{avg_d:.0f}m</b></div>
            </div>
        </div>
        """
    )
    if st.button("Inspect facility →", key=f"{key_prefix}_{lid}", use_container_width=True):
        navigate("location_detail", location_id=lid)


def delay_split_visual(
    initial_minutes: Any,
    propagated_minutes: Any,
    deliveries_at_risk: Any,
    total_minutes: Any = None,
) -> None:
    """Visually distinct: Original delay vs Downstream propagation vs Customer impact."""
    try:
        init_m = int(float(initial_minutes or 0))
    except (TypeError, ValueError):
        init_m = 0
    try:
        prop_m = int(float(propagated_minutes or 0))
    except (TypeError, ValueError):
        prop_m = 0
    try:
        sla_n = int(float(deliveries_at_risk or 0))
    except (TypeError, ValueError):
        sla_n = 0
    prop_h = prop_m / 60.0
    html(
        f"""
        <div class="ci-card" style="padding:0; overflow:hidden;">
            <div style="display:flex; flex-wrap:wrap; text-align:center; align-items:stretch;">
                <div class="ci-split-panel" style="flex:1 1 180px; min-width:0; padding:16px 12px; background:#FEF2F2; border-right:1px solid #E2E8F0;">
                    <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:#991B1B;">Initial disruption</div>
                    <div class="mono" style="font-size:1.35rem; font-weight:700; color:#991B1B; margin-top:4px; white-space:nowrap;">{fmt_minutes(init_m)}</div>
                    <div style="font-size:0.74rem; color:#991B1B;">Original delay</div>
                </div>
                <div class="ci-split-panel" style="flex:1 1 180px; min-width:0; padding:16px 12px; background:#FFFBEB; border-right:1px solid #E2E8F0;">
                    <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:#92400E;">Downstream propagation</div>
                    <div class="mono" style="font-size:1.35rem; font-weight:700; color:#92400E; margin-top:4px; white-space:nowrap;">{prop_h:.1f}h</div>
                    <div style="font-size:0.74rem; color:#92400E;">{fmt_int(prop_m)} min generated downstream</div>
                </div>
                <div class="ci-split-panel" style="flex:1 1 180px; min-width:0; padding:16px 12px; background:#FFFFFF;">
                    <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:#0F172A;">Customer impact</div>
                    <div class="mono" style="font-size:1.35rem; font-weight:700; color:#0F172A; margin-top:4px; white-space:nowrap;">{fmt_int(sla_n)}</div>
                    <div style="font-size:0.74rem; color:#64748B;">SLA breaches</div>
                </div>
            </div>
        </div>
        """
    )


def propagation_tree(propagation: list) -> None:
    """Clean visual propagation tree: ROOT → depth-1 branches → deeper levels."""
    if not propagation:
        empty_state("No propagation data", "Propagation telemetry is unavailable for this cascade.")
        return
    from collections import defaultdict
    levels: dict[int, list[dict]] = defaultdict(list)
    for n in propagation:
        try:
            d = int(n.get("depth", 0) or 0)
        except (TypeError, ValueError):
            d = 0
        levels[d].append(n)
    
    rows: list[str] = []
    for depth in sorted(levels):
        members = sorted(levels[depth], key=lambda m: str(m.get("shipmentId", "")))
        for m in members:
            sid = m.get("shipmentId", "")
            tot = m.get("totalDelayMinutes", 0)
            prop = m.get("propagatedDelayMinutes", 0)
            parent = m.get("parentShipmentId")
            try:
                tot_i, prop_i = int(tot), int(prop)
            except (TypeError, ValueError):
                tot_i, prop_i = 0, 0
            
            tag = '<span class="status-pill critical" style="font-size:0.68rem;">ROOT</span>' if depth == 0 else f'<span style="color:#94A3B8; font-size:0.76rem; font-weight:700;">L{depth}</span>'
            indent_px = min(depth * 20, 100)
            extra = f'<span style="color:#D97706; font-size:0.76rem; margin-left:6px;">(+{prop_i}m downstream)</span>' if depth > 0 and prop_i else ""
            link = f'<span style="color:#64748B; font-size:0.75rem; margin-left:6px;">waited on <b>{parent}</b></span>' if parent else ""
            
            rows.append(
                f'<div style="padding-left:{indent_px}px; display:flex; align-items:center; gap:8px; margin:6px 0; flex-wrap:wrap;">'
                f'{tag} <span class="mono" style="font-weight:700; color:#0F172A; font-size:0.84rem;">{sid}</span>'
                f'<span style="color:#DC2626; font-weight:600; font-size:0.82rem;">+{fmt_minutes(tot_i)}</span>'
                f'{extra}{link}'
                f'</div>'
            )

    html(
        f'<div class="ci-card"><div class="ci-card-title">Propagation chain (root → downstream)</div>'
        f'<div style="display:flex; flex-direction:column; gap:4px; margin-top:8px;">{"".join(rows)}</div>'
        f'</div>'
    )


def journey_steps(steps: list[dict]) -> None:
    """Vertical shipment journey: Origin ↓ Facility ↓ Transfer ↓ … ↓ Destination."""
    if not steps:
        empty_state("No journey data", "Journey reconstruction is unavailable.")
        return
    colour = {
        "origin": "#2563EB", "hub": "#2563EB", "transfer": "#64748B",
        "destination": "#16A34A", "delay": "#DC2626",
    }
    rows: list[str] = []
    for i, s in enumerate(steps):
        c = colour.get(s.get("kind", "hub"), "#2563EB")
        rows.append(
            f"""
            <div style="display:flex; gap:10px; align-items:flex-start;">
                <div style="display:flex; flex-direction:column; align-items:center;">
                    <div style="width:14px; height:14px; border-radius:50%; background:{c};
                                border:2px solid #FFFFFF; box-shadow:0 0 0 1px {c}; flex-shrink:0; margin-top:3px;"></div>
                    {'' if i == len(steps) - 1 else '<div style="width:2px; height:22px; background:#CBD5E1;"></div>'}
                </div>
                <div style="padding-bottom:{'0' if i == len(steps) - 1 else '14px'};">
                    <div style="font-size:0.85rem; font-weight:600; color:#0F172A;">{s.get('label', '')}</div>
                    <div style="font-size:0.78rem; color:#64748B;">{s.get('sub', '')}</div>
                </div>
            </div>
            """
        )
    html(f'<div class="ci-card">{"".join(rows)}</div>')


def metric_grid(items: list[dict]) -> None:
    """Compact metric grid inside a card — even CSS-grid columns, shared baseline."""
    cells = "".join(
        f"""
        <div style="min-width:0;">
            <div style="font-size:0.68rem; font-weight:700; letter-spacing:0.05em;
                        text-transform:uppercase; color:#64748B;">{m.get('label', '')}</div>
            <div class="mono" style="font-size:1.02rem; font-weight:700; color:#0F172A; margin-top:2px; overflow-wrap:break-word;">{m.get('value', '—')}</div>
            {f"<div style='font-size:0.74rem; color:#64748B; margin-top:2px; line-height:1.45;'>{m.get('sub', '')}</div>" if m.get('sub') else ''}
        </div>
        """
        for m in items
    )
    html(f'<div class="ci-card"><div class="ci-metric-grid">{cells}</div></div>')
