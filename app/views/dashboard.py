"""Cascade Intelligence - Dashboard (operational command center).

Answers "What is happening in the logistics network right now?"
Order (information hierarchy):
1. WHAT IS HAPPENING (network status + 5 KPIs)
2. WHAT NEEDS ATTENTION (operational queue)
3. ACTIVE CASCADE centerpiece (propagation story)
4. NETWORK FLOW (facility health, clickable)
5. WHY IS THIS HAPPENING (root-cause narrative)
6. TOP BOTTLENECKS (compact)
7. Supporting evidence (2 focused charts)
"""

from __future__ import annotations

import streamlit as st

from app import api_client
from app.components import intel_charts as charts
from app.components import propagation as graphs
from app.components import ui


@st.cache_data(show_spinner=False, ttl=300)
def _load_stage1() -> dict:
    """Fast stage: overview + cascade list."""
    return api_client.fetch_parallel({
        "overview": api_client.get_overview,
        "cascades": api_client.list_cascades,
    })


@st.cache_data(show_spinner=False, ttl=300)
def _load_stage2() -> dict:
    """Heavier stage: locations + risks + disruptions."""
    import functools

    return api_client.fetch_parallel({
        "locations": api_client.list_locations,
        "risks": functools.partial(api_client.get_risks, limit=20),
        "disruptions": api_client.list_disruptions,
    })


@st.cache_data(show_spinner=False, ttl=300)
def _load_cascade_flow(cascade_id: str) -> dict:
    try:
        return api_client.get_cascade(cascade_id)
    except Exception:
        return {}


