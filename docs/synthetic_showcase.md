# Synthetic Showcase Dataset — Cascading Delay Intelligence

## 1. Why this exists

The real-world LaDe showcase (`docs/dataset_mapping.md`) honestly cannot
cover warehouses, transfers, delay reasons, or cascades: LaDe pickup has no
such entities, so those dashboard sections show empty states on LaDe data.
This synthetic showcase is the complement: a **deterministic, documented,
clearly labeled** dataset that exercises the *full* product surface —
all three sources, all dashboard pages, all SQL sections, all alert types.

It is synthetic by construction and never presented as observed data:
every raw row carries `source_file = synthetic_showcase`, and the
integrated output is `integrated_logistics_showcase.csv` (the LaDe
integrated file remains the dashboard default).

## 2. How to (re)produce

```bash
python pipeline/synthetic_showcase.py
```

or from Python:

```python
from pipeline.synthetic_showcase import run_showcase_pipeline
info = run_showcase_pipeline()  # seed=42, 3,000 shipments
```

Steps: `generate_showcase()` → raw CSVs in `data/raw/showcase/` →
`clean_file()` per source (declared configs in `CLEANING_CONFIGS`) →
`data/processed/showcase/` → `build_integrated_dataset()` →
`data/processed/integrated_logistics_showcase.csv`. Raw/processed files
are gitignored local artifacts; the generator (`pipeline/`) plus a
1,016-row sample (`data/sample/showcase_sample.csv`, 340 whole journeys)
are versioned. Tests: `pytest tests/test_synthetic_showcase.py`.

## 3. Design (seed 42, 3,000 shipments, 2024-03-01 + 21 days)

| Dimension | Design |
| --------- | ------ |
| Routes | R1–R6 (weighted); **R2 is the problem lane** (38% pickup-delay p, 62% hub-routed) |
| Warehouses | W1–W5; **W2 is the congested hub** (34% hub-event delay p); per-route origin facilities |
| Journeys | 55% direct (pickup → delivery, failed attempts get attempt + redelivery rows), 45% hub (pickup → hub_arrival → hub_departure → delivery) |
| Delay reasons | traffic / weather / customs / congestion / mechanical; mix shifts with context (hub stages → congestion, R4 → weather) |
| Cascade mechanism | a later stage is far likelier to be late when an earlier stage was (55% vs 8%) — candidates emerge from the process, not from tuning |
| Transfers | one row per hub-routed shipment at most (many-to-one joins, never cartesian); a documented ~10% tracking gap has no transfer row, exercising `_transfer_match` honestly |
| Time | strictly chronological journeys; `reported_at` always after the last event (0 temporal violations) |
| Hygiene | `shipment_id` never missing, `delay_duration` ≥ 0, no exact-duplicate rows — cleaning loses 0 rows |

## 4. Observed headline metrics (seed 42)

- 3,000 shipments → 8,870 scan events + 990 delay incidents + 1,233 transfers
- Delay rate **33.0%** (990 delayed), avg delay 61.3 min (median 45.3)
- **602 cascade candidates (20.1%)**, depths 1/2/3 = 390/167/45; stages observed: `initial_delay`, `transfer_disruption`, `warehouse_delay`, `final_delivery_delay`, `downstream_route_delay`
- Worst lane confirmed by the data: R2 (46.6% delay rate), W2 (41.1%)
- Alerts: 1,277 (412 critical, 757 warning, 108 info); **zero unavailable checks** — every alert type fires
- SQL/Pandas: **15/15 like-for-like comparisons match** (3 shipment KPIs + record-average delay + 6 routes + 5 warehouses), including the route and warehouse sections that are unrunnable on LaDe

## 5. Limitations (read before demoing)

1. Synthetic: realistic *shapes*, not observed behaviour. Problem-lane
   parameters (R2/W2) are chosen, not learned.
2. One transfer leg per shipment max (keeps joins many-to-one); real
   networks have multi-leg journeys.
3. Delay rate (~33%) is higher than typical operations — tuned for a
   readable sprint demo, not for calibration.
4. Language stays associational ("downstream delay observed"), never causal.
