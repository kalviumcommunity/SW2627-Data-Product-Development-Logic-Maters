"""Cascade Intelligence - Risk Monitor (operational risk queue).

Each item shows current delay, dependencies, delivery impact, and WHY at risk
(drivers, never colour alone). Filters: level / location / risk reason / search.
"""

from __future__ import annotations

import streamlit as st

from app import api_client
from app.components import ui


REASON_GROUPS = {
    "All reasons": None,
    "SLA breach / buffer exhausted": ["breach", "buffer", "sla"],
    "Downstream dependencies": ["downstream", "holds up"],
    "Cascade propagation": ["cascade", "propagat"],
    "Hub disruption": ["disruption", "facility"],
    "Priority cargo": ["priority", "express", "critical"],
}


def render(navigate) -> None:
    ui.page_header(
        "Risks",
        "Operational risk queue — shipments whose delivery buffers are compromised, with reasons.",
    )

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        level = st.selectbox("Risk level", ["All", "CRITICAL", "HIGH", "MEDIUM", "LOW"])
    with c2:
        limit = st.selectbox("Show records", [25, 50, 100], index=0)
    with c3:
        q = st.text_input(
            "Search",
            placeholder="Search by SHP- ID or risk driver reason…",
            label_visibility="collapsed",
        )

    c4, c5 = st.columns([1, 1])
    with c4:
        loc_q = st.text_input(
            "Location filter",
            placeholder="Filter by facility in reason (e.g. LOC-MAA-02)…",
            label_visibility="collapsed",
        )
    with c5:
        reason_group = st.selectbox("Risk reason", list(REASON_GROUPS.keys()), label_visibility="collapsed")

    try:
        with st.spinner("Loading operational risk profiles…"):
            payload = api_client.get_risks(
                limit=int(limit),
                risk_level=None if level == "All" else level,
            )
    except Exception as exc:
        if ui.error_state("Unable to load risk profiles.", "The intelligence service could not be reached."):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Technical detail: {exc}")
        return

    ships = payload.get("shipments", [])
    if q:
        ql = q.lower()
        ships = [
            s for s in ships
            if ql in str(s.get("shipment_id", "")).lower()
            or any(ql in str(r).lower() for r in (s.get("reasons", []) or []))
        ]
    if loc_q:
        ll = loc_q.lower()
        ships = [s for s in ships if any(ll in str(r).lower() for r in (s.get("reasons", []) or []))]
    needles = REASON_GROUPS.get(reason_group)
    if needles:
        ships = [s for s in ships
                 if any(any(n in str(r).lower() for n in needles) for r in (s.get("reasons", []) or []))]

    # Sort by operational urgency: risk score, then delay, then dependencies.
    ships = sorted(
        ships,
        key=lambda s: (
            s.get("risk_score", 0) or 0,
            (s.get("metrics", {}) or {}).get("current_delay_minutes", 0) or 0,
            (s.get("metrics", {}) or {}).get("downstream_dependencies", 0) or 0,
        ),
        reverse=True,
    )

    st.caption(f"{len(ships)} shipments requiring operational attention · sorted by risk score")

    if not ships:
        ui.empty_state("No shipments at this risk level", "Try selecting a different risk filter or clearing the search.")
        return

    for r in ships:
        _render_risk_card(r, navigate)

    ui.glossary_box(["Risk Score", "Dependency", "Blast Radius"])


def _render_risk_card(r: dict, navigate) -> None:
    sid = r.get("shipment_id", "")
    m = r.get("metrics", {}) or {}
    reasons = r.get("reasons", []) or []
    delay_m = m.get("current_delay_minutes", 0)
    deps_m = m.get("downstream_dependencies", 0)
    delivery = r.get("delivery_details", {}) or {}
    level = r.get("risk_level", "HIGH")

    sla_txt = delivery.get("delivery_status", "—")
    sla_risk = delivery.get("risk_reason", "")
    score = r.get("risk_score", "—")

    ui.html(
        f"""
        <div class="ci-risk-item">
            <div class="ci-risk-title">
                <div>
                    {ui.risk_badge(level)}
                    <b class="mono" style="margin-left:6px; font-size:0.88rem;">{sid}</b>
                    <span class="mono" style="font-size:0.74rem; color:#64748B; margin-left:8px;">score {score}</span>
                </div>
                <span class="mono" style="font-size:0.76rem; color:#64748B; text-align:right;">
                    +{ui.fmt_int(delay_m)}m delay · {ui.fmt_int(deps_m)} deps · {sla_txt}
                </span>
            </div>
            <div style="font-size:0.78rem; color:#475569; margin-top:6px;">
                Delivery impact: <b>{sla_txt}</b>{f' — {sla_risk}' if sla_risk else ''}
                {' · <b style="color:#DC2626;">SLA breached</b>' if not m.get('customer_sla_met', True) else ''}
            </div>
            <div style="font-size:0.75rem; font-weight:700; color:#64748B; text-transform:uppercase; margin-top:8px; letter-spacing:0.04em;">
                Why at risk?
            </div>
            <div style="margin-top:2px;">
                {''.join(f'<div class="ci-risk-bullet">{x}</div>' for x in reasons[:4]) if reasons else '<div class="ci-risk-bullet">Operational delay exceeds buffer</div>'}
            </div>
        </div>
        """
    )
    if st.button("Inspect shipment →", key=f"risk_mon_{sid}", use_container_width=True):
        navigate("shipment_detail", shipment_id=sid)
