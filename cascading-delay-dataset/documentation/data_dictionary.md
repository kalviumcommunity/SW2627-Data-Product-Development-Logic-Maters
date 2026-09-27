# Cascading Delay Intelligence - Data Dictionary

This document provides a comprehensive specification for every table and column in the **Cascading Delay Intelligence** dataset.

---

## 1. Table: `shipments.csv`

**Description:** Represents every freight shipment moving through the intercity and hub logistics network. Contains scheduling, actual operational timestamps, delay metrics, and machine learning ground-truth target variables.

| Column Name | Data Type | Unit / Format | Description / Meaning | Calculated From / Source | Example Values |
|---|---|---|---|---|---|
| `shipment_id` | String (PK) | Text (`SHP-XXXXX`) | Unique identifier for the consignment moving through the network. | Generated sequential identifier | `SHP-00001`, `SHP-04724` |
| `order_id` | String (FK) | Text (`ORD-XXXXX`) | Associated customer order identifier. | Generated sequential order link | `ORD-00001`, `ORD-04724` |
| `origin_location_id` | String (FK) | Text (`LOC-XXX-XX`) | Origin hub, fulfillment center, or warehouse. | References `locations.location_id` | `LOC-DEL-01`, `LOC-HYD-01` |
| `destination_location_id` | String (FK) | Text (`LOC-XXX-XX`) | Destination hub, fulfillment center, or warehouse. | References `locations.location_id` | `LOC-BOM-01`, `LOC-IDR-01` |
| `assigned_vehicle_id` | String (FK) | Text (`VEH-XXXX`) | Transport vehicle assigned to execute this shipment leg. | References `vehicles.vehicle_id` | `VEH-1025`, `VEH-1162` |
| `priority` | String | Categorical | Priority level governing dispatch precedence and SLA tightness. | Business scheduling tier | `Standard`, `Express`, `Critical` |
| `cargo_type` | String | Categorical | Classification of goods transported. | Consignment manifest | `Electronics`, `Perishables`, `Automotive Parts` |
| `quantity` | Integer | Units (Cartons/Pallets) | Number of packages/pallets in the consignment. | Manifest package count | `24`, `150`, `380` |
| `weight_kg` | Float | Kilograms (kg) | Total gross freight weight. | Physical scale reading | `1250.5`, `8400.0`, `18250.0` |
| `planned_departure` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Scheduled departure timestamp from origin location. | Dispatch schedule | `2026-08-19 16:45:00` |
| `actual_departure` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Actual gate-out timestamp from origin location. | In-transit scan / gate pass | `2026-08-19 20:01:00` |
| `planned_arrival` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Scheduled arrival timestamp at destination location. | Transit schedule model | `2026-08-20 11:33:00` |
| `actual_arrival` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Actual gate-in timestamp at destination location. | Gate arrival scan | `2026-08-20 14:56:00` |
| `status` | String | Categorical | Final lifecycle operational status of shipment. | Fleet management system | `Delivered`, `Delivered Late`, `Delayed` |
| `initial_delay_minutes` | Integer | Minutes | Delay incurred at dispatch departure. | `max(0, actual_dep - planned_dep)` | `0`, `45`, `196` |
| `final_delay_minutes` | Integer | Minutes | Total delay experienced at destination arrival. | `max(0, actual_arr - planned_arr)` | `0`, `84`, `203` |
| `delay_status` | String | Categorical | Severity tier of arrival delay. | Binned from `final_delay_minutes` | `On-Time`, `Minor Delay`, `Moderate Delay`, `Severe Delay` |
| `created_at` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Consignment booking/manifest generation timestamp. | Order management system | `2026-08-17 11:15:00` |
| `will_be_delayed` | Integer | Binary (0 or 1) | Target label: 1 if shipment arrival delay > 15 mins. | Derived ground truth | `0`, `1` |
| `will_cascade` | Integer | Binary (0 or 1) | Target label: 1 if shipment causes downstream delays in network. | Network dependency trace | `0`, `1` |
| `delivery_at_risk` | Integer | Binary (0 or 1) | Target label: 1 if downstream delivery SLA is breached or at severe risk. | Linked to `deliveries.at_risk` | `0`, `1` |
| `root_cause_category` | String | Categorical | Root cause category of delay if delayed. | Traceability engine | `Transportation`, `Warehouse`, `External`, `Operational`, `Documentation`, `None` |
| `cascade_severity` | String | Categorical | Severity level of cascading impact. | Propagation impact | `None`, `Low`, `Medium`, `Major`, `Critical` |
| `cascade_level` | Integer | Index (-1, 0, 1, 2, 3+) | Position in the causal propagation hierarchy (-1 = non-cascading, 0 = root cause, 1+ = propagated). | Causal graph hierarchy | `-1`, `0`, `1`, `2`, `3` |

