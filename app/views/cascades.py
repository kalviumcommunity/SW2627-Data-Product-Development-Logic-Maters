"""Cascade Intelligence - Cascades investigation index.

Central index for every delay propagation chain, sorted by operational impact.
Filters: status / severity / location / disruption type / search.
Sort: impact score / propagated delay / shipments affected.
"""

from __future__ import annotations

import streamlit as st

from app import api_client
from app.components import ui


@st.cache_data(show_spinner=False, ttl=120)
def _load(status: str, severity: str) -> dict:
    return api_client.list_cascades(
        status=None if status == "All" else status,
        severity=None if severity == "All" else severity,
    )


def render(navigate) -> None:
    ui.page_header(
        "Cascades",
        "Every identified delay propagation chain — ranked by operational impact. Open one to investigate.",
    )

    # Row 1: search + status + severity.
    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        search = st.text_input(
            "Search",
            placeholder="Search by ID, disruption type, or location (e.g. CAS-0117, Road Closure, Kolkata)…",
            label_visibility="collapsed",
        )
    with f2:
        status = st.selectbox("Status", ["All", "ACTIVE", "RESOLVED"], label_visibility="collapsed")
    with f3:
        severity = st.selectbox("Severity", ["All", "CRITICAL", "HIGH", "MEDIUM", "LOW"], label_visibility="collapsed")

    # Row 2: location + disruption type + sort (client-side, from real API values).
    g1, g2, g3 = st.columns([1, 1, 1])
    with g1:
        loc_filter = st.text_input(
            "Location filter",
            placeholder="Filter by origin facility (e.g. Kolkata, MAA-01)…",
            label_visibility="collapsed",
        )
    with g2:
        disr_filter = st.text_input(
            "Disruption filter",
            placeholder="Filter by disruption type (e.g. Road Closure)…",
            label_visibility="collapsed",
        )
    with g3:
        sort_by = st.selectbox(
            "Sort by",
            ["Operational impact", "Propagated delay", "Shipments affected", "Deliveries at risk"],
            label_visibility="collapsed",
        )

    try:
        with st.spinner("Loading cascades…"):
            payload = _load(status, severity)
    except Exception as exc:
        if ui.error_state("Unable to load cascades.", "The intelligence service could not be reached."):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Technical detail: {exc}")
        return

    cascades = payload.get("cascades", [])
    if search:
        q = search.lower()
        cascades = [
            c for c in cascades
            if q in str(c.get("cascade_id", "")).lower()
            or q in str(c.get("root_cause", "")).lower()
            or q in str(c.get("origin_location", "")).lower()
        ]
    if loc_filter:
        ql = loc_filter.lower()
        cascades = [c for c in cascades if ql in str(c.get("origin_location", "")).lower()]
    if disr_filter:
        qd = disr_filter.lower()
        cascades = [c for c in cascades if qd in str(c.get("root_cause", "")).lower()]

    # Sort primarily by operational impact (backend impact_score); alternatives are explicit.
    if sort_by == "Propagated delay":
        cascades = sorted(cascades, key=lambda c: c.get("propagated_delay_hours", 0) or 0, reverse=True)
    elif sort_by == "Shipments affected":
        cascades = sorted(cascades, key=lambda c: c.get("affected_shipments", 0) or 0, reverse=True)
    elif sort_by == "Deliveries at risk":
        cascades = sorted(cascades, key=lambda c: c.get("deliveries_at_risk", 0) or 0, reverse=True)
    else:
        cascades = sorted(cascades, key=lambda c: c.get("impact_score", 0) or 0, reverse=True)

    if not cascades:
        ui.empty_state("No cascades match these filters", "Try adjusting the status, severity, location, or search query.")
        return

    st.caption(f"Showing {len(cascades[:50])} of {payload.get('total', len(cascades))} cascading events · sorted by {sort_by.lower()}")

    for c in cascades[:50]:
        cid = c.get("cascade_id", "")
        sev = str(c.get("severity", "")).upper()
        rc = c.get("root_cause", "Disruption")
        origin = c.get("origin_location", "Network Location")
        ships = c.get("affected_shipments", 0)
        sla = c.get("deliveries_at_risk", 0)
        locs = c.get("affected_locations", 0)
        delivs = c.get("affected_deliveries", 0)
        prop_h = c.get("propagated_delay_hours", "—")
        tot_h = c.get("total_delay_hours", "—")

        ui.html(
            f"""
            <div class="ci-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; flex-wrap:wrap; gap:6px;">
                    <div>
                        <span class="mono" style="font-weight:700; font-size:0.88rem; color:#0F172A;">{cid}</span>
                        <span style="margin-left:8px;">{ui.severity_badge(sev)} {ui.status_badge(c.get("status"))}</span>
                    </div>
                    <span class="mono" style="font-size:0.76rem; color:#64748B;">Impact {c.get("impact_score", "—")}</span>
                </div>
                <div style="font-size:1rem; font-weight:600; color:#0F172A; margin-bottom:2px;">
                    {rc} at {origin}
                </div>
                <div style="font-size:0.82rem; color:#475569; margin-top:6px; line-height:1.6;">
                    <b>{ui.fmt_int(ships)}</b> shipments affected ·
                    <b>{ui.fmt_int(locs)}</b> facilities ·
                    <b>{ui.fmt_int(sla)}</b> of {ui.fmt_int(delivs)} deliveries at risk<br>
                    <span class="mono">+{prop_h}h propagated · {tot_h}h total</span>
                    <span style="color:#94A3B8;"> · depth loads in detail view</span>
                </div>
            </div>
            """
        )
        if st.button("Investigate cascade →", key=f"btn_cas_card_{cid}", use_container_width=True):
            navigate("cascade_detail", cascade_id=cid)

    if len(cascades) > 50:
        st.caption(f"Showing top 50 results of {len(cascades)} — refine filters to narrow.")

    ui.glossary_box(["Cascade", "Root Delay", "Propagated Delay", "Blast Radius"])
