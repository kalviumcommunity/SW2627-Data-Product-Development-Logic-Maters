"""Cascade Intelligence - About / system architecture page."""

from __future__ import annotations

import streamlit as st

from app import api_client
from app.components import ui


def render(navigate) -> None:
    ui.page_header(
        "About Cascade Intelligence",
        "Deterministic delay propagation and cascading impact analysis for supply chain operations.",
    )

    ui.hero_section(
        lead="Operational Objective",
        headline="Transforming logistics telemetries into transparent explanations of delay, propagation, impact, and risk.",
        detail=(
            "Cascade Intelligence answers six core questions: what is happening → where did it start → "
            "why did it happen → how did it spread → what is affected → which shipments require immediate operational intervention."
        ),
    )

    ui.section_title("Operational Investigation Flow", "Standard sequence for diagnosing network delay incidents.")
    ui.story_step(1, "What is happening?", "Dashboard headlines and the active cascade centerpiece synthesize live network disruptions.")
    ui.story_step(2, "Where did it start?", "Root cause attribution identifies the origin facility, timestamp, and initial delayed shipment.")
    ui.story_step(3, "Why did it happen?", "Disruption logs pair with operational conditions to explain the initial setback.")
    ui.story_step(4, "How did it spread?", "Chronological timelines and directed acyclic graphs trace waiting dependencies.")
    ui.story_step(5, "What is affected?", "Blast radius counts downstream shipments, touched facilities, and delivery SLA breaches.")
    ui.story_step(6, "What requires attention?", "The Risk Monitor surfaces compromised buffers and critical transfer risks.")

    ui.glossary_box()

    try:
        reachable = api_client.is_api_reachable()
        st.caption(
            f"Intelligence Engine: {'Connected to live FastAPI service at ' + api_client.API_BASE_URL if reachable else 'In-process intelligence engine active (identical real dataset)'}"
        )
    except Exception:
        pass