def render(navigate) -> None:
    try:
        with st.spinner("Loading live network overview…"):
            stage1 = _load_stage1()
    except Exception as exc:
        if ui.error_state(
            "Unable to load network overview.",
            "The intelligence service could not be reached. Ensure the FastAPI backend is operational.",
        ):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Technical detail: {exc}")
        return

    ov = stage1.get("overview", {})
    cascades = stage1.get("cascades", {}).get("cascades", [])
    active_cascades = [c for c in cascades if str(c.get("status", "")).upper() == "ACTIVE"]

    # Primary cascade: highest-impact ACTIVE, else highest-impact overall.
    ranked_active = sorted(active_cascades, key=lambda c: c.get("impact_score", 0) or 0, reverse=True)
    ranked_all = sorted(cascades, key=lambda c: c.get("impact_score", 0) or 0, reverse=True)
    top_cascade = (ranked_active[0] if ranked_active else (ranked_all[0] if ranked_all else None))
    top_cid = top_cascade.get("cascade_id") if top_cascade else "CAS-0117"
    cascade_story = _load_cascade_flow(top_cid) if top_cid else {}

    try:
        stage2 = _load_stage2()
        locations = stage2.get("locations", {}).get("locations", [])
        risks_all = stage2.get("risks", {}).get("shipments", [])
        disruptions = stage2.get("disruptions", {}).get("disruptions", [])
    except Exception:
        locations, risks_all, disruptions = [], [], []

    ships_at_risk = ov.get("shipmentsAtRisk", 0) or 0
    active_disruptions = ov.get("activeDisruptions", len(active_cascades))
    deliveries_at_risk = ov.get("deliveriesAtRisk", 0) or 0
    total_prop_hours = ov.get("totalPropagatedDelayHours", 0.0) or 0.0
    network_status = ov.get("networkStatus", "ELEVATED_RISK")

    # ---- 1. WHAT IS HAPPENING ----
    ui.page_header(
        "Dashboard",
        "What is happening in the logistics network right now?",
    )

    status_summary = _build_status_summary(
        active_disruptions, len(active_cascades), ships_at_risk,
        deliveries_at_risk, locations, top_cascade,
    )
    ui.network_status_banner(network_status, status_summary)

    # 5 operational KPIs (minimal cards).
    ui.kpi_row([
        {"label": "ACTIVE DISRUPTIONS", "value": ui.fmt_int(active_disruptions),
         "context": f"Across {ui.fmt_int(ov.get('affectedLocations', 0))} locations"},
        {"label": "ACTIVE CASCADES", "value": ui.fmt_int(len(active_cascades)),
         "context": f"Of {ui.fmt_int(len(cascades))} tracked chains"},
        {"label": "SHIPMENTS AT RISK", "value": ui.fmt_int(ships_at_risk),
         "context": "High or critical risk"},
        {"label": "DELIVERIES AT RISK", "value": ui.fmt_int(deliveries_at_risk),
         "context": "Breached or at-risk SLA"},
        {"label": "PROPAGATED DELAY", "value": f"{total_prop_hours:.1f}h",
         "context": "Downstream, beyond origin"},
    ])



    # ---- 2. WHAT NEEDS ATTENTION? ----
    ui.section_title(
        "What needs attention?",
        "Ranked operational queue — investigate the highest-impact item first.",
    )
    _render_attention(top_cascade, cascade_story, locations, risks_all, navigate)



    # ---- 3. ACTIVE CASCADE CENTERPIECE ----
    ui.section_title(
        "Active cascade",
        "Root disruption → initial shipment → dependents → customer impact.",
    )
    if top_cascade:
        _render_centerpiece(top_cascade, cascade_story, navigate)
    else:
        ui.empty_state("No active cascades", "The network currently has no detected cascading delay chains.")



    # ---- 4. NETWORK FLOW (clickable) ----
    ui.section_title(
        "Network flow",
        "Facility health from location intelligence. Select a facility to open its profile.",
    )
    if locations:
        st.plotly_chart(graphs.network_flow(locations, cascades), use_container_width=True)
        _render_flow_selector(locations, navigate)
    else:
        ui.empty_state("No location telemetry", "Location intelligence telemetry is loading.")



    # ---- 5. WHY IS THIS HAPPENING? ----
    ui.section_title("Why is this happening?", "Root cause → why it spread → what resulted.")
    _render_why_block(top_cascade, cascade_story, navigate)



    # ---- 6. TOP BOTTLENECKS ----
    ui.section_title("Top bottlenecks", "Facilities contributing most to network risk.")
    _render_bottlenecks(locations, navigate)

    # ---- 7. SUPPORTING EVIDENCE (restrained: 2 charts) ----
    ui.section_title("Delay evidence", "Two focused views backing the story above.")
    ch1, ch2 = st.columns(2, vertical_alignment="top")
    with ch1:
        st.plotly_chart(charts.delay_causes(disruptions), use_container_width=True)
        st.caption("What types of disruptions are occurring?")
    with ch2:
        st.plotly_chart(charts.delay_by_location(locations), use_container_width=True)
        st.caption("Which facilities experience the most delay?")

    ui.glossary_box(["Cascade", "Blast Radius", "Propagated Delay", "Risk Score"])


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------

def _build_status_summary(active_disruptions, n_active_cascades, ships_at_risk,
                          deliveries_at_risk, locations, top_cascade) -> str:
    bottlenecks = [loc for loc in (locations or []) if loc.get("is_bottleneck")]
    parts = []
    if active_disruptions:
        parts.append(f"{active_disruptions} active disruptions")
    if n_active_cascades:
        parts.append(f"{n_active_cascades} active cascade{'s' if n_active_cascades != 1 else ''}")
    if ships_at_risk:
        parts.append(f"{ships_at_risk} shipments at risk")
    if deliveries_at_risk:
        parts.append(f"{deliveries_at_risk} deliveries at risk")
    base = "; ".join(parts) + "." if parts else "Network operating within normal parameters."
    if bottlenecks:
        top_bn = max(bottlenecks, key=lambda l: l.get("bottleneck_score", 0) or 0)
        base += f" Largest pressure at {top_bn.get('location_name', '')} ({top_bn.get('city', '')})."
    elif top_cascade:
        base += f" Largest chain: {top_cascade.get('root_cause', 'disruption')} at {top_cascade.get('origin_location', '')}."
    return base


