"""KPI display preparation (pure functions; pages call st.metric).

Values that cannot be computed are rendered as "n/a" so pages never show
misleading zeros. No Streamlit dependency here - fully unit-testable.
"""

from __future__ import annotations

from typing import Any, Optional


def _fmt(value: Any, spec: str) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if pd_is_na(number):
        return "n/a"
    return format(number, spec)


def pd_is_na(value: float) -> bool:
    """NaN check without importing pandas in this tiny helper."""
    return value != value


def format_percent(value: Any) -> str:
    """Format a rate as 'x.x%' or 'n/a'."""
    formatted = _fmt(value, ".1f")
    return f"{formatted}%" if formatted != "n/a" else "n/a"


def format_number(value: Any) -> str:
    """Format a count as an integer string or 'n/a'."""
    formatted = _fmt(value, ".0f")
    return formatted if formatted != "n/a" else "n/a"


def format_duration(value: Any) -> str:
    """Format a duration with one decimal or 'n/a'."""
    formatted = _fmt(value, ".1f")
    return formatted if formatted != "n/a" else "n/a"


def prepare_kpi_cards(
    shipment_kpis: Optional[dict[str, Any]] = None,
    delay_kpis: Optional[dict[str, Any]] = None,
    cascade_summary: Optional[dict[str, Any]] = None,
) -> list[dict[str, str]]:
    """Build display-ready KPI cards from analytics outputs.

    Each card is ``{"label": ..., "value": ...}``. Missing sections yield
    "n/a" cards so the overview stays structurally complete.
    """
    shipment_kpis = shipment_kpis or {}
    delay_kpis = delay_kpis or {}
    cascade_summary = cascade_summary or {}
    return [
        {"label": "Total shipments", "value": format_number(shipment_kpis.get("total_shipments"))},
        {"label": "Delayed shipments", "value": format_number(shipment_kpis.get("delayed_shipments"))},
        {"label": "Delay rate", "value": format_percent(shipment_kpis.get("delay_rate"))},
        {"label": "On-time rate", "value": format_percent(shipment_kpis.get("on_time_rate"))},
        {"label": "Average delay", "value": format_duration(delay_kpis.get("average_delay"))},
        {"label": "Cascade candidates", "value": format_number(cascade_summary.get("candidate_count"))},
    ]
