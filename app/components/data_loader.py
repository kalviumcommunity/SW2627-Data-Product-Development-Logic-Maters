"""Dashboard data loading (no Streamlit dependency).

The Streamlit entry point wraps :func:`load_processed_csv` with
``st.cache_data``. Everything here is pure and unit-testable. Nothing is
ever written back to disk: filters and pages operate on in-memory copies.

When no processed data exists, :func:`build_demo_dataset` provides a
clearly labeled synthetic dataset so the UI can be exercised without
fabricating production insights.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd

PathLike = Union[str, Path]

PROCESSED_DIR = Path("data/processed")
INTEGRATED_FILENAME = "integrated_logistics_data.csv"


def discover_processed_datasets(
    processed_dir: PathLike = PROCESSED_DIR,
) -> list[Path]:
    """List processed CSVs, integrated output first, then alphabetical."""
    directory = Path(processed_dir)
    if not directory.is_dir():
        return []
    files = sorted(
        (p for p in directory.glob("*.csv") if p.is_file()),
        key=lambda p: p.name,
    )
    integrated = [p for p in files if p.name == INTEGRATED_FILENAME]
    return integrated + [p for p in files if p.name != INTEGRATED_FILENAME]


def load_processed_csv(path: PathLike) -> pd.DataFrame:
    """Load one processed CSV (read-only; raises FileNotFoundError)."""
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Dataset not found: {resolved}")
    return pd.read_csv(resolved)


def build_demo_dataset() -> pd.DataFrame:
    """Build a deterministic synthetic demo dataset (in-memory only).

    Clearly labeled via ``_demo_source`` so the UI can badge it as DEMO.
    Mirrors canonical integrated columns: 60 shipments across 3 routes and
    3 warehouses with mixed on-time/delayed records, reasons, statuses,
    one transfer leg per delayed shipment, and traceability columns.
    """
    rows: list[dict] = []
    reasons = ["traffic", "weather", "customs"]
    for i in range(1, 61):
        shipment = f"D{i:03d}"
        route = f"R{(i - 1) % 3 + 1}"
        warehouse = f"W{(i - 1) % 3 + 1}"
        day = (i - 1) % 14 + 1
        delayed = i % 3 != 0  # 40 delayed, 20 on-time
        duration = float((i % 7 + 1) * 10) if delayed else 0.0
        rows.append(
            {
                "shipment_id": shipment,
                "timestamp": f"2024-03-{day:02d} 08:{i % 60:02d}:00",
                "route_id": route,
                "warehouse_id": warehouse,
                "status": "delayed" if delayed else "delivered",
                "delay_reason": reasons[(i - 1) % 3] if delayed else "none",
                "delay_duration": duration,
                "reported_at": (
                    f"2024-03-{day:02d} 10:{i % 60:02d}:00" if delayed else None
                ),
                "transfer_id": f"T{i:03d}" if delayed and i % 2 == 0 else None,
                "source_warehouse": warehouse if delayed and i % 2 == 0 else None,
                "destination_warehouse": (
                    f"W{i % 3 + 1}" if delayed and i % 2 == 0 else None
                ),
                "_delay_match": "both" if delayed else "left-only",
                "_transfer_match": (
                    "both" if delayed and i % 2 == 0 else "left-only"
                ),
                "_record_source": "demo",
                "_demo_source": True,
            }
        )
        if delayed and i % 4 == 0:
            # A second delayed event for some shipments so cascade
            # candidates exist in the demo.
            rows.append(
                {
                    "shipment_id": shipment,
                    "timestamp": f"2024-03-{min(day + 1, 28):02d} 14:00:00",
                    "route_id": route,
                    "warehouse_id": f"W{i % 3 + 1}",
                    "status": "delayed",
                    "delay_reason": "congestion",
                    "delay_duration": duration + 15.0,
                    "reported_at": f"2024-03-{min(day + 1, 28):02d} 15:00:00",
                    "transfer_id": None,
                    "source_warehouse": None,
                    "destination_warehouse": None,
                    "_delay_match": "both",
                    "_transfer_match": "left-only",
                    "_record_source": "demo",
                    "_demo_source": True,
                }
            )
    return pd.DataFrame(rows)
