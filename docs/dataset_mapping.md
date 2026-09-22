# Dataset Mapping — LaDe → Cascading Delay Intelligence

## 1. Source dataset

| Item | Value |
| ---- | ----- |
| Dataset | LaDe — Large-scale Last-mile Delivery Dataset |
| Distribution | Hugging Face `Cainiao-AI/LaDe` |
| Revision inspected | `be2cec02775cafc8d52230303f32134382bcc50b` |
| Access date | 2026-09-22 |
| License (Hub metadata) | `apache-2.0` |
| License (paper text) | Research use, CC BY-NC 4.0 terms quoted in the paper |
| Research reference | Wu et al., "LaDe: The First Comprehensive Last-mile Delivery Dataset from Industry", arXiv:2306.10675 (KDD 2024) |
| Official code | https://github.com/wenhaomin/LaDe |
| Dataset website | https://cainiaotechai.github.io/LaDe-website/ |
| File used | `pickup/pickup_jl.csv` (Jilin pickup scenario) |
| Full-file size | ~43 MB, 261,801 packages, 665 couriers, 15 regions, 184 `ds` days |
| Files inspected (header/schema) | `pickup/pickup_jl.csv`, `delivery/delivery_jl.csv` (31,415 rows, 57 couriers, 4 regions) |
| Files NOT used | `delivery/*.csv` (no promised time window → no honest delay definition), `road-network/roads.csv`, trajectory archives (out of MVP scope), all other cities (not needed for the showcase; would harm local performance) |

Why this subset: pickup (not delivery) is the only sub-dataset carrying an
explicit promised time window (`time_window_start`/`time_window_end`), which
is the only honest anchor for a delay definition. Jilin pickup is the
smallest pickup file, keeping local Streamlit execution responsive. No
mirror was used; files come from the official Hub repo (local HF cache of
the official download).

## 2. Actual LaDe schema (observed, not assumed)

`pickup/pickup_jl.csv` columns (19):

```text
order_id, region_id, city, courier_id, accept_time, time_window_start,
time_window_end, lng, lat, aoi_id, aoi_type, pickup_time, pickup_gps_time,
pickup_gps_lng, pickup_gps_lat, accept_gps_time, accept_gps_lng,
accept_gps_lat, ds
```

Notes:

- The identifier is `order_id` (the paper calls it `package_id`); the adapter
  maps it to `shipment_id` 1:1 with no renaming ambiguity.
- Clock times have NO year (`MM-DD HH:MM:SS`); `ds` is MMDD (e.g. `607`).
  The adapter assumes reference year 2022 for parsing only; all durations
  and orderings are relative and unaffected.
- `delivery/delivery_jl.csv` has the same shape minus the time-window
  columns (hence no usable delay anchor) and was not selected.
- There are NO columns for delay reason, delay duration, warehouse,
  transfer, route, scan type, or delivery status in the source.

## 3. Showcase subset rule (systematic, outcome-blind)

```text
source  = pickup/pickup_jl.csv (all 261,801 rows)
rule    = keep rows with ds in [605, 618] (14 contiguous days, June 5-18)
sampling = none (every package, courier, and region in the window is kept)
result  = 25,934 packages -> 51,868 scan events + delay incidents
```

The window was chosen before measuring outcomes, on neutral grounds
(mid-year, contiguous, ~26k packages: large enough for stable route metrics,
small enough for a responsive dashboard). Reproduce with
`pipeline/lade_adapter.py::build_lade_sources`.

## 4. Product-concept mapping

| Product concept | Actual LaDe field/file | Supported? | Transformation |
| --------------- | ---------------------- | ---------- | -------------- |
| Shipment ID | `pickup_jl.csv.order_id` | Yes | 1:1 → `shipment_id` (string) |
| Shipment event | `accept_time`, `pickup_time` (+ GPS-time twins) | Yes | 2 event rows per package: `accept`, `pickup` |
| Event timestamp | `accept_time` / `pickup_time` | Yes | parsed with assumed year 2022 → `timestamp` (UTC) |
| Location | `lng`, `lat`, `aoi_id`, `aoi_type`, `region_id`, `city` | Yes | carried as-is |
| Route | none (no route entity) | Proxy | `route_id = "region_<region_id>"`; documented proxy, not a real route |
| Delay | `pickup_time > time_window_end`, `accept_time > time_window_start` | Yes (derived SLA breach) | per-stage lateness minutes → `delay_duration` (0 when early); threshold is the contract window itself, no invented cutoff |
| Delay reason | none | **No** | column absent everywhere; analytics reports "reason unavailable" |
| Warehouse | none | **No** | no warehouse entity in LaDe; Warehouses dashboard page shows its honest empty state |
| Transfer | none | **No** | no transfer records; `warehouse_transfers.csv` is NOT fabricated; integration records the missing source |
| Delivery outcome | `pickup_time` (task completed) | Partial | completion time is real; no explicit delivered/failed status exists |
| Courier | `courier_id` | Yes | carried as operational actor (not part of the 3-source model) |

## 5. Three operational sources — honest verdict

| Source | Verdict | File |
| ------ | ------- | ---- |
| `shipment_scans` | Genuinely supported (event-level accept/pickup rows + real timestamps, locations, per-stage lateness) | `data/raw/shipment_scans.csv` (51,868 rows) |
| `delay_reports` | Partially supported (real SLA-breach incidents; NO delay reasons) | `data/raw/delay_reports.csv` (shipment-grain, late packages only) |
| `warehouse_transfers` | **Not directly available in LaDe.** No warehouse or transfer entities exist. Closest legitimate representation: none — courier GPS trajectories exist but describe movement, not warehouse transfers, and are out of MVP scope. | **No file created (never fabricated).** |

## 6. Provenance

Every derived row retains `source_file` (`Cainiao-AI/LaDe:pickup/pickup_jl.csv`
+ revision in the adapter docstring), `source_row_id` (0-based line in the
source file), `source_event_id` (`<order_id>:<accept|pickup>`), and
`source_timestamp` (original clock string). Raw LaDe data is read-only and
never committed (see `.gitignore`); only the deterministic adapter
(`pipeline/lade_adapter.py`) plus a small sample (`data/sample/`) are
versioned.

## 7. Known limitations

1. Delay rate is low (~0.2% pickup-late in the full file): LaDe couriers
   mostly pick up well before the window ends. Metrics are real, not tuned.
2. Package-level cascades need BOTH stages late (accept after window start
   AND pickup after window end) — genuinely rare events. Candidates are
   reported as observed; the cascade rule was NOT relaxed to inflate them.
3. No warehouse/transfer analysis is possible; those dashboard sections
   intentionally show empty states.
4. No delay reasons exist; reason breakdowns are unavailable.
5. Times lack a year (assumed 2022 for parsing; relative metrics unaffected).
6. Showcase ≠ full data: the 14-day Jilin window is a performance subset;
   full-file reproduction is supported by the same adapter (drop the `ds`
   filter).
7. Language is associational ("downstream delay observed"), never causal.
