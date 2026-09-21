"""Alerts & risk page: threshold breaches and cascade activity (read-only).

All alert logic lives in analysis/alerts.py with thresholds from
config/alert_config.py (configurable demonstration parameters, not
production-learned values). This page renders, filters, and explains.
Language is factual: what happened, which metric, which threshold.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from analysis.alerts import generate_alerts, summarize_alerts
from config.alert_config import DEFAULT_ALERT_CONFIG


def _summary_cards(summary: dict[str, Any]) -> None:
    total = summary["total_alerts"]
    by_sev = summary["by_severity"]
    cols = st.columns(4)
    cols[0].metric("Total alerts", f"{total}")
    for col, level in zip(cols[1:], ("CRITICAL", "WARNING", "INFO")):
        col.metric(f"{level.title()} alerts", f"{by_sev.get(level, 0)}")


def render(filtered: pd.DataFrame, full: pd.DataFrame) -> None:
    st.header("Alerts & risk")
    st.caption(
        "Thresholds are configurable demonstration parameters "
        f"(delay rate {DEFAULT_ALERT_CONFIG['delay_rate_threshold']:.0f}%, "
        f"duration {DEFAULT_ALERT_CONFIG['delay_duration_threshold']:.0f}); "
        "alerts report observed breaches, not predictions."
    )
    if filtered.empty:
        st.info("No records match the selected filters.")
        return
    alerts, report = generate_alerts(filtered)
    if alerts.empty:
        st.success(
            "No alerts in the current selection. "
            f"Unavailable checks: {', '.join(report['unavailable']) or 'none'}."
        )
        return
    summary = summarize_alerts(alerts)
    _summary_cards(summary)
    st.caption(
        f"Affected routes: {', '.join(summary['affected_routes']) or 'none'} | "
        f"Affected warehouses: {', '.join(summary['affected_warehouses']) or 'none'} | "
        f"Cascade alerts: {summary['cascade_alerts']}"
    )
    view = _apply_table_filters(alerts)
    if view.empty:
        st.info("No alerts match the selected severity/type filters.")
        return
    st.subheader("Alert table")
    st.dataframe(
        view[
            ["alert_id", "alert_type", "severity", "entity_type", "entity_id",
             "metric", "metric_value", "threshold", "detected_at", "message"]
        ],
        width="stretch",
    )
    _render_evidence(view)


def _apply_table_filters(alerts: pd.DataFrame) -> pd.DataFrame:
    """Severity/type/entity filters that always affect the table below."""
    col_a, col_b = st.columns(2)
    severities = sorted(alerts["severity"].unique().tolist())
    types = sorted(alerts["alert_type"].unique().tolist())
    pick_sev = col_a.multiselect("Severity", severities, default=severities)
    pick_type = col_b.multiselect("Alert type", types, default=types)
    entities = sorted(alerts["entity_id"].astype(str).unique().tolist())
    pick_entity = st.multiselect("Entity (route/warehouse/shipment)", entities)
    view = alerts[
        alerts["severity"].isin(pick_sev) & alerts["alert_type"].isin(pick_type)
    ]
    if pick_entity:
        view = view[view["entity_id"].astype(str).isin(pick_entity)]
    return view.reset_index(drop=True)


def _render_evidence(view: pd.DataFrame) -> None:
    st.subheader("Alert evidence")
    choice = st.selectbox(
        "Alert",
        view["alert_id"].tolist(),
        format_func=lambda aid: _alert_label(view, aid),
    )
    row = view[view["alert_id"] == choice].iloc[0]
    st.write(f"**{row['severity']}** - {row['message']}")
    st.write(
        f"Metric `{row['metric']}` observed at {row['metric_value']} "
        f"against the configured threshold {row['threshold']} "
        f"(detected {row['detected_at']})."
    )
    try:
        st.json(json.loads(row["evidence"]))
    except (TypeError, ValueError):
        st.info("No structured evidence available for this alert.")


def _alert_label(view: pd.DataFrame, alert_id: str) -> str:
    row = view[view["alert_id"] == alert_id].iloc[0]
    return f"{alert_id} [{row['severity']}] {row['alert_type']} - {row['entity_id']}"
