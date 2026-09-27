"""Cascade Intelligence - Shipments list and Shipment detail pages."""

from __future__ import annotations

import streamlit as st

from app import api_client
from app.components import intel_charts as charts
from app.components import ui


def render_list(navigate) -> None:
    ui.page_header(
        "Shipments",
        "Individual freight movements across origin, transfer hubs, and customer destinations.",
    )

    q = st.text_input(
        "Search shipments",
        placeholder="Search by ID (e.g. SHP-07128, SHP-13459)…",
        label_visibility="collapsed",
    )

    try:
        with st.spinner("Loading shipments…"):
            payload = api_client.explore("shipments", limit=25, offset=0, search=q or None)
    except Exception as exc:
        if ui.error_state("Unable to load shipments.", "The intelligence service could not be reached."):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Technical detail: {exc}")
        return

    records = payload.get("records", [])
    st.caption(f"{payload.get('total_records', 0):,} shipments recorded · showing {len(records)}")

    if not records:
        ui.empty_state("No shipments found", "Try searching for a different shipment identifier.")
        return

    for rec in records:
        raw = rec.get("raw", {})
        eid = rec.get("entityId", "")
        orig = raw.get("origin_location_id", "")
        dest = raw.get("destination_location_id", "")
        pri = raw.get("priority", "Standard")
        delay_m = raw.get("final_delay_minutes", 0)

        ui.html(
            f"""
            <div class="ci-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span class="mono" style="font-size:0.95rem; font-weight:700; color:#0F172A;">{eid}</span>
                        <span style="margin-left:8px;">{ui.status_badge(rec.get("status"))}</span>
                    </div>
                    <span class="mono" style="font-size:0.8rem; font-weight:600; color:{'#DC2626' if delay_m > 30 else '#2563EB'};">
                        +{ui.fmt_minutes(delay_m)}
                    </span>
                </div>
                <div style="font-size:0.82rem; color:#64748B; margin:4px 0 6px 0;">
                    Route: <span class="mono">{orig}</span> → <span class="mono">{dest}</span> · Priority: <b>{pri}</b>
                </div>
                <div class="ci-card-body" style="font-size:0.82rem;">
                    {rec.get("humanExplanation", "")}
                </div>
            </div>
            """
        )
        if st.button("Inspect journey story →", key=f"btn_shp_card_{eid}", use_container_width=True):
            navigate("shipment_detail", shipment_id=eid)


@st.cache_data(show_spinner=False, ttl=300)
def _load_shipment(shipment_id: str) -> dict:
    return api_client.get_shipment(shipment_id)


