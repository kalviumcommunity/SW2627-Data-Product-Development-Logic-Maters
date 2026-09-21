"""Shared synthetic fixtures for analytics tests (no production dependence)."""

import pandas as pd


def shipments_100_20() -> pd.DataFrame:
    """100 shipments, 20 delayed.

    R1 holds shipments S001-S050 (15 delayed, durations 10..150).
    R2 holds shipments S051-S100 (5 delayed, durations 10..50).
    W1/W2 alternate; reasons cycle traffic/weather/customs.
    Timestamps spread across 2024-01-01 .. 2024-01-10.
    """
    rows = []
    reasons = ["traffic", "weather", "customs"]
    for i in range(1, 101):
        delayed = i <= 15 or 51 <= i <= 55
        duration = float(((i - 1) % 15 + 1) * 10) if delayed else 0.0
        rows.append(
            {
                "shipment_id": f"S{i:03d}",
                "timestamp": f"2024-01-{(i - 1) % 10 + 1:02d} 08:00:00",
                "route_id": "R1" if i <= 50 else "R2",
                "warehouse_id": "W1" if i % 2 else "W2",
                "delay_reason": reasons[(i - 1) % 3] if delayed else "none",
                "delay_duration": duration,
            }
        )
    return pd.DataFrame(rows)


def integrated_like() -> pd.DataFrame:
    """Small frame mimicking integration output incl. traceability columns."""
    return pd.DataFrame(
        {
            "shipment_id": ["S1", "S1", "S2", "S3"],
            "timestamp": [
                "2024-01-01 08:00",
                "2024-01-01 12:00",
                "2024-01-02 09:00",
                "2024-01-03 10:00",
            ],
            "route_id": ["R1", "R1", "R2", "R1"],
            "warehouse_id": ["W1", "W2", "W1", "W1"],
            "delay_reason": ["traffic", "traffic", "weather", None],
            "delay_duration": [30.0, 30.0, 60.0, 0.0],
            "_delay_match": ["both", "both", "both", "left-only"],
            "_transfer_match": ["both", "both", "left-only", "left-only"],
            "_record_source": ["scans"] * 4,
            "_source_datasets": ["scans+delays+transfers"] * 4,
            "_integration_key": ["S1", "S1", "S2", "S3"],
        }
    )
