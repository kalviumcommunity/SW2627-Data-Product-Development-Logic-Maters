"""Cascade Intelligence - Data Explorer view.

Professional data inspection interface:
[Shipments] [Events] [Dependencies] [Cascades] [Disruptions] [Deliveries] [Locations]
Every record defaults to the plain-language operational explanation, with raw JSON secondary.
"""

from __future__ import annotations

import streamlit as st

from app import api_client
from app.components import ui

PAGE_SIZE = 25


def render(navigate) -> None:
    ui.page_header(
        "Data Explorer",
        "Explore underlying logistics records and understand what each entry represents in plain language.",
    )

    entities = api_client.EXPLORER_ENTITIES
    labels = ["Shipments", "Events", "Dependencies", "Cascades", "Disruptions", "Deliveries", "Locations"]
    tabs = st.tabs(labels)

    for tab, entity in zip(tabs, entities):
        with tab:
            _render_entity_explorer(entity, navigate)


def _render_entity_explorer(entity: str, navigate) -> None:
    st.session_state.setdefault(f"exp_offset_{entity}", 0)

    c1, c2 = st.columns([3.5, 1], vertical_alignment="bottom")
    with c1:
        q = st.text_input(
            "Search",
            placeholder=f"Search {entity} records by ID or attributes…",
            key=f"exp_q_{entity}",
            label_visibility="collapsed",
        )
    with c2:
        if st.button("Clear Search", key=f"exp_clear_{entity}", use_container_width=True):
            st.session_state[f"exp_offset_{entity}"] = 0
            st.session_state[f"exp_q_{entity}"] = ""
            st.rerun()

    offset = st.session_state[f"exp_offset_{entity}"]
    try:
        with st.spinner(f"Loading {entity}…"):
            payload = api_client.explore(entity, limit=PAGE_SIZE, offset=offset, search=q or None)
    except Exception as exc:
        if ui.error_state(f"Unable to load {entity}.", "The intelligence service could not be reached."):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Technical detail: {exc}")
        return

    total = payload.get("total_records", 0)
    records = payload.get("records", [])

    st.caption(f"{total:,} records logged · showing {offset + 1}–{offset + len(records)}")

    if not records:
        ui.empty_state(f"No {entity} records found", "Try widening or clearing your search filter.")
        return

    for idx, rec in enumerate(records):
        eid = rec.get("entityId", "")
        ts = rec.get("timestamp") or ""

        ui.html(
            f"""
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; padding:14px 18px; margin-bottom:12px; box-shadow:0 1px 2px rgba(0,0,0,0.02);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div>
                        <span class="mono" style="font-weight:700; font-size:0.95rem; color:#0F172A;">{eid}</span>
                        <span style="margin-left:8px;">{ui.status_badge(rec.get("status"))}</span>
                    </div>
                    {f'<span class="mono" style="font-size:0.75rem; color:#64748B;">{ts}</span>' if ts else ''}
                </div>
            </div>
            """
        )

        t_explain, t_raw = st.tabs(["Human Explanation", "Raw Data"])
        with t_explain:
            ui.html(
                f"""
                <div style="padding: 10px 14px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; font-size:0.86rem; color:#334155; line-height:1.6;">
                    {rec.get("humanExplanation", "Record verified by intelligence engine.")}
                </div>
                """
            )
            _render_deep_link(entity, rec, navigate, suffix=f"{offset}_{idx}")

        with t_raw:
            st.json(rec.get("raw", {}))

    # Pagination controls

    p1, p2, p3 = st.columns([1, 1, 3])
    with p1:
        if st.button("← Previous", key=f"exp_prev_{entity}", disabled=offset <= 0):
            st.session_state[f"exp_offset_{entity}"] = max(0, offset - PAGE_SIZE)
            st.rerun()
    with p2:
        if st.button("Next →", key=f"exp_next_{entity}", disabled=offset + PAGE_SIZE >= total):
            st.session_state[f"exp_offset_{entity}"] = offset + PAGE_SIZE
            st.rerun()


def _render_deep_link(entity: str, rec: dict, navigate, suffix: str = "") -> None:
    eid = rec.get("entityId", "")
    raw = rec.get("raw", {}) or {}
    if entity == "shipments":
        if st.button("Open shipment journey story →", key=f"exp_lnk_shp_{eid}_{suffix}"):
            navigate("shipment_detail", shipment_id=eid)
    elif entity == "cascades":
        cid = str(raw.get("cascade_id", "") or "").strip() or eid
        if st.button("Open cascade investigation story →", key=f"exp_lnk_cas_{eid}_{suffix}"):
            navigate("cascade_detail", cascade_id=cid)
    elif entity == "locations":
        if st.button("Open facility operations profile →", key=f"exp_lnk_loc_{eid}_{suffix}"):
            navigate("location_detail", location_id=eid)
