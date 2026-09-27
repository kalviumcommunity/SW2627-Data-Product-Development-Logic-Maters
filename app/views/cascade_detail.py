"""Cascade Intelligence - Cascade Detail (incident investigation).

Narrative order:
1. Back + header (CASCADE id, title, severity/status)
2. Key metrics
3. ROOT CAUSE (origin disruption, location, initial shipment, initial delay + explanation)
4. HOW THE DELAY SPREAD (propagation tree + timeline + graph, nodes inspectable)
5. DELAY SPLIT (original vs propagated vs customer — visually distinct)
6. DOWNSTREAM IMPACT (blast radius grid + why it matters)
7. CURRENT RISK (drivers, not just score)
8. Technical details (expandable)
"""

from __future__ import annotations

import streamlit as st

from app import api_client
from app.components import propagation as graphs
from app.components import ui


@st.cache_data(show_spinner=False, ttl=300)
def _load(cascade_id: str) -> dict:
    return api_client.get_cascade(cascade_id)


def render(navigate, cascade_id: str) -> None:
    if st.button("← Back to cascades", key="btn_back_cascades"):
        navigate("cascades")

    try:
        with st.spinner("Loading cascade intelligence…"):
            story = _load(cascade_id)
    except api_client.NotFoundError:
        ui.empty_state(f"Cascade {cascade_id} Not Found", "Check the identifier or return to the cascade list.")
        return
    except Exception as exc:
        if ui.error_state("Unable to load cascade details.", "The intelligence service could not be reached."):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Technical detail: {exc}")
        return

    summary = story.get("summary", {})
    rc = story.get("rootCause", {})
    impact = story.get("impact", {})
    expl = story.get("explanation", {})
    sev = str(summary.get("severity", "HIGH")).upper()
    status = str(summary.get("status", "")).upper()
    cid_display = story.get("cascadeId", cascade_id)

    # ---- 2. Header ----
    ui.html(
        f"""
        <div style="margin: 12px 0 20px 0;">
            <div class="mono" style="font-size:0.72rem; font-weight:700; letter-spacing:0.08em; color:#64748B;">CASCADE {cid_display}</div>
            <div style="display:flex; align-items:center; gap:10px; margin-top:4px; flex-wrap:wrap;">
                <span style="font-size:1.4rem; font-weight:700; color:#0F172A; letter-spacing:-0.01em;">
                    {summary.get("title", f"{rc.get('type', 'Disruption')} causing downstream delay propagation")}
                </span>
            </div>
            <div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">
                {ui.severity_badge(sev)} {ui.status_badge(summary.get("status"))}
            </div>
        </div>
        """
    )

    # ---- 3. Key metrics ----
    ui.kpi_row([
        {"label": "AFFECTED SHIPMENTS", "value": ui.fmt_int(impact.get("affectedShipments")),
         "context": "Shipments in delay chain"},
        {"label": "FACILITIES AFFECTED", "value": ui.fmt_int(impact.get("affectedLocations")),
         "context": "Facilities touched by delay"},
        {"label": "PROPAGATED DELAY", "value": f"{float(summary.get('propagatedDelayHours', 0.0)):.1f}h",
         "context": "Generated downstream"},
        {"label": "SLA BREACHES", "value": ui.fmt_int(impact.get("deliveriesAtRisk")),
         "context": f"Of {ui.fmt_int(impact.get('affectedDeliveries'))} customer deliveries"},
    ])



    # ---- 4. ROOT CAUSE ----
    ui.section_title("Root cause", "Origin incident that started the chain.")
    initial_ship = rc.get("initialShipmentId", "")
    ui.metric_grid([
        {"label": "Origin disruption", "value": rc.get("type", "—"), "sub": rc.get("timestamp", "")},
        {"label": "Location", "value": rc.get("locationName", "—"), "sub": rc.get("locationId", "")},
        {"label": "Initial shipment", "value": initial_ship or "—", "sub": "Root of chain"},
        {"label": "Initial delay", "value": rc.get("initialDelayFormatted", ui.fmt_minutes(rc.get("initialDelayMinutes", 0))),
         "sub": f"{ui.fmt_int(rc.get('initialDelayMinutes', 0))} min original delay"},
    ])
    ui.info_card(
        "What happened",
        expl.get("whatHappened", "The initial operational disruption caused immediate departure delay."),
        accent="red",
    )
    if initial_ship and st.button("Inspect root shipment →", key=f"cd_root_ship_{initial_ship}", use_container_width=True):
        navigate("shipment_detail", shipment_id=initial_ship)



    # ---- 5. HOW THE DELAY SPREAD ----
    ui.section_title("How the delay spread", "Propagation chain, timeline, and dependency graph.")
    ui.propagation_tree(story.get("propagation", []) or [])

    col_tl, col_graph = st.columns([1.2, 1.8], vertical_alignment="top")
    with col_tl:
        ui.html('<div style="font-size:0.82rem; font-weight:700; color:#1E293B; text-transform:uppercase; margin-bottom:8px;">Propagation timeline</div>')
        ui.render_timeline(story.get("timeline", []), max_items=25)
    with col_graph:
        ui.html('<div style="font-size:0.82rem; font-weight:700; color:#1E293B; text-transform:uppercase; margin-bottom:8px;">Propagation graph</div>')
        st.plotly_chart(graphs.cascade_graph(story), use_container_width=True)

        prop = story.get("propagation", []) or []
        if prop:
            node_ids = [n.get("shipmentId") for n in prop]
            selected_node = st.selectbox("Inspect specific node in delay chain", node_ids, key=f"sel_node_{cascade_id}")
            node_detail = next((n for n in prop if n.get("shipmentId") == selected_node), None)
            if node_detail:
                ui.html(
                    f"""
                    <div class="ci-card" style="margin-top:10px;">
                        <div class="ci-card-title">Node {selected_node} (Level {node_detail.get('depth')})</div>
                        <div class="ci-card-body">
                            Route: <b class="mono">{node_detail.get('originLocation')}</b> → <b class="mono">{node_detail.get('destinationLocation')}</b><br>
                            Total delay: <b>{ui.fmt_minutes(node_detail.get('totalDelayMinutes'))}</b> ·
                            Propagated: <b>{ui.fmt_minutes(node_detail.get('propagatedDelayMinutes'))}</b><br>
                            Parent dependency: <b class="mono">{node_detail.get('parentShipmentId') or 'Root origin'}</b> ·
                            Type: {node_detail.get('dependencyType', 'Direct transfer')}
                        </div>
                    </div>
                    """
                )
                b1, b2 = st.columns(2, vertical_alignment="bottom")
                with b1:
                    if st.button("Open node shipment →", key=f"btn_node_open_{selected_node}", use_container_width=True):
                        navigate("shipment_detail", shipment_id=selected_node)
                with b2:
                    parent_sid = node_detail.get("parentShipmentId")
                    if parent_sid and st.button("Open parent shipment →", key=f"btn_parent_open_{selected_node}", use_container_width=True):
                        navigate("shipment_detail", shipment_id=parent_sid)



    # ---- 6. DELAY SPLIT (original vs propagated vs customer) ----
    ui.section_title(
        "Original vs propagated delay",
        "The initial disruption is small — dependencies multiply it downstream.",
    )
    ui.delay_split_visual(
        initial_minutes=impact.get("initialDelayMinutes", rc.get("initialDelayMinutes", 0)),
        propagated_minutes=impact.get("propagatedDelayMinutes", 0),
        deliveries_at_risk=impact.get("deliveriesAtRisk", 0),
    )



    # ---- 7. DOWNSTREAM IMPACT ----
    ui.section_title("Downstream impact", "Blast radius and affected customer deliveries.")
    ui.metric_grid([
        {"label": "Blast radius", "value": f"{ui.fmt_int(impact.get('affectedShipments'))} shipments",
         "sub": f"{ui.fmt_int(impact.get('affectedLocations'))} facilities · depth {impact.get('cascadeDepth', '—')}"},
        {"label": "Propagated delay", "value": f"{float(summary.get('propagatedDelayHours', 0.0)):.1f}h",
         "sub": f"{float(summary.get('totalDelayHours', 0.0)):.1f}h cumulative total"},
        {"label": "Highest-impact shipment",
         "value": str(impact.get("highestImpactShipmentId", "—")),
         "sub": f"+{ui.fmt_minutes(impact.get('highestImpactDelayMinutes', 0))}"},
        {"label": "Most affected facility", "value": str(impact.get("mostAffectedLocationName", "—")),
         "sub": f"{ui.fmt_int(impact.get('downstreamDependenciesCount', 0))} downstream dependencies"},
    ])
    ui.info_card(
        "Why this matters",
        expl.get(
            "whyItMatters",
            "This disruption propagated through dependent cross-dock transfers and departure schedules.",
        ),
        accent="amber",
    )
    max_ship = impact.get("highestImpactShipmentId", "")
    if max_ship and st.button(f"Inspect highest-impact shipment {max_ship} →", key=f"cd_max_{cid_display}", use_container_width=True):
        navigate("shipment_detail", shipment_id=max_ship)



    # ---- 8. CURRENT RISK ----
    ui.section_title("Current risk", "Why this chain remains risky — drivers, not just a score.")
    ui.info_card(
        "Current risk assessment",
        expl.get("currentRisk", "Risk levels reflect remaining delivery buffer margins and downstream transfers."),
        accent="red" if status == "ACTIVE" else "gray",
    )
    cascade_risks = story.get("risks", []) or []
    if cascade_risks:
        for r in cascade_risks[:4]:
            sid = r.get("shipment_id", "")
            reasons = r.get("reasons", []) or []
            m = r.get("metrics", {}) or {}
            ui.risk_item(
                shipment_id=sid,
                risk_level=r.get("risk_level", "HIGH"),
                delay_minutes=m.get("current_delay_minutes", 0),
                dependencies=m.get("downstream_dependencies", 0),
                reasons=reasons,
                navigate=navigate,
                key_prefix=f"cas_risk_{cascade_id}",
            )
    else:
        ui.empty_state("No downstream risks", "No active shipments in this chain currently exceed risk thresholds.")

    rec_action = expl.get("recommendedAction")
    if rec_action:

        ui.section_title("Recommended action", "Data-backed operational recovery options.")
        ui.info_card("Recommended action", rec_action, accent="blue")



    with st.expander("Technical details"):
        st.json({
            "cascadeId": story.get("cascadeId"),
            "impactScore": impact.get("score"),
            "initialDelayMinutes": impact.get("initialDelayMinutes"),
            "propagatedDelayMinutes": impact.get("propagatedDelayMinutes"),
            "totalDelayMinutes": impact.get("totalDelayMinutes"),
            "durationMinutes": impact.get("durationMinutes"),
            "cascadeDepth": impact.get("cascadeDepth"),
            "confidenceScore": rc.get("confidenceScore"),
            "attributionUncertainty": rc.get("attributionUncertainty"),
        })

    ui.glossary_box(["Root Delay", "Propagated Delay", "Cascade", "Risk Score", "Blast Radius"])