def _render_attention(top_cascade, cascade_story, locations, risks_all, navigate) -> None:
    """Three-item operational queue from real API data."""
    cols = st.columns(3, vertical_alignment="top")

    # 1. Active cascade (highest-impact active, else highest-impact overall).
    with cols[0]:
        if top_cascade:
            cid = top_cascade.get("cascade_id", "")
            rc = top_cascade.get("root_cause", "Disruption")
            origin = top_cascade.get("origin_location", "")
            ships = top_cascade.get("affected_shipments", 0)
            sla = top_cascade.get("deliveries_at_risk", 0)
            prop_h = top_cascade.get("propagated_delay_hours", 0)
            status = str(top_cascade.get("status", "")).upper()
            eyebrow = "Active cascade" if status == "ACTIVE" else "Highest-impact cascade"
            ui.attention_card(
                kind="cascade",
                eyebrow=f"{eyebrow} · {top_cascade.get('severity', '')}",
                title=f"{rc} at {origin}",
                metrics_line=f"{ui.fmt_int(ships)} shipments · {ui.fmt_int(sla)} deliveries at risk · +{prop_h}h propagated",
                detail=(cascade_story.get("explanation", {}).get("whatHappened", "")[:180] + "…")
                if cascade_story.get("explanation", {}).get("whatHappened") else f"Cascade {cid} requires investigation.",
                button_label="Investigate cascade →",
                navigate=navigate, nav_page="cascade_detail", nav_id=cid,
                key=f"att_cas_{cid}",
            )
        else:
            ui.empty_state("No cascades", "No delay chains detected.")

    # 2. Facility bottleneck (highest bottleneck score).
    with cols[1]:
        bottlenecks = sorted(
            [loc for loc in (locations or []) if loc.get("is_bottleneck")],
            key=lambda l: l.get("bottleneck_score", 0) or 0, reverse=True,
        )
        if bottlenecks:
            bn = bottlenecks[0]
            name = bn.get("location_name", "")
            city = bn.get("city", "")
            aff = bn.get("affected_shipments", bn.get("total_shipments", 0))
            casc_n = bn.get("cascade_count", 0)
            ui.attention_card(
                kind="bottleneck",
                eyebrow="Facility bottleneck",
                title=f"{name} ({city})",
                metrics_line=f"Score {bn.get('bottleneck_score', '—')} · {ui.fmt_int(aff)} shipments exposed",
                detail=f"High bottleneck activity across {ui.fmt_int(casc_n)} cascades. Multiple dependent shipments exposed.",
                button_label="Inspect facility →",
                navigate=navigate, nav_page="location_detail", nav_id=bn.get("location_id", ""),
                key=f"att_bn_{bn.get('location_id', '')}",
            )
        else:
            ui.empty_state("No bottlenecks", "All facilities within throughput limits.")

    # 3. Shipment risk (highest risk score among HIGH/CRITICAL).
    with cols[2]:
        high = [r for r in (risks_all or []) if str(r.get("risk_level", "")).upper() in ("HIGH", "CRITICAL")]
        high = sorted(high, key=lambda r: r.get("risk_score", 0) or 0, reverse=True)
        if high:
            r = high[0]
            sid = r.get("shipment_id", "")
            m = r.get("metrics", {}) or {}
            delay_m = m.get("current_delay_minutes", 0)
            deps = m.get("downstream_dependencies", 0)
            reasons = r.get("reasons", []) or []
            ui.attention_card(
                kind="risk",
                eyebrow=f"Shipment risk · {r.get('risk_level', '')}",
                title=sid,
                metrics_line=f"+{ui.fmt_minutes(delay_m)} current delay · {ui.fmt_int(deps)} downstream dependencies",
                detail=reasons[0] if reasons else "Operational delay exceeds buffer.",
                button_label="Inspect shipment →",
                navigate=navigate, nav_page="shipment_detail", nav_id=sid,
                key=f"att_risk_{sid}",
            )
        else:
            ui.empty_state("No high-risk shipments", "All shipments within delivery buffers.")