---

## 2. Table: `logistics_events.csv`

**Description:** Represents the detailed, chronological milestone scans that occur during consignment handling, transit, and sortation.

| Column Name | Data Type | Unit / Format | Description / Meaning | Calculated From / Source | Example Values |
|---|---|---|---|---|---|
| `event_id` | String (PK) | Text (`EVT-XXXXXXX`) | Unique operational scan record identifier. | Scanning terminal / RFID scanner | `EVT-0000001`, `EVT-0045120` |
| `shipment_id` | String (FK) | Text (`SHP-XXXXX`) | Shipment associated with this event. | References `shipments.shipment_id` | `SHP-00001`, `SHP-04724` |
| `location_id` | String (FK) | Text (`LOC-XXX-XX`) | Facility where event scan took place. | References `locations.location_id` | `LOC-DEL-01`, `LOC-BOM-01` |
| `vehicle_id` | String (FK) | Text (`VEH-XXXX`) | Vehicle carrying or assigned to the shipment at scan time. | References `vehicles.vehicle_id` | `VEH-1025`, `VEH-1162` |
| `event_type` | String | Categorical | Operational milestone type. | Milestone event definition | `Warehouse Entry`, `Loading`, `Departure`, `Inspection`, `Arrival`, `Unloading` |
| `scheduled_timestamp` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Planned timestamp for this event milestone. | Scheduling system | `2026-08-19 16:45:00` |
| `actual_timestamp` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Actual physical timestamp when milestone was logged. | Physical scan log | `2026-08-19 20:01:00` |
| `delay_minutes` | Integer | Minutes | Delay incurred specifically at this event. | `max(0, actual_ts - sched_ts)` | `0`, `18`, `196` |
| `delay_reason_id` | String (FK) | Text (`RSN-XX`) | Delay reason if event experienced delay > 15 mins. | References `delay_reasons.delay_reason_id` | `RSN-01`, `RSN-04`, `RSN-12` |
| `event_status` | String | Categorical | Execution status of milestone. | Operational execution | `Completed`, `Delayed`, `In Progress` |
| `notes` | String | Text | Operational observation or system scan note. | Warehouse management / telematics | `Consignment arrived at inbound gate`, `Vehicle departed origin bay` |

---

## 3. Table: `locations.csv`

**Description:** Represents logistics facilities including Fulfillment Centers, Regional Warehouses, Distribution Centers, Cross-Docking Hubs, and Transport Hubs across India.

| Column Name | Data Type | Unit / Format | Description / Meaning | Calculated From / Source | Example Values |
|---|---|---|---|---|---|
| `location_id` | String (PK) | Text (`LOC-XXX-XX`) | Unique identifier for facility. | Network master data | `LOC-DEL-01`, `LOC-BOM-01` |
| `location_name` | String | Text | Full commercial name of warehouse or terminal. | Master data facility directory | `Delhi Central Fulfillment Center` |
| `location_type` | String | Categorical | Operational role of the facility. | Facility specification | `Fulfillment Centers`, `Cross-Docking Hubs`, `Transport Hubs` |
| `city` | String | Text | City location in India. | Geographic division | `Delhi`, `Mumbai`, `Jaipur`, `Bengaluru` |
| `state` | String | Text | State location in India. | Geographic division | `Delhi`, `Maharashtra`, `Rajasthan`, `Karnataka` |
| `region` | String | Categorical | Geographic region within the national network. | Logistics zone | `North`, `West`, `South`, `East`, `Central` |
| `latitude` | Float | Decimal Degrees | Latitude coordinates for GIS and distance calculations. | GPS mapping | `28.6139`, `19.2967` |
| `longitude` | Float | Decimal Degrees | Longitude coordinates for GIS and distance calculations. | GPS mapping | `77.2090`, `73.0631` |
| `capacity` | Integer | Package / Pallet units | Maximum concurrent handling capacity of the facility. | Facility engineering specs | `25000`, `45000`, `55000` |
| `operating_hours` | String | Text | Shift schedule or continuous operation windows. | Operating policy | `24/7`, `06:00-22:00`, `06:00-23:00` |
| `average_processing_time_minutes` | Integer | Minutes | Baseline throughput processing time per consignment. | Historical operational benchmark | `45`, `60`, `75` |

