"""LaDe source adapter (mapping boundary only).

Transforms the real LaDe last-mile pickup records into the product's three
operational source datasets WITHOUT inventing data:

* ``shipment_scans`` — supported (event-level accept/pickup rows).
* ``delay_reports`` — partially supported (SLA-breach incidents derived from
  real promised time windows; ``delay_reason`` is NOT available in LaDe).
* ``warehouse_transfers`` — NOT available in LaDe (no warehouse or transfer
  entities exist in the source); no file is fabricated.

Provenance: every derived row keeps ``source_file``, ``source_row_id``,
``source_event_id`` and ``source_timestamp`` pointing at the original LaDe
record. The transformation is deterministic and reproducible.

Source: ``Cainiao-AI/LaDe`` (Hugging Face), file ``pickup/pickup_jl.csv``,
revision ``be2cec02775cafc8d52230303f32134382bcc50b``, accessed 2026-09-22.
Reference: Wu et al., "LaDe: The First Comprehensive Last-mile Delivery
Dataset from Industry", arXiv:2306.10675 (KDD 2024).
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd

PathLike = Union[str, Path]

SOURCE_REPO = "Cainiao-AI/LaDe"
SOURCE_REVISION = "be2cec02775cafc8d52230303f32134382bcc50b"
SOURCE_FILE = "pickup/pickup_jl.csv"
ACCESS_DATE = "2026-09-22"

# Showcase subset rule (systematic, outcome-blind): Jilin pickup records whose
# `ds` day-marker falls in the contiguous window 0605-0618 (14 days). Jilin
# pickup is the smallest pickup file (fast local execution) and pickup (not
# delivery) is the only sub-dataset carrying explicit promised time windows,
# which is what makes an honest SLA-anchored delay definition possible.
SHOWCASE_DS_MIN = 605
SHOWCASE_DS_MAX = 618

# LaDe clock times carry no year ("MM-DD HH:MM:SS"); `ds` is MMDD. A fixed
# reference year is assumed ONLY for parsing; all durations/orderings are
# relative and unaffected by the choice.
ASSUMED_YEAR = 2022

REQUIRED_LADE_COLUMNS = (
    "order_id",
    "region_id",
    "city",
    "courier_id",
    "accept_time",
    "time_window_start",
    "time_window_end",
    "lng",
    "lat",
    "aoi_id",
    "aoi_type",
    "pickup_time",
    "ds",
)


def parse_lade_time(series: pd.Series, year: int = ASSUMED_YEAR) -> pd.Series:
    """Parse LaDe ``MM-DD HH:MM:SS`` clock times (unparsable -> NaT)."""
    return pd.to_datetime(
        f"{year}-" + series.astype("string").str.strip(),
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )


def load_lade_pickup(
    source_path: PathLike,
    ds_min: int = SHOWCASE_DS_MIN,
    ds_max: int = SHOWCASE_DS_MAX,
) -> tuple[pd.DataFrame, dict]:
    """Load the LaDe pickup file and apply the showcase subset rule.

    Returns ``(subset_frame, info)`` where the frame keeps original LaDe
    columns plus a ``_lade_row_id`` (0-based line number in the source file).
    Raises ``ValueError`` when required columns are absent (never renamed
    blindly).
    """
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"LaDe source not found: {source}")
    frame = pd.read_csv(source)
    missing = [c for c in REQUIRED_LADE_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(
            f"LaDe schema mismatch in {source.name}: missing columns {missing}. "
            f"Found: {list(frame.columns)}. Refusing to guess mappings."
        )
    frame = frame.copy()
    frame["_lade_row_id"] = range(len(frame))
    ds = pd.to_numeric(frame["ds"], errors="coerce")
    subset = frame[(ds >= ds_min) & (ds <= ds_max)].reset_index(drop=True)
    info = {
        "source_repo": SOURCE_REPO,
        "source_revision": SOURCE_REVISION,
        "source_file": SOURCE_FILE,
        "access_date": ACCESS_DATE,
        "assumed_year": ASSUMED_YEAR,
        "subset_rule": (
            f"ds in [{ds_min}, {ds_max}] (contiguous 14-day window, "
            "all records, no sampling)"
        ),
        "source_rows": int(len(frame)),
        "subset_rows": int(len(subset)),
    }
    return subset, info


def _lateness_minutes(actual: pd.Series, scheduled: pd.Series) -> pd.Series:
    """Minutes late (actual - scheduled); early/on-time -> 0.0; NaT -> NaN."""
    minutes = (actual - scheduled).dt.total_seconds() / 60.0
    return minutes.clip(lower=0.0)


def build_shipment_scans(
    lade: pd.DataFrame, source_label: str = f"{SOURCE_REPO}:{SOURCE_FILE}"
) -> pd.DataFrame:
    """Build event-grain shipment scans (2 rows per package).

    * ``accept`` event: actual ``accept_time`` vs scheduled
      ``time_window_start``.
    * ``pickup`` event: actual ``pickup_time`` vs scheduled
      ``time_window_end``.
    * ``delay_duration`` is the real per-stage lateness in minutes (0 when
      early/on-time), anchored to the promised window — no thresholds.
    * ``route_id`` is a documented proxy (``region_<region_id>``): LaDe has
      no explicit route entity.
    """
    accept_actual = parse_lade_time(lade["accept_time"])
    accept_sched = parse_lade_time(lade["time_window_start"])
    pickup_actual = parse_lade_time(lade["pickup_time"])
    pickup_sched = parse_lade_time(lade["time_window_end"])
    accept_late = _lateness_minutes(accept_actual, accept_sched)
    pickup_late = _lateness_minutes(pickup_actual, pickup_sched)

    base = pd.DataFrame(
        {
            "shipment_id": lade["order_id"].astype("string"),
            "courier_id": lade["courier_id"].astype("string"),
            "route_id": "region_" + lade["region_id"].astype("string"),
            "region_id": lade["region_id"],
            "aoi_id": lade["aoi_id"],
            "aoi_type": lade["aoi_type"],
            "city": lade["city"],
            "lng": pd.to_numeric(lade["lng"], errors="coerce"),
            "lat": pd.to_numeric(lade["lat"], errors="coerce"),
            "ds": lade["ds"],
            "source_file": source_label,
            "source_row_id": lade["_lade_row_id"],
        }
    )
    accept = base.copy()
    accept["event_type"] = "accept"
    accept["timestamp"] = accept_actual.dt.strftime("%Y-%m-%d %H:%M:%S")
    accept["scheduled_time"] = accept_sched.dt.strftime("%Y-%m-%d %H:%M:%S")
    accept["delay_duration"] = accept_late
    accept["source_event_id"] = accept["shipment_id"] + ":accept"
    accept["source_timestamp"] = lade["accept_time"]

    pickup = base.copy()
    pickup["event_type"] = "pickup"
    pickup["timestamp"] = pickup_actual.dt.strftime("%Y-%m-%d %H:%M:%S")
    pickup["scheduled_time"] = pickup_sched.dt.strftime("%Y-%m-%d %H:%M:%S")
    pickup["delay_duration"] = pickup_late
    pickup["source_event_id"] = pickup["shipment_id"] + ":pickup"
    pickup["source_timestamp"] = lade["pickup_time"]

    scans = pd.concat([accept, pickup], ignore_index=True)
    scans["status"] = pd.to_numeric(
        scans["delay_duration"], errors="coerce"
    ).fillna(0).gt(0).map({True: "delayed", False: "on_time"})
    scans = scans.sort_values(
        ["shipment_id", "timestamp"], kind="mergesort", na_position="last"
    ).reset_index(drop=True)
    return scans[
        [
            "shipment_id", "timestamp", "event_type", "status",
            "delay_duration", "scheduled_time", "courier_id", "route_id",
            "region_id", "aoi_id", "aoi_type", "city", "lng", "lat", "ds",
            "source_file", "source_row_id", "source_event_id",
            "source_timestamp",
        ]
    ]


def build_delay_reports(
    lade: pd.DataFrame, source_label: str = f"{SOURCE_REPO}:{SOURCE_FILE}"
) -> tuple[pd.DataFrame, dict]:
    """Build shipment-grain delay incidents (packages with any stage late).

    One row per late package (keeps the integration join one-to-many at
    most, never cartesian). ``delay_duration`` is the customer-facing pickup
    lateness; ``initial_delay_duration`` is the accept-stage lateness. Both
    are real window-anchored minutes. ``delay_reason`` is NOT available in
    LaDe and is therefore absent (never invented).
    """
    accept_actual = parse_lade_time(lade["accept_time"])
    accept_sched = parse_lade_time(lade["time_window_start"])
    pickup_actual = parse_lade_time(lade["pickup_time"])
    pickup_sched = parse_lade_time(lade["time_window_end"])
    accept_late = _lateness_minutes(accept_actual, accept_sched)
    pickup_late = _lateness_minutes(pickup_actual, pickup_sched)

    late_mask = (accept_late.fillna(0) > 0) | (pickup_late.fillna(0) > 0)
    late = lade.loc[late_mask].reset_index(drop=True)
    info = {
        "packages_checked": int(len(lade)),
        "incident_packages": int(late_mask.sum()),
        "pickup_late_packages": int((pickup_late.fillna(0) > 0).sum()),
        "accept_late_packages": int((accept_late.fillna(0) > 0).sum()),
        "note": (
            "Incidents are real SLA touches (actual later than promised "
            "window). delay_reason is not available in LaDe."
        ),
    }
    if late.empty:
        columns = [
            "shipment_id", "delay_id", "delay_stage", "delay_duration",
            "initial_delay_duration", "reported_at", "courier_id",
            "route_id", "region_id", "city", "ds", "source_file",
            "source_row_id", "source_timestamp",
        ]
        return pd.DataFrame(columns=columns), info

    pickup_late_vals = pickup_late.loc[late_mask].reset_index(drop=True).fillna(0.0)
    accept_late_vals = accept_late.loc[late_mask].reset_index(drop=True).fillna(0.0)
    delays = pd.DataFrame(
        {
            "shipment_id": late["order_id"].astype("string"),
            "delay_stage": pd.to_numeric(pickup_late_vals, errors="coerce").gt(0).map(
                {True: "pickup", False: "accept"}
            ),
            "delay_duration": pd.to_numeric(pickup_late_vals, errors="coerce"),
            "initial_delay_duration": pd.to_numeric(accept_late_vals, errors="coerce"),
            "reported_at": parse_lade_time(late["pickup_time"]).dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "courier_id": late["courier_id"].astype("string"),
            "route_id": "region_" + late["region_id"].astype("string"),
            "region_id": late["region_id"],
            "city": late["city"],
            "ds": late["ds"],
            "source_file": source_label,
            "source_row_id": late["_lade_row_id"],
            "source_timestamp": late["pickup_time"],
        }
    )
    delays["delay_id"] = "DL-" + delays["shipment_id"]
    return delays[
        [
            "shipment_id", "delay_id", "delay_stage", "delay_duration",
            "initial_delay_duration", "reported_at", "courier_id",
            "route_id", "region_id", "city", "ds", "source_file",
            "source_row_id", "source_timestamp",
        ]
    ], info


def build_lade_sources(
    source_path: PathLike,
    raw_dir: PathLike = Path("data/raw"),
    ds_min: int = SHOWCASE_DS_MIN,
    ds_max: int = SHOWCASE_DS_MAX,
) -> dict:
    """Run the full LaDe mapping boundary: subset -> scans/delays CSVs.

    Writes ``shipment_scans.csv`` and ``delay_reports.csv`` into ``raw_dir``
    (no warehouse file: not available in LaDe). Returns a run summary.
    """
    lade, info = load_lade_pickup(source_path, ds_min, ds_max)
    scans = build_shipment_scans(lade)
    delays, delay_info = build_delay_reports(lade)

    out_dir = Path(raw_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scans_path = out_dir / "shipment_scans.csv"
    delays_path = out_dir / "delay_reports.csv"
    scans.to_csv(scans_path, index=False)
    delays.to_csv(delays_path, index=False)
    return {
        **info,
        "scans_rows": int(len(scans)),
        "delays_rows": int(len(delays)),
        "scans_path": str(scans_path),
        "delays_path": str(delays_path),
        "warehouse_transfers": (
            "NOT available in LaDe (no warehouse/transfer entities); "
            "no file fabricated."
        ),
        "delay_info": delay_info,
    }
