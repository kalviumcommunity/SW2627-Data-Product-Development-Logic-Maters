"""Cascade Intelligence - Locations list and Location detail views."""

from __future__ import annotations

import streamlit as st

from app import api_client
from app.components import ui


@st.cache_data(show_spinner=False, ttl=300)
def _load_all(bottlenecks_only: bool) -> dict:
    return api_client.list_locations(bottlenecks_only=bottlenecks_only)


@st.cache_data(show_spinner=False, ttl=300)
def _load_one(location_id: str) -> dict:
    return api_client.get_location(location_id)


def render_list(navigate) -> None:
    ui.page_header(
        "Locations",
        "Facility health, bottleneck diagnosis, and delay roles across network hubs.",
    )

    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    with c1:
        q = st.text_input(
            "Search facilities",
            placeholder="Search by facility name, city, or ID (e.g. Kolkata, LOC-CCU-01)…",
            label_visibility="collapsed",
        )
    with c2:
        only_bn = st.checkbox("Bottlenecks only", value=False)

    try:
        with st.spinner("Loading facility telemetry…"):
            payload = _load_all(only_bn)
    except Exception as exc:
        if ui.error_state("Unable to load facilities.", "The intelligence service could not be reached."):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Technical detail: {exc}")
        return

    locations = payload.get("locations", [])
    if q:
        ql = q.lower()
        locations = [
            l for l in locations
            if ql in str(l.get("location_name", "")).lower()
            or ql in str(l.get("location_id", "")).lower()
            or ql in str(l.get("city", "")).lower()
        ]

    st.caption(f"{len(locations)} facilities monitored")

    if not locations:
        ui.empty_state("No facilities match criteria", "Try adjusting the search query or bottleneck filter.")
        return

    for loc in locations[:40]:
        lid = loc.get("location_id", "")
        name = loc.get("location_name", "")
        city = loc.get("city", "")
        is_bn = loc.get("is_bottleneck", False)
        rate = (loc.get("delay_rate", 0) or 0) * 100
        avg_d = loc.get("average_delay_minutes", 0) or 0
        cascades_c = loc.get("cascade_count", 0)

        badge_html = '<span class="status-pill critical">BOTTLENECK</span>' if is_bn else '<span class="status-pill success">HEALTHY</span>'

        ui.html(
            f"""
            <div class="ci-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        {badge_html}
                        <span class="mono" style="font-weight:700; font-size:0.85rem; color:#0F172A; margin-left:8px;">{lid}</span>
                    </div>
                    <span class="mono" style="font-size:0.78rem; color:#64748B;">Bottleneck Score: {loc.get('bottleneck_score', '—')}</span>
                </div>
                <div style="font-size:1rem; font-weight:600; color:#0F172A; margin:4px 0 2px 0;">
                    {name} ({city})
                </div>
                <div style="font-size:0.82rem; color:#475569; margin-top:4px;">
                    <b>{ui.fmt_int(loc.get('total_shipments'))}</b> shipments handled ·
                    Delay rate <b>{rate:.1f}%</b> ·
                    Mean delay <b>+{avg_d:.0f}m</b> ·
                    <b>{cascades_c}</b> cascades touched
                </div>
            </div>
            """
        )
        if st.button("Inspect facility operations →", key=f"btn_loc_card_{lid}", use_container_width=True):
            navigate("location_detail", location_id=lid)