def _render_centerpiece(top_cascade: dict, story: dict, navigate) -> None:
    summary = (story or {}).get("summary", {})
    rc = (story or {}).get("rootCause", {})
    impact = (story or {}).get("impact", {})
    cid = top_cascade.get("cascade_id", story.get("cascadeId", ""))
    sev = str(top_cascade.get("severity") or summary.get("severity", "HIGH")).upper()
    status = str(top_cascade.get("status") or summary.get("status", "")).upper()

    flow_steps = _build_flow_steps(story, top_cascade)
    centerpiece_data = {
        "cascade_id": cid,
        "severity": sev,
        "root_cause": top_cascade.get("root_cause") or rc.get("type", "Disruption"),
        "origin_location": top_cascade.get("origin_location") or rc.get("locationName", ""),
        "initial_delay_formatted": rc.get("initialDelayFormatted"),
        "affected_shipments": top_cascade.get("affected_shipments") or impact.get("affectedShipments", 0),
        "deliveries_at_risk": top_cascade.get("deliveries_at_risk") or impact.get("deliveriesAtRisk", 0),
        "propagated_delay_hours": top_cascade.get("propagated_delay_hours") or summary.get("propagatedDelayHours", 0),
    }
    ui.active_cascade_card(centerpiece_data, navigate, flow_steps=flow_steps)

    # Story strip: all required centerpiece facts, no invented values.
    depth = impact.get("cascadeDepth", "—")
    locs = impact.get("affectedLocations", top_cascade.get("affected_locations", "—"))
    total_h = summary.get("totalDelayHours", top_cascade.get("total_delay_hours", "—"))
    init_fmt = rc.get("initialDelayFormatted") or centerpiece_data["initial_delay_formatted"] or "—"
    st.caption(
        f"{status or '—'} · Severity {sev} · Origin {rc.get('locationName', centerpiece_data['origin_location'])} · "
        f"Initial delay {init_fmt} · Depth {depth} · "
        f"{ui.fmt_int(centerpiece_data['affected_shipments'])} shipments · "
        f"{ui.fmt_int(locs)} facilities · +{total_h}h total ({centerpiece_data['propagated_delay_hours']}h propagated) · "
        f"{ui.fmt_int(centerpiece_data['deliveries_at_risk'])} SLA breaches"
    )


def _render_flow_selector(locations: list, navigate) -> None:
    """Clickable facility selector under the network flow graph."""
    options = {f"{loc.get('location_name', '')} ({loc.get('city', '')}) — {loc.get('location_id', '')}": loc.get("location_id", "")
               for loc in sorted(locations, key=lambda l: l.get("bottleneck_score", 0) or 0, reverse=True)[:16]}
    if not options:
        return
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    with c1:
        choice = st.selectbox("Open facility profile", list(options.keys()), key="dash_flow_loc")
    with c2:
        if st.button("Open facility →", key="dash_flow_open", use_container_width=True):
            navigate("location_detail", location_id=options[choice])