---

## 4. Table: `vehicles.csv`

**Description:** Represents transportation assets deployed across linehaul corridors and feeder routes.

| Column Name | Data Type | Unit / Format | Description / Meaning | Calculated From / Source | Example Values |
|---|---|---|---|---|---|
| `vehicle_id` | String (PK) | Text (`VEH-XXXX`) | Unique fleet asset identifier. | Fleet asset register | `VEH-1001`, `VEH-1162` |
| `vehicle_type` | String | Categorical | Vehicle form factor and equipment capability. | Fleet asset classification | `Van`, `Mini Truck`, `Truck`, `Refrigerated Truck`, `Container Truck` |
| `capacity_kg` | Integer | Kilograms (kg) | Maximum legal payload weight. | Vehicle manufacturer rating | `1500`, `3500`, `10000`, `25000` |
| `carrier` | String | Text | Primary logistics operator / carrier running the asset. | Transport contract | `Delhivery Express`, `BlueDart Logistics`, `Safexpress` |
| `home_location_id` | String (FK) | Text (`LOC-XXX-XX`) | Maintenance base and domicile depot of the vehicle. | References `locations.location_id` | `LOC-DEL-01`, `LOC-BOM-01` |
| `reliability_score` | Float | Decimal (0.00 to 1.00) | Historical reliability score based on mechanical uptime. | Fleet maintenance analytics | `0.88`, `0.94`, `0.98` |
| `average_speed_kmph` | Float | km/h | Average cruising speed on Indian highway network. | Telematics averages | `42.5`, `48.0`, `54.2` |
| `status` | String | Categorical | Real-time vehicle operational status. | Telematics / dispatch board | `Available`, `In Transit`, `Assigned`, `Maintenance` |

---

## 5. Table: `delay_reasons.csv`

**Description:** Standardized industry taxonomy of logistics delays, categorized by organizational failure mode and severity.

| Column Name | Data Type | Unit / Format | Description / Meaning | Calculated From / Source | Example Values |
|---|---|---|---|---|---|
| `delay_reason_id` | String (PK) | Text (`RSN-XX`) | Unique standardized delay code. | Operational taxonomy | `RSN-01`, `RSN-04`, `RSN-14` |
| `reason_category` | String | Categorical | High-level organizational cause category. | Taxonomy classification | `Transportation`, `Warehouse`, `External`, `Operational`, `Documentation` |
| `reason_name` | String | Text | Common operational name of the delay event. | Standard naming | `Vehicle Breakdown`, `Warehouse Congestion`, `Severe Weather` |
| `description` | String | Text | Detailed explanation of root cause mechanics. | SOP incident documentation | `Mechanical engine failure, tire blowout, or electrical failure during transit` |
| `severity` | String | Categorical | Operational severity rating. | Risk assessment tier | `Minor`, `Moderate`, `Major`, `Critical` |

---

## 6. Table: `dependencies.csv`

**Description:** The causal backbone of the dataset. Explicitly models handovers, connections, and shared resources between upstream and downstream shipments.

