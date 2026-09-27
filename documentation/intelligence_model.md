# Unified Intelligence Model Architecture

The **Cascading Delay Intelligence** platform transforms raw operational supply chain events into causal diagnostics, blast-radius projections, and human-readable logistics intelligence.

```
REAL LOGISTICS DATA
        ↓
DATA UNDERSTANDING & VALIDATION
        ↓
CAUSAL DEPENDENCY GRAPH (DAG)
        ↓
CASCADE DETECTION & TREE RECONSTRUCTION
        ↓
ROOT CAUSE ATTRIBUTION (WITH UNCERTAINTY)
        ↓
DOWNSTREAM IMPACT & BLAST RADIUS ANALYSIS
        ↓
NETWORK BOTTLENECK DISCOVERY
        ↓
DETERMINISTIC VULNERABILITY & RISK SCORING
        ↓
HUMAN-READABLE LOGISTICS NARRATIVES
        ↓
FASTAPI REST DATA LAYER FOR FRONTEND
```

---

## 1. Graph Model Architecture (`LogisticsGraph`)

The logistics network is modeled as a heterogeneous directed dependency graph $G = (V, E)$:

### Nodes ($V$)
1. **Shipment Nodes ($V_{shp}$):** Unique consignment journeys with planned/actual departure and arrival timestamps, cargo type, priority, and delay values.
2. **Location Nodes ($V_{loc}$):** Hubs, distribution centers, and warehouses with capacity limits and nominal processing time.
3. **Disruption Nodes ($V_{dis}$):** Physical, operational, or environmental incidents (breakdowns, weather, congestion) with start/end windows and severity.

### Edges ($E$)
1. **Routing Edges ($E_{route}$):** Origin location $\to$ Shipment and Shipment $\to$ Destination location.
2. **Operational Dependency Edges ($E_{dep}$):** Direct causal handovers between shipments (e.g. `Cross-Dock Transfer`, `Waiting for Inbound Shipment`, `Shared Vehicle Handover`).
3. **Disruption Incidence Edges ($E_{dis}$):** Disruption incident $\to$ Affected facility.

Edges encode planned handoff time, actual handoff time, delay transferred, and dependency type. Relationships are only established when explicit causal dependencies exist.

---

## 2. Root Cause Attribution & Uncertainty Preservation

When a cascade is detected, the engine determines:
1. **Root Cause Type:** The primary triggering failure (e.g. `Vehicle Breakdown`, `Warehouse Congestion`, `Road Closure`).
2. **Origin Facility:** The specific logistics node where the initial delay occurred.
3. **Trigger Consignment:** The initial shipment that suffered direct delay.
4. **Initial Delay Magnitude:** The initial delay minutes introduced prior to network propagation.

### Preserving Uncertainty
If multiple disruptions occurred within a $\pm 6$ hour window at the origin facility, the system avoids false determinism:
* The candidate disruptions are recorded with relative confidence weights.
* `attribution_uncertainty` is set to `true`.
* The composite confidence score is adjusted to reflect the ambiguity.

---

## 3. Downstream Blast Radius & Compounding Impact

For each cascade, the engine calculates:
* **Initial Delay ($D_{init}$):** Direct delay introduced by the root trigger.
* **Propagated Delay ($D_{prop}$):** Cumulative delay inherited by downstream legs across dependencies:
  $$D_{prop} = \sum_{s \in S_{downstream}} \text{propagated\_delay}(s)$$
* **Total Network Delay ($D_{total} = D_{init} + D_{prop}$)**
* **Cascade Depth:** Maximum echelon level reached by the propagation tree.
* **Delivery SLA Breaches:** Count of connected doorstep deliveries that missed customer delivery deadlines.
* **Impact Score ($0 - 100$):** Weighted multi-factor indicator evaluating cascade depth (15%), affected shipments (35%), propagated delay hours (30%), and customer SLA breaches (20%).

---

## 4. Bottleneck Detection Engine

Logistics facilities are evaluated using multi-factor performance indicators to prevent false alerts on high-volume hubs:
* **Delay Rate:** Percentage of departing shipments delayed $>15$ minutes (threshold $\ge 30\%$).
* **Cascade Involvement:** Number of cascades originating or transiting through the facility ($\ge 15$).
* **Propagated Delay Contribution:** Total downstream delay minutes introduced ($\ge 3,000$m).
* **Dependency Transfer Volume:** Cross-docking handovers with high average delay ($\ge 300$ connections).

A hub is only classified as a **CRITICAL BOTTLENECK** if it triggers at least 2 independent criteria, and the engine generates deterministic explanatory reasons for each flagged facility.

---

## 5. Deterministic Risk Engine

Rather than emitting uncalibrated machine learning probabilities, the risk engine calculates a deterministic vulnerability score $R \in [0.05, 1.00]$ based on active physics:
* **Buffer Erosion Factor (35%):** Ratio of accumulated delay to remaining delivery buffer slack.
* **Downstream Dependency Pressure (25%):** Number of connecting outbound shipments held up by this leg.
* **Cascade Propagation Depth (20%):** Multi-echelon position in the delay tree.
* **Priority & Hub Congestion (20%):** Cargo priority tier (`CRITICAL`, `EXPRESS`) and active destination disruptions.

Scores are mapped into transparent operational risk bands: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, accompanied by plain-English bulleted reasons.

---

## 6. Human-Readable Logistics Intelligence

Every cascade and shipment record is synthesized into an executive narrative answering 4 core operational questions:
1. **What happened?** Clear identification of the origin event, root shipment, and transfer delays.
2. **Impact?** Scope of disruption across shipments, facilities, and customer delivery promises.
3. **Why does it matter?** Causal explanation of why this delay propagated through the network rather than staying isolated.
4. **Current risk & Recommended action?** Deterministic forecast of downstream breach risk and actionable mitigation advice.

---

## 7. Dual-Representation Data Explorer

All explorer endpoints (`GET /api/explorer/{entity_type}`) return two parallel representations for every record:
1. **`raw`:** Complete structured database fields for programmatic access.
2. **`humanExplanation`:** Plain-English summary explaining the real-world operational event.