def render_detail(navigate, location_id: str) -> None:
    if st.button("← Back to locations", key="btn_back_locations"):
        navigate("locations")

    try:
        with st.spinner("Loading facility profile…"):
            story = _load_one(location_id)
    except api_client.NotFoundError:
        ui.empty_state(f"Facility {location_id} Not Found", "Check the identifier or return to the facility list.")
        return
    except Exception as exc:
        if ui.error_state("Unable to load facility profile.", "The intelligence service could not be reached."):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Technical detail: {exc}")
        return

    is_bn = story.get("isBottleneck", False)
    badge_html = '<span class="status-pill critical">BOTTLENECK</span>' if is_bn else '<span class="status-pill success">OPERATING NORMALLY</span>'

    ui.html(
        f"""
        <div style="margin: 12px 0 20px 0;">
            <div class="mono" style="font-size:0.72rem; font-weight:700; letter-spacing:0.08em; color:#64748B;">FACILITY {story.get('locationId', location_id)}</div>
            <div style="display:flex; align-items:center; gap:10px; margin-top:4px; flex-wrap:wrap;">
                <span style="font-size:1.4rem; font-weight:700; color:#0F172A;">
                    {story.get('locationName', location_id)}
                </span>
                {badge_html}
            </div>
            <div style="font-size:0.88rem; color:#475569; margin-top:4px;">
                {story.get('locationType', 'Facility')} · {story.get('city', '')}, {story.get('state', '')}
            </div>
        </div>
        """
    )

    # ---- Facility health ----
    ui.section_title("Facility health", "Is this facility creating, absorbing, or transmitting delay?")
    ui.kpi_row([
        {"label": "SHIPMENTS HANDLED", "value": ui.fmt_int(story.get("totalShipments")),
         "context": "Origin and inbound volume"},
        {"label": "DELAY RATE", "value": f"{round((story.get('delayRate', 0) or 0) * 100, 1)}%",
         "context": f"{ui.fmt_int(story.get('delayedShipments'))} delayed departures"},
        {"label": "AVERAGE DELAY", "value": f"+{(story.get('averageDelayMinutes', 0) or 0):.0f}m",
         "context": "Mean departure delay"},
        {"label": "CASCADE INVOLVEMENT", "value": ui.fmt_int(story.get("cascadeInvolvementCount")),
         "context": f"{ui.fmt_hours((story.get('propagatedDelayMinutes', 0) or 0) / 60)} propagated"},
    ])
    _render_delay_role(story)

    reasons = story.get("bottleneckReasons", []) or []
    diag_body = (
        f"{story.get('operationalSummary', 'Facility operating within design parameters.')}<br><br>"
        + "<br>".join(f"• {r}" for r in reasons)
    )
    ui.info_card("Operational summary", diag_body, accent="red" if is_bn else "green")



    # ---- Incoming risk / Outgoing impact (from disruptions + dependencies) ----
    ui.section_title("Incoming risk → Outgoing impact", "What hits this facility, and what it passes downstream.")
    _render_incoming_outgoing(location_id, story, navigate)



    # ---- Cascade history ----
    active = story.get("activeCascades", []) or []
    ui.section_title("Cascade history", "How often this facility appears in delay chains.")
    ui.metric_grid([
        {"label": "Chains involving facility", "value": ui.fmt_int(len(active)),
         "sub": f"{ui.fmt_int(story.get('cascadeInvolvementCount', 0))} scored involvements"},
        {"label": "Propagated delay", "value": ui.fmt_hours((story.get("propagatedDelayMinutes", 0) or 0) / 60),
         "sub": "Transmitted downstream"},
        {"label": "Dependency volume", "value": ui.fmt_int(story.get("dependencyVolume", 0)),
         "sub": "Cross-dock connections"},
        {"label": "Bottleneck score", "value": str(story.get("bottleneckScore", "—")),
         "sub": "Bottleneck" if is_bn else "Within limits"},
    ])
    if not active:
        ui.empty_state("No linked cascades", "No cascading disruptions currently involve this facility.")
    else:
        st.caption(f"{len(active)} delay chains identified — showing up to 8")
        cols = st.columns(min(len(active[:8]), 4) or 1, vertical_alignment="top")
        for idx, cid in enumerate(active[:8]):
            col = cols[idx % len(cols)]
            with col:
                if st.button(f"Inspect {cid} →", key=f"btn_loc_cas_{location_id}_{cid}", use_container_width=True):
                    navigate("cascade_detail", cascade_id=cid)

    # Recent disruptions at this facility
    ui.section_title("Logged incidents", "Disruption event records occurring at this facility.")
    try:
        dis = api_client.list_disruptions()
        mine = [d for d in dis.get("disruptions", []) if d.get("location_id") == location_id][:8]
        if not mine:
            ui.empty_state("No recent incidents", "No disruption logs recorded at this location.")
        else:
            for d in mine:
                ui.html(
                    f"""
                    <div class="ci-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                {ui.severity_badge(d.get("severity"))}
                                <b style="margin-left:6px; color:#0F172A;">{d.get("disruption_type", "Incident")}</b>
                            </div>
                            <span class="mono" style="font-size:0.78rem; color:#64748B;">{d.get("disruption_id")}</span>
                        </div>
                        <div class="ci-card-body" style="margin-top:6px; font-size:0.82rem;">
                            {d.get("description", "")}<br>
                            <span style="color:#64748B;">
                                Duration: {d.get("duration_minutes", "—")} min · Root cause: {d.get("root_cause", "—")}
                            </span>
                        </div>
                    </div>
                    """
                )
    except Exception:
        st.caption("Disruption telemetry unavailable.")

    ui.glossary_box(["Blast Radius", "Propagated Delay"])


