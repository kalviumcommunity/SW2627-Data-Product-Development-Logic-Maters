# Actual Dataset Schema & Column Specification

This document details the **actual schema, types, nullability, unique counts, and sample values** of the 9 relational CSV files in `cascading-delay-dataset/data/`.

---

## 1. `shipments.csv` (14,000 rows, 24 columns)

Represents each consignment journey through origin-destination legs.

| Column | Actual Dtype | Null Count | Unique Count | Sample Value | Role / Semantics |
|---|---|---|---|---|---|
| `shipment_id` | `object` (str) | 0 | 14,000 | `SHP-00001` | **Primary Key** |
| `order_id` | `object` (str) | 0 | 14,000 | `ORD-00001` | **Foreign Key** to `deliveries.order_id` (1:1) |
| `origin_location_id` | `object` (str) | 0 | 28 | `LOC-PNQ-01` | **Foreign Key** to `locations.location_id` |
| `destination_location_id` | `object` (str) | 0 | 28 | `LOC-STV-01` | **Foreign Key** to `locations.location_id` |
| `assigned_vehicle_id` | `object` (str) | 0 | 650 | `VEH-1361` | **Foreign Key** to `vehicles.vehicle_id` |
| `priority` | `object` (str) | 0 | 3 | `Standard` | Priority tier: `Standard`, `Express`, `Critical` |
| `cargo_type` | `object` (str) | 0 | 7 | `Pharmaceuticals` | `Electronics`, `Pharmaceuticals`, `Automotive Parts`, `Perishables`, `Apparel`, `FMCG`, `Industrial Equipment` |
| `quantity` | `int64` | 0 | 874 | `185` | Manifest carton / pallet count |
| `weight_kg` | `float64` | 0 | 13,015 | `9085.2` | Gross payload weight |
| `planned_departure` | `object` (ts) | 0 | 1,116 | `2026-08-16 10:00:00` | Scheduled departure timestamp |
| `actual_departure` | `object` (ts) | 0 | 6,739 | `2026-08-16 10:00:00` | Actual gate-out departure timestamp |
| `planned_arrival` | `object` (ts) | 0 | 11,996 | `2026-08-16 20:32:00` | Scheduled destination arrival timestamp |
| `actual_arrival` | `object` (ts) | 0 | 12,068 | `2026-08-16 20:32:00` | Actual gate-in docking timestamp |
| `status` | `object` (str) | 0 | 3 | `Delivered` | `Delivered`, `Delivered Late`, `Delayed` |
| `initial_delay_minutes` | `int64` | 0 | 257 | `0` | Departure lateness in minutes |
| `final_delay_minutes` | `int64` | 0 | 264 | `0` | Arrival lateness in minutes |
| `delay_status` | `object` (str) | 0 | 4 | `On-Time` | `On-Time`, `Minor Delay`, `Moderate Delay`, `Severe Delay` |
| `created_at` | `object` (ts) | 0 | 3,000 | `2026-08-15 07:00:00` | Consignment booking timestamp |
| `will_be_delayed` | `int64` | 0 | 2 | `0` | **ML Target**: 1 if `final_delay_minutes > 15` |
| `will_cascade` | `int64` | 0 | 2 | `0` | **ML Target**: 1 if delay propagated to downstream handovers |
| `delivery_at_risk` | `int64` | 0 | 2 | `0` | **ML Target**: 1 if delivery SLA breached or at risk |
| `root_cause_category` | `object` (str) | 8,400 | 5 | `Warehouse` | Root cause category (null for on-time shipments) |
| `cascade_severity` | `object` (str) | 8,400 | 5 | `Low` | Severity rating: `None`, `Low`, `Medium`, `Major`, `Critical` |
| `cascade_level` | `int64` | 0 | 5 | `-1` | Echelon level: `-1` (non-cascade), `0` (root), `1`, `2`, `3` |

---

## 2. `logistics_events.csv` (77,063 rows, 11 columns)

Detailed chronological operational scan events for every shipment.