def render_detail(navigate, shipment_id: str) -> None:
    if st.button("← Back to shipments", key="btn_back_shipments"):
        navigate("shipments")

    try:
        with st.spinner("Loading shipment journey…"):
            story = _load_shipment(shipment_id)
    except api_client.NotFoundError:
        ui.empty_state(f"Shipment {shipment_id} Not Found", "Check the identifier or return to the shipment list.")
        return
    except Exception as exc:
        if ui.error_state("Unable to load shipment details.", "The intelligence service could not be reached."):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Technical detail: {exc}")
        return

    risk = story.get("riskProfile", {}) or {}
    level = str(risk.get("risk_level", "LOW")).upper()
    delay_m = story.get("finalDelayMinutes", 0)
    delivery = story.get("deliveryStatus", {}) or {}
    del_status = delivery.get("delivery_status", "On Schedule")
    m = risk.get("metrics", {}) or {}
    deps_n = len(story.get("downstreamDependencies", []) or [])

    # ---- Top: WHAT is this shipment's state ----
    ui.html(
        f"""
        <div style="margin: 12px 0 20px 0;">
            <div class="mono" style="font-size:0.72rem; font-weight:700; letter-spacing:0.08em; color:#64748B;">SHIPMENT {story.get('shipmentId', shipment_id)}</div>
            <div style="display:flex; align-items:center; gap:10px; margin-top:4px; flex-wrap:wrap;">
                <span style="font-size:1.4rem; font-weight:700; color:#0F172A;">{story.get('originLocation', '—')} → {story.get('destinationLocation', '—')}</span>
            </div>
            <div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">
                {ui.risk_badge(level)} {ui.status_badge(story.get("status"))}
            </div>
            <div style="font-size:0.88rem; color:#475569; margin-top:8px;">
                Current delay: <b class="mono">+{ui.fmt_minutes(delay_m)}</b> ·
                Delivery: <b>{del_status}</b> ·
                Priority: <b>{story.get('priority', 'Standard')}</b> ·
                Role: <b>{story.get('delayNature', '—')}</b>
            </div>
        </div>
        """
    )

    ui.kpi_row([
        {"label": "CURRENT DELAY", "value": f"+{ui.fmt_minutes(delay_m)}",
         "context": story.get("delayNature", "Delay condition")},
        {"label": "DELIVERY STATUS", "value": del_status,
         "context": delivery.get("risk_reason", "Customer delivery window")},
        {"label": "DOWNSTREAM DEPENDENCIES", "value": ui.fmt_int(deps_n),
         "context": f"{ui.fmt_int(m.get('downstream_dependencies', deps_n))} waiting legs"},
        {"label": "RISK", "value": f"{level} ({risk.get('risk_score', '—')})",
         "context": "Deterministic drivers below"},
    ])



    # ---- Journey: Origin ↓ Facility ↓ Transfer ↓ … ↓ Destination ----
    ui.section_title("Journey", "Origin → transfer hubs → destination, with planned vs actual timing.")
    ui.metric_grid([
        {"label": "Planned departure", "value": story.get("plannedDeparture", "—")},
        {"label": "Actual departure", "value": story.get("actualDeparture", "—")},
        {"label": "Planned arrival", "value": story.get("plannedArrival", "—")},
        {"label": "Actual arrival", "value": story.get("actualArrival", "—")},
    ])
    _render_journey_story(story, shipment_id)

    # Journey event log (evidence, secondary).
    with st.expander("Journey event log (evidence)"):
        events = story.get("timeline", []) or []
        mapped_events = [{
            "timestamp": ev.get("timestamp", ""),
            "eventType": ev.get("eventType", "Checkpoint"),
            "shipmentId": shipment_id,
            "delayMinutes": ev.get("delayMinutes", 0),
            "locationName": ev.get("locationName", ""),
            "description": ev.get("humanExplanation", ""),
        } for ev in events]
        ui.render_timeline(mapped_events, max_items=15)



    # ---- Current situation ----
    ui.section_title("Current situation", "Where this shipment stands right now.")
    ui.metric_grid([
        {"label": "Current delay", "value": f"+{ui.fmt_minutes(delay_m)}"},
        {"label": "Delay reason", "value": delivery.get("risk_reason", story.get("delayExplanation", "—"))[:80]},
        {"label": "Delivery SLA", "value": del_status,
         "sub": f"SLA met: {'yes' if delivery.get('customer_sla_met') else 'no'} · {ui.fmt_minutes(delivery.get('delay_minutes', 0))} delivery delay"},
        {"label": "Cascade", "value": story.get("cascadeId") or "Isolated",
         "sub": story.get("delayNature", "")},
    ])
    ui.info_card("Delay explanation", story.get("delayExplanation", "No operational delay detected."), accent="blue")



    # ---- Dependency impact: why this shipment matters to the network ----
    ui.section_title("Dependency impact", "Why this shipment matters to the network.")
    _render_dependency_impact(story, navigate, shipment_id)



    # ---- Risk drivers (WHY at risk) ----
    ui.section_title("Why at risk?", "Deterministic drivers behind the risk level.")
    reasons = risk.get("reasons", []) or []
    if reasons:
        ui.html(
            f"""
            <div class="ci-card">
                <div style="font-size:0.75rem; font-weight:700; color:#64748B; text-transform:uppercase; margin-bottom:8px;">
                    {level} risk — drivers
                </div>
                {''.join(f'<div class="ci-risk-bullet">{r}</div>' for r in reasons)}
            </div>
            """
        )
    if risk.get("factors"):
        st.plotly_chart(charts.risk_factor_bars(risk), use_container_width=True)

    ui.glossary_box(["Dependency", "Propagated Delay", "Risk Score"])


