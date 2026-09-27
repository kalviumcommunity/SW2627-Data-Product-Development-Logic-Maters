# Cascading Delay Intelligence - Dataset Overview

## 1. Executive Summary

The **Cascading Delay Intelligence** dataset is an enterprise-grade synthetic logistics dataset explicitly engineered to detect, explain, trace, and predict **cascading delays** across an intercity supply chain and freight distribution network.

In traditional logistics datasets, delays are treated as isolated events or assigned randomly to records. In reality, modern supply chains are tightly coupled networks: a 2-hour engine breakdown on a feeder truck from Delhi to Jaipur does not merely delay one truck—it starves a cross-dock sorting bay in Jaipur, delays 3 regional distribution vans departing for Jodhpur, Kota, and Ajmer, causes a scheduled linehaul transfer to miss its connecting window, and triggers late customer SLA breaches hundreds of kilometers downstream.

This dataset solves this fundamental modeling gap by providing **relational, causally linked ground truth**. Every delay can be traced along a verified chain:

$$\text{Root Disruption} \longrightarrow \text{Initial Delay} \longrightarrow \text{Dependency Transfer} \longrightarrow \text{Propagation} \longrightarrow \text{Downstream Impact} \longrightarrow \text{Delivery SLA Risk}$$

---

## 2. Core Operational Entities

To analyze supply chain delay physics, the dataset models five fundamental operational entities:

### A. What is a Shipment?
A **shipment** (`shipments.csv`) represents a discrete movement of cargo between an origin facility and a destination facility. Each shipment is assigned a specific vehicle, carries a declared weight and quantity of goods (e.g., Electronics, Pharmaceuticals, Perishables), and follows an official operating plan defined by `planned_departure` and `planned_arrival`. When disruptions occur, its actual execution (`actual_departure`, `actual_arrival`) deviates from the plan, producing initial and final delays.

### B. What is a Logistics Event?
A **logistics event** (`logistics_events.csv`) represents a physical, timestamped operational scan recorded during the shipment’s journey. These include:
- `Warehouse Entry`: Arrival at facility staging gates.
- `Loading`: Consignment palletization and loading into the vehicle cargo hold.
- `Departure`: Seal verification and physical gate-out dispatch.
- `Inspection`: FASTag, e-way bill, or border checkpoint verification en-route.
- `Arrival`: Gate-in docking at the destination hub.
- `Unloading`: De-palletization and inbound cargo reconciliation.

All events for every shipment are **strictly chronologically ordered** ($t_1 \le t_2 \le \dots \le t_n$). If an operational failure occurs during loading or transit, the exact event captures the delay and links directly to a standardized `delay_reason_id`.

### C. What is a Dependency?
A **dependency** (`dependencies.csv`) represents an operational constraint linking two distinct shipments ($S_{\text{upstream}} \to S_{\text{downstream}}$). 

Logistics dependencies arise naturally from physical constraints:
1. **Waiting for Inbound Shipment:** Feeder shipment $S_1$ carries cargo that must be cross-docked into outgoing linehaul shipment $S_2$.
2. **Warehouse Transfer:** Inbound shipment $S_1$ must be sorted and staged before local distribution shipment $S_2$ can be dispatched.
3. **Shared Vehicle:** A single vehicle completes shipment $S_1$, undergoes inspection/cleaning, and is immediately scheduled to haul shipment $S_2$.
4. **Route Connection:** Multi-leg transit connections where missing a connection window delays the next departure leg.
5. **Shared Warehouse Capacity:** Inbound volume surges saturate facility dock bays, bottlenecking outbound dispatch bays.

Dependencies also demonstrate **buffer absorption**: if an upstream shipment is delayed by 30 minutes, but the planned connection buffer is 60 minutes, the downstream shipment departs on time. The delay is marked as `Delayed - Absorbed`, providing essential counterfactual training data for machine learning.

### D. What is a Disruption?
A **disruption** (`disruptions.csv`) represents the root-cause operational or external shock introduced into the logistics network. Disruptions model real-world incidents such as:
- Mechanical vehicle breakdown (radiator burst, transmission failure).
- Warehouse congestion (dock yard gridlock, automated sorter failure).
- Route disruptions (national highway construction closures, bridge repairs).
- Extreme weather (monsoon flash floods, cyclonic gale winds, dense fog).
- Labor strikes or seasonal absenteeism.
- Regulatory checkpoint holds (commercial tax audits, FASTag server downtime).

Each disruption defines the exact incident start/end times, location, affected vehicle, and severity.

### E. What is a Cascade?
A **cascade** (`cascade_events.csv`) is the explicit, ground-truth propagation tree tracing how a disruption ripples through the network across multiple echelons:
- **Level 0 (Root Cause):** The shipment directly hit by the initial disruption.
- **Level 1 (Direct Impact):** Immediate downstream shipments whose planned departure buffers were breached.
- **Level 2 (Secondary Impact):** Downstream shipments delayed because Level 1 shipments arrived late.
- **Level 3+ (Tertiary Impact):** Deep propagation continuing into regional deliveries.

Each cascade event explicitly documents `direct_delay_minutes`, `propagated_delay_minutes`, and `total_delay_minutes`, enabling precise attribution of root causes vs. secondary propagation.

---

## 3. Dataset Architecture & Relational Mapping

The dataset is partitioned into 9 relational CSV tables:

```text
locations (28 hubs) ────────┬────── vehicles (650 fleet assets)
                            │                  │
                            ▼                  ▼
                       shipments (14,000 consignments)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
logistics_events        deliveries         dependencies (10,000 links)
 (77,063 scans)       (14,000 SLAs)             │
                                                ▼
  disruptions (720 root incidents) ───► cascade_events (6,300 tree nodes)
```

### Table Summary:
1. `shipments.csv`: Core shipment journeys, operational times, delay figures, and ML labels.
2. `logistics_events.csv`: Chronological operational milestone scans for every shipment.
3. `locations.csv`: 28 major Indian logistics hubs with GPS coordinates, operational capacities, and processing times.
4. `vehicles.csv`: 650 transport vehicles across 6 carriers with capacities, speeds, and reliability metrics.
5. `delay_reasons.csv`: Standardized 20-category industry delay taxonomy.
6. `dependencies.csv`: Explicit upstream-to-downstream relationships, buffer times, and transfer statuses.
7. `disruptions.csv`: Root-cause incident logs detailing when, where, and why disruptions occurred.
8. `cascade_events.csv`: Ground-truth causal tree tracking propagation depth, parent-child links, and delay transmission.
9. `deliveries.csv`: Final customer SLA compliance records with delay minutes, at-risk flags, and causal risk reasons.

---

## 4. Key Supply Chain Propagation Patterns

The dataset models 6 canonical supply chain cascade topologies:

| Pattern ID | Pattern Name | Topology | Operational Mechanism |
|---|---|---|---|
| **Pattern 1** | Simple Chain | $S_1 \to S_2 \to S_3$ | Feeder leg delayed $\to$ missed transfer at transshipment hub $\to$ linehaul leg delayed. |
| **Pattern 2** | One-to-Many Fan-Out | $S_1 \to \{S_2, S_3, S_4\}$ | Major trunkline trailer arrives late at cross-dock hub $\to$ stalls multiple regional feeder vans waiting for consolidated pallets. |
| **Pattern 3** | Deep Multi-Level Branching | $S_1 \to S_2 \to \{S_4, S_5\} \to S_7$ | Multi-echelon cascade propagating across 4 levels from national linehaul to intra-city final delivery. |
| **Pattern 4** | Warehouse Bottleneck | Inbound Surge $\to$ Congestion $\to$ Outbounds | Severe facility congestion or sorter breakdown delays multiple departing consignments simultaneously. |
| **Pattern 5** | Vehicle Dependency | $S_1 \xrightarrow{\text{Shared Veh}} S_2$ | Vehicle suffers engine breakdown on leg 1 $\to$ delayed arrival stalls next scheduled departure run. |
| **Pattern 6** | Route Disruption | Corridor Blockage $\to$ Detour $\to$ Downstream Miss | Highway closure (e.g. NH-48) forces a 150 km detour $\to$ delay exhausts connection buffer at destination hub. |

---

## 5. Machine Learning Applications & Tasks

The dataset includes grounded target variables designed for production ML models:

### 1. Delay Classification (`will_be_delayed`)
- **Objective:** Predict whether a newly scheduled shipment will experience an arrival delay exceeding 15 minutes.
- **Input Features:** Origin hub capacity, destination hub congestion, distance, vehicle reliability, scheduled departure time, cargo weight, historical carrier reliability.

### 2. Cascade Susceptibility Prediction (`will_cascade`)
- **Objective:** Given a shipment that has experienced an operational delay, predict whether this delay will breach scheduled buffer slack and cascade into downstream dependencies.
- **Input Features:** Incurred initial delay, scheduled transfer buffer, number of downstream dependencies, downstream priority tier, facility throughput speed.

### 3. Final Delivery SLA Risk (`delivery_at_risk`)
- **Objective:** Early warning system to predict whether a customer delivery will breach its SLA or fail while the shipment is still in-transit.
- **Input Features:** Current shipment milestone delay, upstream cascade level, cumulative en-route variance, remaining transit distance, carrier speed.

### 4. Root Cause Category Classification (`root_cause_category`)
- **Objective:** Automatically classify the true operational root cause (`Transportation`, `Warehouse`, `External`, `Operational`, `Documentation`) from telemetry logs and early milestone scans.

### 5. Cascade Severity Regression & Echelon Depth (`cascade_severity`, `cascade_level`)
- **Objective:** Predict total network delay impact (in minutes) and how deep down the echelon hierarchy the cascade will reach.

---

## 6. Dataset Summary Statistics

- **Total Shipments:** 14,000
- **Total Operational Scans:** 77,063
- **Network Locations:** 28 hubs across 15 Indian states (Delhi, Mumbai, Bengaluru, Chennai, Kolkata, Hyderabad, Ahmedabad, Pune, Jaipur, etc.)
- **Fleet Assets:** 650 vehicles across 6 carriers (Delhivery, BlueDart, Safexpress, Gati KWE, V-Trans, TCI)
- **Total Dependencies:** 10,000 relationships (2,500 active cascade handovers + 7,500 regular/buffer-absorbed transfers)
- **Root Disruptions:** 720 verified incidents
- **Cascade Tree Milestones:** 6,300 propagation events
- **Customer Deliveries:** 14,000 SLA fulfillment records
- **On-Time Shipments:** 61.5% (8,608 shipments)
- **Isolated Delay Shipments:** 25.0% (3,500 shipments)
- **Cascading Delay Shipments:** 15.0% (2,100 shipments across Levels 0, 1, 2, 3+)