| Column | Actual Dtype | Null Count | Unique Count | Sample Value | Role / Semantics |
|---|---|---|---|---|---|
| `event_id` | `object` (str) | 0 | 77,063 | `EVT-0000001` | **Primary Key** |
| `shipment_id` | `object` (str) | 0 | 14,000 | `SHP-00001` | **Foreign Key** to `shipments.shipment_id` |
| `location_id` | `object` (str) | 0 | 28 | `LOC-PNQ-01` | **Foreign Key** to `locations.location_id` |
| `vehicle_id` | `object` (str) | 0 | 650 | `VEH-1361` | **Foreign Key** to `vehicles.vehicle_id` |
| `event_type` | `object` (str) | 0 | 6 | `Warehouse Entry` | Scan milestone: `Warehouse Entry`, `Loading`, `Departure`, `Inspection`, `Arrival`, `Unloading` |
| `scheduled_timestamp` | `object` (ts) | 0 | 35,924 | `2026-08-16 08:19:00` | Planned milestone time |
| `actual_timestamp` | `object` (ts) | 0 | 37,452 | `2026-08-16 08:19:00` | Actual scan time |
| `delay_minutes` | `int64` | 0 | 287 | `0` | Delay at this milestone |
| `delay_reason_id` | `object` (str) | 58,566 | 10 | `RSN-02` | **Foreign Key** to `delay_reasons.delay_reason_id` (null if on-time) |
| `event_status` | `object` (str) | 0 | 2 | `Completed` | Milestone status: `Completed`, `Delayed` |
| `notes` | `object` (str) | 0 | 709 | `Consignment arrived...` | Telematics / scan observation |

---

## 3. `locations.csv` (28 rows, 11 columns)

Network facilities across India.

| Column | Actual Dtype | Null Count | Unique Count | Sample Value | Role / Semantics |
|---|---|---|---|---|---|
| `location_id` | `object` (str) | 0 | 28 | `LOC-DEL-01` | **Primary Key** |
| `location_name` | `object` (str) | 0 | 28 | `Delhi Central Fulfillment Center` | Facility name |
| `location_type` | `object` (str) | 0 | 5 | `Fulfillment Centers` | `Fulfillment Centers`, `Distribution Centers`, `Regional Warehouses`, `Cross-Docking Hubs`, `Transport Hubs` |
| `city` | `object` (str) | 0 | 18 | `Delhi` | City |
| `state` | `object` (str) | 0 | 12 | `Delhi` | State |
| `region` | `object` (str) | 0 | 5 | `North` | Region: `North`, `West`, `South`, `East`, `Central` |
| `latitude` | `float64` | 0 | 27 | `28.6139` | Decimal latitude |
| `longitude` | `float64` | 0 | 28 | `77.209` | Decimal longitude |
| `capacity` | `int64` | 0 | 16 | `45000` | Facility handling volume limit |
| `operating_hours` | `object` (str) | 0 | 3 | `24/7` | `24/7`, `06:00-22:00`, `06:00-23:00` |
| `average_processing_time_minutes` | `int64` | 0 | 7 | `60` | Nominal processing duration |

---

## 4. `vehicles.csv` (650 rows, 8 columns)

Fleet transport assets.

| Column | Actual Dtype | Null Count | Unique Count | Sample Value | Role / Semantics |
|---|---|---|---|---|---|
| `vehicle_id` | `object` (str) | 0 | 650 | `VEH-1001` | **Primary Key** |
| `vehicle_type` | `object` (str) | 0 | 5 | `Mini Truck` | `Van`, `Mini Truck`, `Truck`, `Refrigerated Truck`, `Container Truck` |
| `capacity_kg` | `int64` | 0 | 5 | `3500` | Maximum payload capacity |
| `carrier` | `object` (str) | 0 | 6 | `TCI Freight` | Carrier company |
| `home_location_id` | `object` (str) | 0 | 28 | `LOC-NOI-01` | **Foreign Key** to `locations.location_id` |
| `reliability_score` | `float64` | 0 | 15 | `0.85` | Fleet asset reliability index |
| `average_speed_kmph` | `float64` | 0 | 168 | `46.7` | Highway speed benchmark |
| `status` | `object` (str) | 0 | 4 | `Assigned` | Operational status: `Available`, `In Transit`, `Assigned`, `Maintenance` |

---

## 5. `delay_reasons.csv` (20 rows, 5 columns)