| Column Name | Data Type | Unit / Format | Description / Meaning | Calculated From / Source | Example Values |
|---|---|---|---|---|---|
| `dependency_id` | String (PK) | Text (`DEP-XXXXXX`) | Unique dependency relationship record identifier. | Relationship generator | `DEP-000001`, `DEP-001254` |
| `upstream_shipment_id` | String (FK) | Text (`SHP-XXXXX`) | Preceding shipment providing freight, vehicle, or trigger. | References `shipments.shipment_id` | `SHP-04724`, `SHP-06805` |
| `downstream_shipment_id` | String (FK) | Text (`SHP-XXXXX`) | Succeeding shipment waiting for feeder freight, vehicle, or dock. | References `shipments.shipment_id` | `SHP-12985`, `SHP-03399` |
| `upstream_location_id` | String (FK) | Text (`LOC-XXX-XX`) | Facility where upstream shipment finishes its transfer leg. | References `locations.location_id` | `LOC-IDR-01`, `LOC-AMD-01` |
| `downstream_location_id` | String (FK) | Text (`LOC-XXX-XX`) | Facility where downstream shipment departs with transferred freight. | References `locations.location_id` | `LOC-IDR-01`, `LOC-AMD-01` |
| `dependency_type` | String | Categorical | Physical or operational nature of the dependency. | Relationship classification | `Waiting for Inbound Shipment`, `Warehouse Transfer`, `Cross-Dock Transfer`, `Shared Vehicle`, `Shared Warehouse Capacity` |
| `planned_dependency_time` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Scheduled handover or meeting timestamp. | Operating plan | `2026-08-20 11:33:00` |
| `actual_dependency_time` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Actual time handover occurred. | Upstream actual arrival | `2026-08-20 14:56:00` |
| `dependency_delay_minutes` | Integer | Minutes | Delay transmitted to the downstream departure. | `max(0, act_time - planned_dep_downstream)` | `0`, `45`, `162` |
| `dependency_status` | String | Categorical | Whether delay propagated, was absorbed by buffer, or resolved on time. | Operational outcome | `Resolved On-Time`, `Delayed - Propagated`, `Delayed - Absorbed` |
| `cascade_id` | String (FK) | Text (`CAS-XXXX` or empty) | Associated cascade tree identifier if part of an active propagation. | References `cascade_events.cascade_id` | `CAS-0003`, `CAS-0004`, empty string |

---

## 7. Table: `disruptions.csv`

**Description:** Represents root-cause incidents (internal equipment failures, highway blockages, weather storms, labor strikes) that initiate delay chains.

| Column Name | Data Type | Unit / Format | Description / Meaning | Calculated From / Source | Example Values |
|---|---|---|---|---|---|
| `disruption_id` | String (PK) | Text (`DIS-XXXX`) | Unique disruption incident identifier. | Incident logging system | `DIS-0001`, `DIS-0003` |
| `disruption_type` | String | Categorical | Incident type classification. | Standard disruption types | `Vehicle Breakdown`, `Warehouse Congestion`, `Road Closure`, `Severe Weather` |
| `location_id` | String (FK) | Text (`LOC-XXX-XX`) | Facility or hub where disruption initiated. | References `locations.location_id` | `LOC-DEL-01`, `LOC-HYD-01` |
| `vehicle_id` | String (FK) | Text (`VEH-XXXX` or empty) | Vehicle involved if disruption was transport/mechanical. | References `vehicles.vehicle_id` | `VEH-1162`, empty string |
| `start_time` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Start timestamp of disruption incident. | Incident log | `2026-08-19 16:24:00` |
| `end_time` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Clearance / resolution timestamp of disruption. | Incident log | `2026-08-19 20:12:00` |
| `severity` | String | Categorical | Disruption impact severity level. | Incident rating | `Moderate`, `Major`, `Critical` |
| `description` | String | Text | Operational description of the failure event. | Incident log details | `Radiator burst and cooling system leak` |
| `root_cause` | String | Text | Primary causal classification name. | Root cause analysis | `Vehicle Breakdown`, `Warehouse Congestion` |
| `affected_capacity_percentage` | Float | Percentage (%) | Estimated reduction in local handling or lane capacity. | Facility monitoring | `35.0%`, `68.5%`, `80.0%` |

---

## 8. Table: `cascade_events.csv`

**Description:** Ground-truth causal tree tracking how delays propagate from root disruptions through successive tiers of downstream shipments.