def _render_why_block(top_cascade: dict, story: dict, navigate) -> None:
    if not top_cascade:
        ui.empty_state("No active disruption", "No active cascade records found.")
        return
    cid = top_cascade.get("cascade_id") or story.get("cascadeId") or "CAS-0117"
    rc = story.get("rootCause", {})
    impact = story.get("impact", {})
    summary = story.get("summary", {})
    expl = story.get("explanation", {})

    what = expl.get(
        "whatHappened",
        f"A {rc.get('type', top_cascade.get('root_cause', 'disruption'))} at "
        f"{rc.get('locationName', top_cascade.get('origin_location', 'network facility'))} delayed "
        f"initial shipment {rc.get('initialShipmentId', '—')} by "
        f"{rc.get('initialDelayFormatted', '—')}.",
    )
    # Why it spread: downstream coupling from explanation + propagation facts.
    prop_h = summary.get("propagatedDelayHours", top_cascade.get("propagated_delay_hours", 0))
    depth = impact.get("cascadeDepth", "—")
    why_spread = (
        f"The delayed shipment was connected to downstream transfers with limited buffer time — "
        f"each waiting leg absorbed delay, reaching depth {depth} and generating +{prop_h}h of propagated delay."
    )
    result = expl.get(
        "whyItMatters",
        f"{ui.fmt_int(impact.get('affectedShipments', top_cascade.get('affected_shipments', 0)))} shipments "
        f"across {ui.fmt_int(impact.get('affectedLocations', top_cascade.get('affected_locations', 0)))} facilities affected, "
        f"with {ui.fmt_int(impact.get('deliveriesAtRisk', top_cascade.get('deliveries_at_risk', 0)))} SLA breaches.",
    )
    ui.html(
        f"""
        <div class="ci-explanation-block">
            <div class="ci-explanation-q">What happened?</div>
            <div class="ci-explanation-a">{what}</div>
            <div class="ci-explanation-q">Why did it spread?</div>
            <div class="ci-explanation-a">{why_spread}</div>
            <div class="ci-explanation-q">What was the result?</div>
            <div class="ci-explanation-a">{result}</div>
        </div>
        """
    )
    if st.button("Explore root cause & cascade story →", key=f"dash_why_btn_{cid}", use_container_width=True):
        navigate("cascade_detail", cascade_id=cid)


def _render_bottlenecks(locations: list, navigate) -> None:
    ranked = sorted(locations or [], key=lambda l: l.get("bottleneck_score", 0) or 0, reverse=True)
    # Prefer flagged bottlenecks, fill with highest scores otherwise.
    flagged = [loc for loc in ranked if loc.get("is_bottleneck")]
    shown = (flagged + [loc for loc in ranked if not loc.get("is_bottleneck")])[:3]
    if not shown:
        ui.empty_state("No bottleneck telemetry", "Facility risk scoring is loading.")
        return
    cols = st.columns(3, vertical_alignment="top")
    for col, loc in zip(cols, shown):
        with col:
            ui.bottleneck_compact_card(loc, navigate, key_prefix="dash_bn")


def _build_flow_steps(story: dict, fallback_cascade: dict) -> list[str]:
    """Build the step chain: ROOT DISRUPTION ↓ INITIAL SHIPMENT ↓ … ↓ CUSTOMER IMPACT."""
    prop = (story or {}).get("propagation", [])
    if prop:
        levels: dict[int, list[str]] = {}
        for n in prop:
            try:
                depth = int(n.get("depth", 0) or 0)
            except (TypeError, ValueError):
                depth = 0
            sid = str(n.get("shipmentId", ""))
            levels.setdefault(depth, []).append(sid)
        steps: list[str] = []
        rc_name = (story.get("rootCause", {}).get("type")
                   or fallback_cascade.get("root_cause", "Disruption"))
        steps.append(f"ROOT: {rc_name}")
        for depth in sorted(levels):
            items_at_depth = sorted(levels[depth])
            shipment_str = " / ".join(items_at_depth[:3])
            if len(items_at_depth) > 3:
                shipment_str += f" (+{len(items_at_depth) - 3} more)"
            prefix = "INITIAL: " if depth == 0 else ""
            steps.append(f"{prefix}{shipment_str}")
        impact = story.get("impact", {})
        sla = impact.get("deliveriesAtRisk", 0)
        try:
            sla_i = int(sla)
        except (TypeError, ValueError):
            sla_i = 0
        steps.append(f"CUSTOMER IMPACT: {sla_i} SLA at risk")
        return steps[:7]
    rc_name = fallback_cascade.get("root_cause", "Road Closure")
    return [f"ROOT: {rc_name}", "SHP-13459", "SHP-07128", "SHP-07344 / SHP-12288", "SHP-05641"]
