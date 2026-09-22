"""Deterministic synthetic showcase data (generation boundary only).

Produces the three operational sources the product model expects, sized and
shaped so every pipeline stage and dashboard page has real signal to work
with (~3k shipments, 6 routes, 5 warehouses, 5 delay reasons, hub transfers,
and genuine multi-stage cascade chains):

* ``showcase_shipment_scans`` — event-grain journey rows (pickup,
  hub_arrival, hub_departure, delivery_attempt, delivery).
* ``showcase_delay_reports`` — one row per delayed shipment (shipment grain,
  like the LaDe adapter output; on-time shipments have no row).
* ``showcase_warehouse_transfers`` — one row per hub-routed shipment that
  has transfer tracking (a documented ~10% gap has none, exercising
  ``_transfer_match`` reporting honestly).

Design rules (all deterministic under ``SEED``):

* Delay probabilities differ by route/warehouse (R2 + W2 are the problem
  lane) and a later stage is much likelier to be late when an earlier
  stage was — that is what creates honest cascade candidates.
* Every timestamp is chronological within a journey; ``reported_at`` is
  always after the last event, so temporal checks come back clean.
* One transfer row per shipment at most: scans x transfers stays
  many-to-one, never a many-to-many cartesian.
* ``delay_duration`` is always >= 0, ``shipment_id`` never missing, no
  exact-duplicate rows — the cleaning layer is exercised, not fought.

Everything here is labeled synthetic: raw files land in
``data/raw/showcase/``, cleaned frames in ``data/processed/showcase/``,
and the integrated output is ``data/processed/integrated_logistics_showcase.csv``.
Raw/processed data is gitignored (local artifacts); this script plus a
small sample under ``data/sample/`` are what get versioned.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Make the repo root importable when run as a script
# (`python pipeline/synthetic_showcase.py` puts only pipeline/ on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Any, Optional, Union

import numpy as np
import pandas as pd

PathLike = Union[str, Path]

SEED = 42
N_SHIPMENTS = 3000
START_DATE = datetime(2024, 3, 1)
N_DAYS = 21

ROUTES = ["R1", "R2", "R3", "R4", "R5", "R6"]
ROUTE_WEIGHTS = [0.20, 0.22, 0.16, 0.14, 0.14, 0.14]
# Per-route pickup delay probability (R2 is the problem lane).
ROUTE_DELAY_P = {"R1": 0.12, "R2": 0.38, "R3": 0.14, "R4": 0.16, "R5": 0.11, "R6": 0.13}
# Per-route hub-routing probability (R2 flows through the congested hub).
ROUTE_HUB_P = {"R1": 0.40, "R2": 0.62, "R3": 0.42, "R4": 0.38, "R5": 0.40, "R6": 0.41}
# Origin facility per route.
ROUTE_ORIGIN = {"R1": "W1", "R2": "W2", "R3": "W3", "R4": "W1", "R5": "W4", "R6": "W5"}

WAREHOUSES = ["W1", "W2", "W3", "W4", "W5"]
# Per-hub event delay probability (W2 is the congested hub).
HUB_DELAY_P = {"W1": 0.10, "W2": 0.34, "W3": 0.12, "W4": 0.09, "W5": 0.11}

REASONS = ["traffic", "weather", "customs", "congestion", "mechanical"]
# Reason mix shifts with context (hub stages skew to congestion/mechanical,
# the northern lane R4 skews to weather); base mix otherwise.
REASON_BASE = [0.34, 0.18, 0.16, 0.20, 0.12]
REASON_HUB = [0.16, 0.10, 0.12, 0.42, 0.20]
REASON_R4 = [0.22, 0.44, 0.12, 0.12, 0.10]

BASE_DELIVERY_P = 0.08  # delivery late with no earlier delay
CASCADE_BOOST_P = 0.55  # delivery/hub-departure late given an earlier delay
TRANSFER_TRACKING_P = 0.90  # hub shipments with a transfer record
REDELIVERY_P = 0.55  # delayed direct delivery gets attempt + redelivery rows

RAW_DIR = Path("data/raw/showcase")
PROCESSED_DIR = Path("data/processed/showcase")
SHOWCASE_OUTPUT_FILENAME = "integrated_logistics_showcase.csv"

CLEANING_CONFIGS: dict[str, dict[str, Any]] = {
    "showcase_shipment_scans": {
        "identifier_columns": ["shipment_id"],
        "numeric_columns": ["delay_duration"],
        "categorical_columns": ["route_id", "scan_type", "status"],
        "datetime_columns": ["timestamp"],
        "non_negative_columns": ["delay_duration"],
    },
    "showcase_delay_reports": {
        "identifier_columns": ["shipment_id", "delay_id"],
        "numeric_columns": ["delay_duration", "initial_delay_duration"],
        "categorical_columns": ["route_id", "warehouse_id", "delay_reason"],
        "datetime_columns": ["reported_at"],
        "non_negative_columns": ["delay_duration", "initial_delay_duration"],
    },
    "showcase_warehouse_transfers": {
        "identifier_columns": ["shipment_id", "transfer_id"],
        "numeric_columns": [],
        "categorical_columns": [
            "source_warehouse",
            "destination_warehouse",
            "transfer_status",
        ],
        "datetime_columns": [
            "transfer_time",
            "expected_transfer_time",
            "actual_transfer_time",
        ],
    },
}


def _minutes(rng: np.random.RandomState, scale: float = 50.0) -> float:
    """One delay duration: 10 min floor, exponential tail, 12h cap."""
    return float(min(720.0, round(10.0 + rng.exponential(scale), 1)))


def _pick_reason(rng: np.random.RandomState, route: str, hub_stage: bool) -> str:
    weights = REASON_HUB if hub_stage else (REASON_R4 if route == "R4" else REASON_BASE)
    return str(rng.choice(REASONS, p=np.asarray(weights, dtype=float)))


def generate_showcase(seed: int = SEED, n_shipments: int = N_SHIPMENTS) -> dict[str, pd.DataFrame]:
    """Generate the three raw source frames (deterministic for a seed)."""
    rng = np.random.RandomState(seed)
    scan_rows: list[dict[str, Any]] = []
    delay_rows: list[dict[str, Any]] = []
    transfer_rows: list[dict[str, Any]] = []

    route_weights = np.asarray(ROUTE_WEIGHTS, dtype=float)

    for i in range(1, n_shipments + 1):
        shipment = f"S{i:05d}"
        route = str(rng.choice(ROUTES, p=route_weights))
        origin = ROUTE_ORIGIN[route]
        day = (i - 1) % N_DAYS
        clock = START_DATE + timedelta(days=int(day))
        pickup_time = clock + timedelta(hours=8, minutes=int(rng.randint(0, 120)))

        hubbed = bool(rng.rand() < ROUTE_HUB_P[route])
        hub = None
        if hubbed:
            choices = [w for w in WAREHOUSES if w != origin]
            hub = str(rng.choice(choices))

        events: list[dict[str, Any]] = []  # (time, scan_type, warehouse, delay_p, hub_stage)

        pickup_late = bool(rng.rand() < ROUTE_DELAY_P[route])
        events.append(
            {
                "time": pickup_time,
                "scan_type": "pickup",
                "warehouse": origin,
                "delayed": pickup_late,
                "hub_stage": False,
            }
        )

        earlier_late = pickup_late
        if hubbed:
            assert hub is not None
            hub_p = HUB_DELAY_P[hub]
            arr_time = pickup_time + timedelta(hours=int(rng.randint(4, 11)))
            arr_late = bool(rng.rand() < (CASCADE_BOOST_P if earlier_late else hub_p))
            events.append(
                {
                    "time": arr_time,
                    "scan_type": "hub_arrival",
                    "warehouse": hub,
                    "delayed": arr_late,
                    "hub_stage": True,
                }
            )
            earlier_late = earlier_late or arr_late
            dep_time = arr_time + timedelta(hours=int(rng.randint(1, 5)))
            dep_late = bool(rng.rand() < (CASCADE_BOOST_P if earlier_late else hub_p * 0.8))
            events.append(
                {
                    "time": dep_time,
                    "scan_type": "hub_departure",
                    "warehouse": hub,
                    "delayed": dep_late,
                    "hub_stage": True,
                }
            )
            earlier_late = earlier_late or dep_late
            last_time = dep_time
        else:
            last_time = pickup_time

        delivery_time = last_time + timedelta(hours=int(rng.randint(6, 19)))
        delivery_p = CASCADE_BOOST_P if earlier_late else BASE_DELIVERY_P
        delivery_late = bool(rng.rand() < delivery_p)

        if not hubbed and delivery_late and rng.rand() < REDELIVERY_P:
            # Failed first attempt (kept, status delayed, non-final) plus a
            # next-day redelivery: this is what yields downstream_route_delay
            # stages on direct lanes.
            events.append(
                {
                    "time": delivery_time,
                    "scan_type": "delivery_attempt",
                    "warehouse": None,
                    "delayed": True,
                    "hub_stage": False,
                }
            )
            redelivery_late = bool(rng.rand() < 0.20)
            events.append(
                {
                    "time": delivery_time + timedelta(hours=int(rng.randint(14, 26))),
                    "scan_type": "delivery",
                    "warehouse": None,
                    "delayed": redelivery_late,
                    "hub_stage": False,
                }
            )
        else:
            events.append(
                {
                    "time": delivery_time,
                    "scan_type": "delivery",
                    "warehouse": None,
                    "delayed": delivery_late,
                    "hub_stage": False,
                }
            )

        # Materialize scan rows (final event always status delivered).
        for pos, event in enumerate(events):
            is_final = pos == len(events) - 1
            duration = _minutes(rng) if event["delayed"] else 0.0
            if is_final:
                status = "delivered"
            else:
                status = "delayed" if event["delayed"] else "on_time"
            scan_rows.append(
                {
                    "shipment_id": shipment,
                    "timestamp": event["time"].strftime("%Y-%m-%d %H:%M:%S"),
                    "scan_type": event["scan_type"],
                    "status": status,
                    "delay_duration": duration,
                    "route_id": route,
                    "warehouse_id": event["warehouse"],
                    "source_file": "synthetic_showcase",
                    "source_row_id": len(scan_rows),
                }
            )

        delayed_events = [e for e in events if e["delayed"]]
        if delayed_events:
            # Durations were drawn above in event order; recover them from
            # the scan rows just appended.
            seg = scan_rows[len(scan_rows) - len(events):]
            durations = [float(r["delay_duration"]) for r in seg]
            worst_duration = max(durations)
            worst_pos = int(np.argmax(durations))
            worst_event = events[worst_pos]
            delay_rows.append(
                {
                    "shipment_id": shipment,
                    "delay_id": f"DL-{shipment}",
                    "delay_reason": _pick_reason(
                        rng, route, bool(worst_event["hub_stage"])
                    ),
                    "delay_duration": worst_duration,
                    "initial_delay_duration": durations[0],
                    "reported_at": (
                        events[-1]["time"] + timedelta(hours=2)
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "route_id": route,
                    "warehouse_id": hub if hubbed else origin,
                    "source_file": "synthetic_showcase",
                    "source_row_id": len(delay_rows),
                }
            )

        if hubbed and rng.rand() < TRANSFER_TRACKING_P:
            assert hub is not None
            hub_arr_time = events[1]["time"]
            transfer_rows.append(
                {
                    "transfer_id": f"T-{shipment}",
                    "shipment_id": shipment,
                    "source_warehouse": origin,
                    "destination_warehouse": hub,
                    "transfer_time": hub_arr_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "expected_transfer_time": (
                        hub_arr_time - timedelta(hours=1)
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "actual_transfer_time": hub_arr_time.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "transfer_status": (
                        "delayed" if events[1]["delayed"] else "on_time"
                    ),
                    "source_file": "synthetic_showcase",
                    "source_row_id": len(transfer_rows),
                }
            )

    scans = pd.DataFrame(scan_rows)
    delays = pd.DataFrame(delay_rows)
    transfers = pd.DataFrame(transfer_rows)
    return {
        "showcase_shipment_scans": scans,
        "showcase_delay_reports": delays,
        "showcase_warehouse_transfers": transfers,
    }


def build_showcase_sources(
    seed: int = SEED,
    n_shipments: int = N_SHIPMENTS,
    raw_dir: PathLike = RAW_DIR,
) -> dict[str, Any]:
    """Generate showcase sources and write raw CSVs (creates parents)."""
    frames = generate_showcase(seed=seed, n_shipments=n_shipments)
    out_dir = Path(raw_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name, frame in frames.items():
        path = out_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = str(path)
    delayed = int((frames["showcase_shipment_scans"]["delay_duration"] > 0).sum())
    return {
        "seed": seed,
        "n_shipments": n_shipments,
        "raw_dir": str(out_dir),
        "paths": paths,
        "scan_rows": int(len(frames["showcase_shipment_scans"])),
        "delay_rows": int(len(frames["showcase_delay_reports"])),
        "transfer_rows": int(len(frames["showcase_warehouse_transfers"])),
        "delayed_events": delayed,
    }


def run_showcase_pipeline(
    seed: int = SEED,
    n_shipments: int = N_SHIPMENTS,
    raw_dir: PathLike = RAW_DIR,
    processed_dir: PathLike = PROCESSED_DIR,
    output_path: Optional[PathLike] = None,
) -> dict[str, Any]:
    """End-to-end showcase run: generate -> clean -> integrate -> save.

    Cleaning uses :func:`pipeline.cleaning.clean_file` with the declared
    configs above; integration joins on ``shipment_id`` with temporal scope
    limited to the meaningful ``timestamp <= reported_at`` pair.
    """
    from pipeline.cleaning import clean_file
    from pipeline.integration import (
        build_integrated_dataset,
        format_integration_report,
        load_processed_datasets,
        save_integrated_dataset,
    )

    gen_info = build_showcase_sources(
        seed=seed, n_shipments=n_shipments, raw_dir=raw_dir
    )
    out_processed = Path(processed_dir)
    out_processed.mkdir(parents=True, exist_ok=True)

    cleaned: dict[str, Any] = {}
    summaries: dict[str, Any] = {}
    for name in (
        "showcase_shipment_scans",
        "showcase_delay_reports",
        "showcase_warehouse_transfers",
    ):
        raw_path = Path(gen_info["paths"][name])
        frame, summary, saved = clean_file(
            raw_path,
            output_path=out_processed / f"{name}_cleaned.csv",
            dataset_name=name,
            **CLEANING_CONFIGS[name],
        )
        cleaned[name] = frame
        summaries[name] = summary

    datasets = load_processed_datasets(out_processed)
    integrated, report = build_integrated_dataset(
        datasets,
        timestamp_pairs=[("timestamp", "reported_at")],
    )
    destination = (
        Path(output_path)
        if output_path is not None
        else Path("data/processed") / SHOWCASE_OUTPUT_FILENAME
    )
    saved_path = save_integrated_dataset(integrated, destination)
    return {
        "generation": gen_info,
        "cleaning": summaries,
        "integration_report": report,
        "integration_report_text": format_integration_report(report),
        "integrated_path": str(saved_path),
        "integrated_rows": int(len(integrated)),
        "integrated_columns": [str(c) for c in integrated.columns],
    }


if __name__ == "__main__":
    info = run_showcase_pipeline()
    print(f"seed={info['generation']['seed']} "
          f"shipments={info['generation']['n_shipments']}")
    print(f"raw: scans={info['generation']['scan_rows']} "
          f"delays={info['generation']['delay_rows']} "
          f"transfers={info['generation']['transfer_rows']}")
    for name, summary in info["cleaning"].items():
        print(f"cleaned {name}: "
              f"{summary['input_rows']} -> {summary['output_rows']} rows")
    print(info["integration_report_text"])
    print(f"integrated: {info['integrated_path']} "
          f"({info['integrated_rows']} rows)")