Taxonomy of operational root causes.

| Column | Actual Dtype | Null Count | Unique Count | Sample Value | Role / Semantics |
|---|---|---|---|---|---|
| `delay_reason_id` | `object` (str) | 0 | 20 | `RSN-01` | **Primary Key** |
| `reason_category` | `object` (str) | 0 | 5 | `Transportation` | `Transportation`, `Warehouse`, `External`, `Operational`, `Documentation` |
| `reason_name` | `object` (str) | 0 | 20 | `Vehicle Breakdown` | Standard title |
| `description` | `object` (str) | 0 | 20 | `Mechanical engine failure...` | Detailed failure explanation |
| `severity` | `object` (str) | 0 | 4 | `Major` | `Minor`, `Moderate`, `Major`, `Critical` |

---

## 6. `dependencies.csv` (10,000 rows, 11 columns)

The causal fabric connecting upstream and downstream operations.

| Column | Actual Dtype | Null Count | Unique Count | Sample Value | Role / Semantics |
|---|---|---|---|---|---|
| `dependency_id` | `object` (str) | 0 | 10,000 | `DEP-000001` | **Primary Key** |
| `upstream_shipment_id` | `object` (str) | 0 | 4,621 | `SHP-11910` | **Foreign Key** to `shipments.shipment_id` |
| `downstream_shipment_id` | `object` (str) | 0 | 4,888 | `SHP-06422` | **Foreign Key** to `shipments.shipment_id` |
| `upstream_location_id` | `object` (str) | 0 | 28 | `LOC-DEL-02` | **Foreign Key** to `locations.location_id` |
| `downstream_location_id` | `object` (str) | 0 | 28 | `LOC-DEL-02` | **Foreign Key** to `locations.location_id` |
| `dependency_type` | `object` (str) | 0 | 7 | `Cross-Dock Transfer` | `Waiting for Inbound Shipment`, `Warehouse Transfer`, `Cross-Dock Transfer`, `Shared Vehicle`, `Route Connection`, `Shared Warehouse Capacity`, `Shared Vehicle Handover` |
| `planned_dependency_time` | `object` (ts) | 0 | 4,381 | `2026-08-25 22:54:00` | Scheduled connection window |
| `actual_dependency_time` | `object` (ts) | 0 | 4,364 | `2026-08-26 01:19:00` | Actual connection completion |
| `dependency_delay_minutes` | `int64` | 0 | 186 | `16` | Delay passed to downstream |
| `dependency_status` | `object` (str) | 0 | 3 | `Delayed - Propagated` | `Delayed - Propagated`, `Delayed - Absorbed`, `Resolved On-Time` |
| `cascade_id` | `object` (str) | 8,620 | 720 | `CAS-0001` | **Foreign Key** to `cascade_events.cascade_id` (null if regular non-cascade transfer) |

---

## 7. `disruptions.csv` (720 rows, 10 columns)

Original root cause events that initiate delays.

| Column | Actual Dtype | Null Count | Unique Count | Sample Value | Role / Semantics |
|---|---|---|---|---|---|
| `disruption_id` | `object` (str) | 0 | 720 | `DIS-0001` | **Primary Key** |
| `disruption_type` | `object` (str) | 0 | 7 | `State Border Checkpoint Hold` | `Vehicle Breakdown`, `Warehouse Congestion`, `Road Closure`, `Severe Weather`, `Equipment Failure`, `Labor Shortage`, `State Border Checkpoint Hold` |
| `location_id` | `object` (str) | 0 | 28 | `LOC-MAA-01` | **Foreign Key** to `locations.location_id` |
| `vehicle_id` | `object` (str) | 510 | 178 | `VEH-1162` | **Foreign Key** to `vehicles.vehicle_id` (null if fixed warehouse disruption) |
| `start_time` | `object` (ts) | 0 | 712 | `2026-08-23 17:56:00` | Incident start |
| `end_time` | `object` (ts) | 0 | 710 | `2026-08-23 20:45:00` | Incident resolution |
| `severity` | `object` (str) | 0 | 3 | `Major` | `Moderate`, `Major`, `Critical` |
| `description` | `object` (str) | 0 | 28 | `State boundary regulatory...` | Incident narrative |
| `root_cause` | `object` (str) | 0 | 7 | `State Border Checkpoint Hold` | High-level cause |
| `affected_capacity_percentage` | `float64` | 0 | 406 | `50.0` | Facility / lane degradation percentage |