def _render_journey_story(story: dict, shipment_id: str) -> None:
    """Vertical journey from origin through event locations to destination."""
    events = story.get("timeline", []) or []
    steps: list[dict] = [{"label": f"Origin — {story.get('originLocation', '—')}",
                          "sub": f"Planned {story.get('plannedDeparture', '—')} → Actual {story.get('actualDeparture', '—')}",
                          "kind": "origin"}]
    seen_locs: list[str] = []
    for ev in events:
        loc = ev.get("locationName", "")
        if loc and loc not in seen_locs:
            seen_locs.append(loc)
            delay = ev.get("delayMinutes", 0)
            try:
                d = int(delay)
            except (TypeError, ValueError):
                d = 0
            steps.append({
                "label": f"{ev.get('eventType', 'Checkpoint')} — {loc}",
                "sub": f"{ev.get('timestamp', '')} · {'on time' if d <= 0 else f'+{ui.fmt_minutes(d)} delay'}",
                "kind": "delay" if d > 30 else "hub",
            })
    steps.append({"label": f"Destination — {story.get('destinationLocation', '—')}",
                  "sub": f"Planned {story.get('plannedArrival', '—')} → Actual {story.get('actualArrival', '—')}",
                  "kind": "destination"})
    ui.journey_steps(steps)


def _render_dependency_impact(story: dict, navigate, shipment_id: str) -> None:
    cid = story.get("cascadeId")
    ups = story.get("upstreamDependencies", []) or []
    downs = story.get("downstreamDependencies", []) or []
    parent = ups[0].get("upstream_shipment_id") if ups else None
    delivery = story.get("deliveryStatus", {}) or {}

    # Propagated delay contributed by this shipment (sum of downstream waits).
    try:
        prop_out = sum(int(d.get("dependency_delay_minutes", 0) or 0) for d in downs)
    except (TypeError, ValueError):
        prop_out = 0

    ui.metric_grid([
        {"label": "Parent shipment", "value": parent or "None (origin)",
         "sub": ups[0].get("dependency_type", "") if ups else "No upstream wait"},
        {"label": "Downstream shipments", "value": ui.fmt_int(len(downs)),
         "sub": f"+{ui.fmt_minutes(prop_out)} transferred delay"},
        {"label": "Cascade membership", "value": cid or "Isolated",
         "sub": story.get("delayNature", "")},
        {"label": "Affected delivery", "value": delivery.get("delivery_id", "—"),
         "sub": f"{delivery.get('delivery_status', '—')} · {ui.fmt_minutes(delivery.get('delay_minutes', 0))}"},
    ])

    if downs:
        with st.expander(f"Downstream dependencies ({len(downs)}) — shipments waiting on {shipment_id}"):
            for d in downs[:10]:
                dsid = d.get("downstream_shipment_id", "")
                ui.html(
                    f"<div style='font-size:0.84rem; color:#334155;'>"
                    f"<b class='mono'>{dsid}</b> at {d.get('transfer_location', '—')} — "
                    f"waited <b>+{ui.fmt_minutes(d.get('dependency_delay_minutes', 0))}</b> "
                    f"({d.get('dependency_status', '')})</div>"
                )
                if st.button("Open downstream shipment →", key=f"shp_down_{shipment_id}_{dsid}", use_container_width=True):
                    navigate("shipment_detail", shipment_id=dsid)
    if cid and st.button(f"Inspect cascade {cid} →", key=f"btn_cas_link_{shipment_id}", use_container_width=True):
        navigate("cascade_detail", cascade_id=cid)