def _render_delay_role(story: dict) -> None:
    """Verdict: creating, absorbing, or transmitting delay — from real scores."""
    delay_rate = story.get("delayRate", 0) or 0
    casc_n = story.get("cascadeInvolvementCount", 0) or 0
    prop_m = story.get("propagatedDelayMinutes", 0) or 0
    is_bn = story.get("isBottleneck", False)
    if is_bn and prop_m >= 3000 and casc_n >= 15:
        role, colour, msg = ("TRANSMITTING DELAY", "#DC2626",
            "This facility both generates departure delays and passes large volumes downstream — "
            "it amplifies cascades rather than absorbing them.")
    elif delay_rate >= 0.35:
        role, colour, msg = ("CREATING DELAY", "#D97706",
            "Departure delays originate here at an elevated rate. Downstream facilities inherit this lateness.")
    elif casc_n >= 10:
        role, colour, msg = ("TRANSMITTING DELAY", "#D97706",
            "The facility frequently appears inside cascade chains — delay passes through even when it does not originate here.")
    else:
        role, colour, msg = ("ABSORBING / STABLE", "#16A34A",
            "Delay mostly terminates here within buffer tolerance. No evidence of systematic downstream transmission.")
    ui.html(
        f"""
        <div class="ci-card" style="border-left:3px solid {colour};">
            <div style="font-size:0.7rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:{colour};">Delay role: {role}</div>
            <div style="font-size:0.86rem; color:#334155; margin-top:6px; line-height:1.55;">{msg}</div>
        </div>
        """
    )


def _render_incoming_outgoing(location_id: str, story: dict, navigate) -> None:
    """Upstream disruptions affecting this facility vs downstream exposure."""
    incoming: list[str] = []
    outgoing: list[str] = []
    try:
        dis = api_client.list_disruptions()
        mine = [d for d in dis.get("disruptions", []) if d.get("location_id") == location_id][:5]
        for d in mine:
            incoming.append(
                f"<b>{d.get('disruption_type', 'Incident')}</b> ({d.get('severity', '')}) — "
                f"{d.get('description', '')} <span style='color:#64748B;'>[{d.get('disruption_id', '')}]</span>"
            )
    except Exception:
        incoming = []
    # Outgoing: cascades + dependency volume from the story itself.
    cascades = story.get("activeCascades", []) or []
    dep_vol = story.get("dependencyVolume", 0) or 0
    prop_m = story.get("propagatedDelayMinutes", 0) or 0
    if cascades:
        outgoing.append(
            f"<b>{ui.fmt_int(len(cascades))} downstream chains</b> depend on this hub "
            f"({ui.fmt_int(dep_vol)} transfer connections, {ui.fmt_int(prop_m)} min propagated)."
        )
    else:
        outgoing.append("No downstream chains currently depend on this hub.")

    c1, c2 = st.columns(2, vertical_alignment="top")
    with c1:
        ui.html(
            f"""<div class="ci-card" style="height:100%;"><div class="ci-card-title">Incoming risk (upstream pressure)</div>
            <div class="ci-card-body">{'<br><br>'.join(incoming) if incoming else 'No active disruption logs at this facility.'}</div></div>"""
        )
    with c2:
        ui.html(
            f"""<div class="ci-card" style="height:100%;"><div class="ci-card-title">Outgoing impact (downstream exposure)</div>
            <div class="ci-card-body">{'<br><br>'.join(outgoing)}</div></div>"""
        )