---

## 8. `cascade_events.csv` (6,300 rows, 14 columns)

Ground-truth causal trees tracking how delays propagate from Level 0 to Level 3+.

| Column | Actual Dtype | Null Count | Unique Count | Sample Value | Role / Semantics |
|---|---|---|---|---|---|
| `cascade_id` | `object` (str) | 0 | 720 | `CAS-0001` | **Foreign Key** to cascade tree identifier |
| `disruption_id` | `object` (str) | 0 | 720 | `DIS-0001` | **Foreign Key** to `disruptions.disruption_id` |
| `root_shipment_id` | `object` (str) | 0 | 720 | `SHP-11910` | **Foreign Key** to `shipments.shipment_id` |
| `affected_shipment_id` | `object` (str) | 0 | 2,100 | `SHP-11910` | **Foreign Key** to `shipments.shipment_id` |
| `parent_shipment_id` | `object` (str) | 2,160 | 720 | `SHP-11910` | **Foreign Key** to upstream `shipment_id` (null if root) |
| `cascade_level` | `int64` | 0 | 4 | `0` | Depth: `0` (root), `1`, `2`, `3` |
| `propagation_type` | `object` (str) | 0 | 9 | `Root Disruption` | Step type: `Root Disruption`, `Departure Delay`, `Customer Delivery Risk`, `Waiting for Inbound Shipment`, `Warehouse Transfer`, `Cross-Dock Transfer`, `Route Connection`, `Shared Vehicle Turnaround`, `Warehouse Congestion Transfer` |
| `direct_delay_minutes` | `int64` | 0 | 187 | `145` | Direct delay introduced at this step |
| `propagated_delay_minutes` | `int64` | 0 | 200 | `0` | Inherited delay from parent |
| `total_delay_minutes` | `int64` | 0 | 252 | `145` | Total delay experienced at this node |
| `root_cause` | `object` (str) | 0 | 7 | `State Border Checkpoint Hold` | Root disruption cause |
| `is_root_cause` | `bool` | 0 | 2 | `True` | True if level 0 |
| `is_propagated` | `bool` | 0 | 2 | `False` | True if level > 0 |
| `impact_status` | `object` (str) | 0 | 3 | `Active Cascade` | `Active Cascade`, `Partially Absorbed`, `Severe Delay Breached` |

*Composite Unique Key:* `(cascade_id, affected_shipment_id, propagation_type)`

---

## 9. `deliveries.csv` (14,000 rows, 10 columns)

Customer SLA commitments and delivery outcomes.

| Column | Actual Dtype | Null Count | Unique Count | Sample Value | Role / Semantics |
|---|---|---|---|---|---|
| `delivery_id` | `object` (str) | 0 | 14,000 | `DEL-00001` | **Primary Key** |
| `order_id` | `object` (str) | 0 | 14,000 | `ORD-00001` | **Foreign Key** to `shipments.order_id` |
| `shipment_id` | `object` (str) | 0 | 14,000 | `SHP-00001` | **Foreign Key** to `shipments.shipment_id` |
| `destination_location_id` | `object` (str) | 0 | 28 | `LOC-STV-01` | **Foreign Key** to `locations.location_id` |
| `promised_delivery_time` | `object` (ts) | 0 | 12,048 | `2026-08-16 22:32:00` | Promised customer SLA deadline |
| `actual_delivery_time` | `object` (ts) | 0 | 12,060 | `2026-08-16 21:39:00` | Doorstep delivery timestamp |
| `delivery_status` | `object` (str) | 0 | 3 | `Delivered On Time` | `Delivered On Time`, `Delivered Late`, `At Risk` |
| `delay_minutes` | `int64` | 0 | 248 | `0` | Delay past promised SLA in minutes |
| `at_risk` | `bool` | 0 | 2 | `False` | SLA risk flag |
| `risk_reason` | `object` (str) | 0 | 276 | `Delivered within promised...` | Human-readable explanation |
