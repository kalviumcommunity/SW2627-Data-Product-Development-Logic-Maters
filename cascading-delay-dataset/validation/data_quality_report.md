# Data Quality & Integrity Validation Report

**Project:** Cascading Delay Intelligence  
**Dataset Generation Date:** 2026-09-24 09:57:55  
**Simulation Window:** 2026-08-01 00:00:00 to 2026-08-31 23:59:59 (31 days)  
**Random Seed:** 42 (100% Deterministic & Reproducible)

---

## 1. Executive Summary & Verification Matrix

All 14 automated data quality, causal validity, and relational integrity checks have **PASSED** with zero violations.

| Check ID | Verification Rule | Target Expectation | Observed Result | Status |
|---|---|---|---|---|
| **CHK-01** | Primary Key Uniqueness | Zero duplicate IDs in all 9 tables | 0 duplicates across 9 tables | **PASSED** |
| **CHK-02** | FK Integrity: Dependencies -> Shipments | 100% valid upstream & downstream IDs | 0 orphan references | **PASSED** |
| **CHK-03** | FK Integrity: Events -> Shipments | 100% valid shipment IDs | 0 orphan events | **PASSED** |
| **CHK-04** | FK Integrity: Locations Existence | 100% valid origin, destination, hub IDs | 0 invalid location IDs | **PASSED** |
| **CHK-05** | FK Integrity: Vehicles Existence | 100% valid assigned vehicle IDs | 0 invalid vehicle IDs | **PASSED** |
| **CHK-06** | Chronological Ordering of Events | `t_entry <= t_load <= t_dep <= t_arr <= t_unload` | 0 temporal inversions | **PASSED** |
| **CHK-07** | Travel Physics Consistency | `actual_arrival >= actual_departure` | 0 arrival before departure | **PASSED** |
| **CHK-08** | Mathematical Delay Precision | `final_delay_minutes == round(act_arr - plan_arr)` | 0 calculation mismatches | **PASSED** |
| **CHK-09** | Cascade Delay Correspondence | All cascade-affected shipments have positive delays | 0 zero-delay cascade events | **PASSED** |
| **CHK-10** | Cascade Root Disruption Validity | Every cascade points to a valid disruption | 0 orphan cascade trees | **PASSED** |
| **CHK-11** | Cascade Tree Parent-Child Lineage | Every propagated event points to valid parent | 0 orphan child nodes | **PASSED** |
| **CHK-12** | Cascading Shipment Ratio | Target 10%–20% of network shipments | 15.0% (2100 shipments) | **PASSED** |
| **CHK-13** | On-Time vs Delayed Ratio | Target 55%–65% on-time shipments | 61.5% on-time, 38.5% delayed | **PASSED** |
| **CHK-14** | ML Target Logical Grounding | Zero target leakage, grounded in causal ground truth | 100% grounded labels | **PASSED** |

---

## 2. Table Volume & Entity Counts

| Table Name | File Path | Record Count (Full) | Record Count (Sample) | Primary Key | Description |
|---|---|---|---|---|---|
| `shipments` | `data/shipments.csv` | 14,000 | 250 | `shipment_id` | Core shipment records with origin, destination, vehicle, planned/actual times, delays, and ML targets |
| `logistics_events` | `data/logistics_events.csv` | 77,063 | 1,380 | `event_id` | Chronological operational scans (Entry, Loading, Departure, Inspection, Arrival, Unloading) |
| `locations` | `data/locations.csv` | 28 | 28 | `location_id` | 28 Indian hubs (FC, DC, Cross-Dock, Regional Warehouse, Transport Hub) across 5 regions |
| `vehicles` | `data/vehicles.csv` | 650 | 208 | `vehicle_id` | 650 transport vehicles across 6 carriers with capacities, speeds, and reliability scores |
| `delay_reasons` | `data/delay_reasons.csv` | 20 | 20 | `delay_reason_id` | 20 standardized operational, transport, warehouse, and external delay reasons |
| `dependencies` | `data/dependencies.csv` | 10,000 | 45 | `dependency_id` | Upstream-to-downstream relationships (Transfers, Shared Vehicles, Cross-Docks, Connections) |
| `disruptions` | `data/disruptions.csv` | 720 | 20 | `disruption_id` | Root-cause external/internal incidents (Breakdowns, Congestion, Weather, Sorter Failures) |
| `cascade_events` | `data/cascade_events.csv` | 6,300 | 180 | `cascade_id + affected_shipment_id + propagation_type` | Ground-truth causal propagation tree tracing delay depth from Level 0 to Level 3+ |
| `deliveries` | `data/deliveries.csv` | 14,000 | 250 | `delivery_id` | Final customer delivery SLA tracking with risk flags and human-readable risk attribution |

---

## 3. Operational & Causal Distribution Metrics

### Delay Status Distribution
- **On-Time (0–15 min delay):** 8,608 (61.5%)
- **Minor Delay (16–60 min delay):** 4,017 (28.7%)
- **Moderate Delay (61–180 min delay):** 1,126 (8.0%)
- **Severe Delay (>180 min delay):** 249 (1.8%)

### Delay Origin & Propagation Types
- **Isolated Delays:** 3,500 shipments (25.0% - local operational variance, no downstream cascade)
- **Cascading Delays:** 2,100 shipments (15.0% - participating in causal trees across 6 distinct propagation patterns)
  - Level 0 (Root Cause): 720 shipments
  - Level 1 (First Downstream Generation): 1,018 shipments
  - Level 2 (Second Downstream Generation): 289 shipments
  - Level 3 (Third Downstream Generation): 73 shipments

### Delivery SLA Performance
- **Delivered On Time:** 9,066 (64.8%)
- **Delivered Late:** 4,933 (35.2%)
- **At Risk:** 0 (0.0%)
- **Failed Delivery:** 1 (0.0%)

---

## 4. Integrity Verification Code Snippet

To verify all foreign keys and temporal integrity independently:

```python
import pandas as pd

shipments = pd.read_csv("cascading-delay-dataset/data/shipments.csv")
events = pd.read_csv("cascading-delay-dataset/data/logistics_events.csv")
deps = pd.read_csv("cascading-delay-dataset/data/dependencies.csv")
cascades = pd.read_csv("cascading-delay-dataset/data/cascade_events.csv")

# 1. Zero orphan dependencies
assert set(deps["upstream_shipment_id"]).issubset(set(shipments["shipment_id"]))
assert set(deps["downstream_shipment_id"]).issubset(set(shipments["shipment_id"]))

# 2. Zero temporal violations
assert (pd.to_datetime(shipments["actual_arrival"]) >= pd.to_datetime(shipments["actual_departure"])).all()

# 3. Delays exactly match timestamp differences
calc_delays = (pd.to_datetime(shipments["actual_arrival"]) - pd.to_datetime(shipments["planned_arrival"])).dt.total_seconds() / 60.0
assert (calc_delays.clip(lower=0).round().astype(int) == shipments["final_delay_minutes"]).all()

print("All integrity assertions verified successfully!")
```