| Column Name | Data Type | Unit / Format | Description / Meaning | Calculated From / Source | Example Values |
|---|---|---|---|---|---|
| `cascade_id` | String (FK) | Text (`CAS-XXXX`) | Causal cascade sequence identifier. | Propagation tree identifier | `CAS-0001`, `CAS-0003` |
| `disruption_id` | String (FK) | Text (`DIS-XXXX`) | Root disruption initiating this cascade. | References `disruptions.disruption_id` | `DIS-0001`, `DIS-0003` |
| `root_shipment_id` | String (FK) | Text (`SHP-XXXXX`) | First shipment directly impacted by the root disruption. | References `shipments.shipment_id` | `SHP-04724`, `SHP-06805` |
| `affected_shipment_id` | String (FK) | Text (`SHP-XXXXX`) | Shipment currently affected at this node of the cascade. | References `shipments.shipment_id` | `SHP-04724`, `SHP-12985` |
| `parent_shipment_id` | String (FK) | Text (`SHP-XXXXX` or empty) | Preceding shipment that directly transmitted the delay. | Empty for level 0; otherwise upstream shipment ID | `SHP-04724`, empty string |
| `cascade_level` | Integer | Index (0, 1, 2, 3+) | Echelon depth (0 = root cause, 1 = first downstream tier, 2 = second tier, 3+ = deep propagation). | Graph depth | `0`, `1`, `2`, `3` |
| `propagation_type` | String | Categorical | Specific mechanism transmitting the delay. | Propagation classification | `Root Disruption`, `Waiting for Inbound Shipment`, `Departure Delay`, `Customer Delivery Risk`, `Warehouse Transfer` |
| `direct_delay_minutes` | Integer | Minutes | Delay injected locally at this node. | Local delay component | `0`, `10`, `196` |
| `propagated_delay_minutes` | Integer | Minutes | Delay inherited from upstream parent minus buffer. | Upstream transmitted delay | `0`, `157`, `162` |
| `total_delay_minutes` | Integer | Minutes | Total arrival delay suffered by this affected shipment. | `direct + propagated` | `98`, `157`, `203` |
| `root_cause` | String | Text | Original root cause that started the chain. | Propagated root cause name | `Vehicle Breakdown`, `Warehouse Congestion` |
| `is_root_cause` | Boolean | True / False | Flag indicating if this record represents the root cause node. | `cascade_level == 0` | `True`, `False` |
| `is_propagated` | Boolean | True / False | Flag indicating if this record represents downstream propagation. | `cascade_level > 0` | `False`, `True` |
| `impact_status` | String | Categorical | Current containment or breach status. | Impact tracking | `Active Cascade`, `Partially Absorbed`, `Severe Delay Breached` |

---

## 9. Table: `deliveries.csv`

**Description:** Tracks final customer deliveries and contractual Service Level Agreements (SLAs).

| Column Name | Data Type | Unit / Format | Description / Meaning | Calculated From / Source | Example Values |
|---|---|---|---|---|---|
| `delivery_id` | String (PK) | Text (`DEL-XXXXX`) | Unique customer delivery task identifier. | Final-mile delivery system | `DEL-00001`, `DEL-04724` |
| `order_id` | String (FK) | Text (`ORD-XXXXX`) | Customer order reference. | References `shipments.order_id` | `ORD-00001`, `ORD-04724` |
| `shipment_id` | String (FK) | Text (`SHP-XXXXX`) | Linehaul / hub shipment fulfilling this delivery. | References `shipments.shipment_id` | `SHP-00001`, `SHP-04724` |
| `destination_location_id` | String (FK) | Text (`LOC-XXX-XX`) | Final destination delivery depot. | References `locations.location_id` | `LOC-BOM-01`, `LOC-IDR-01` |
| `promised_delivery_time` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Customer promised SLA delivery deadline. | `planned_arrival + SLA buffer` | `2026-08-20 12:33:00` |
| `actual_delivery_time` | Datetime | ISO (`YYYY-MM-DD HH:MM:SS`) | Actual doorstep or customer bay delivery timestamp. | `actual_arrival + last_mile_transit` | `2026-08-20 15:29:00` |
| `delivery_status` | String | Categorical | Final customer delivery outcome. | SLA evaluation | `Delivered On Time`, `Delivered Late`, `At Risk`, `Failed Delivery` |
| `delay_minutes` | Integer | Minutes | Lateness against promised customer SLA. | `max(0, actual_deliv - promised_deliv)` | `0`, `44`, `176` |
| `at_risk` | Boolean | True / False | Binary flag indicating whether delivery breached or endangered SLA. | Business threshold (`delay > 45m` or high priority) | `False`, `True` |
| `risk_reason` | String | Text | Plain-English explanation attributing root cause or operational reason. | Root cause attribution engine | `Late delivery: Root disruption delay of 196 min at origin hub.` |
