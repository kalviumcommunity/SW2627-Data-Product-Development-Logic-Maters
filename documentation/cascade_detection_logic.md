# Cascade Detection & Propagation Logic

This document specifies the algorithmic rules and causal criteria used by the **Cascade Engine** to detect, classify, and reconstruct multi-echelon delay propagation chains.

---

## 1. Fundamental Principle: Causal Evidence vs. Temporal Coincidence

A delay is **not** classified as cascading simply because two shipments arrived late around the same time or at the same facility. 

To classify a downstream delay as part of a cascade, the engine requires five strict criteria:

1. **Upstream Delay Evidence:** The upstream operation experienced an active delay exceeding standard operational tolerance ($> 15$ minutes).
2. **Explicit Dependency Relation:** An operational dependency record exists linking the upstream and downstream shipments (e.g. cross-dock cargo transfer, shared vehicle turnaround, consolidated trailer loading).
3. **Valid Temporal Sequence:** The downstream departure occurs after the upstream arrival or handover window.
4. **Buffer Exhaustion:** The delay passed from upstream exceeds the scheduled buffer/slack allocated for the transfer.
5. **Causal Explanatory Power:** The inherited delay reasonably explains the departure delay of the downstream leg.

```
Upstream Disruption / Delay (> 15m)
                 ↓
      Operational Dependency Handoff
                 ↓
      Buffer Slack Exhaustion (Slack ≤ 0)
                 ↓
Downstream Leg Departure Delay (> 15m)
                 ↓
      Customer Delivery SLA Breach
```

---

## 2. Delay Nature Taxonomy

The system partitions all delayed shipments into three distinct causal classes:

| Class | Definition | Diagnostic Criteria | Network Remediation |
|---|---|---|---|
| **Root Delay** | Delay introduced directly by an external or internal facility disruption. | Shipment is designated as `is_root_cause == True` or `cascade_level == 0`. Direct delay $> 15$m originating at initial loading/departure. | Fix origin root disruption (repair fleet, clear dock, bypass road). |
| **Propagated Delay** | Delay caused by an upstream dependency handover rather than internal failure. | Downstream shipment waiting for delayed feeder; inherited delay accounts for $>50\%$ of final delay; `is_propagated == True`. | Decouple connection, reroute with alternate carrier, buffer recovery. |
| **Independent Delay** | A localized operational variance without upstream causal connection. | Shipment delayed without upstream dependency records or after arriving on-time from previous leg. | Internal hub process optimization, local driver routing. |

---

## 3. Multi-Echelon Propagation Tree Reconstruction

Cascades propagate through multiple tiers of the logistics network:

* **Level 0 (Root Trigger):** The origin shipment experiencing direct disruption impact.
* **Level 1 (Immediate Handover):** Connected shipments that waited at transfer hubs for Level 0 cargo or vehicles.
* **Level 2 (Secondary Propagation):** Shipments waiting for Level 1 consignments at subsequent regional facilities.
* **Level 3+ (Tertiary / Terminal):** Last-mile delivery vehicles and regional distribution legs.

### Tree Traversal Algorithm
1. Locate root event with `cascade_level == 0` and `is_root_cause == True`.
2. Extract all records sharing `cascade_id`.
3. Construct parent-child lineage mapping `parent_shipment_id -> affected_shipment_id`.
4. Partition nodes into discrete echelon levels.
5. Trace delay compounding along each branch:
   $$\text{Total Delay}_{\text{node}} = \text{Direct Delay}_{\text{node}} + \text{Propagated Delay}_{\text{parent}}$$
6. Calculate blast radius (unique shipments, unique facilities, affected customer deliveries).

---

## 4. Preserving Uncertainty in Root Attribution

In complex supply chain networks, multiple disruptions may occur simultaneously at a major transport hub (e.g. concurrent warehouse dock congestion and regional weather holds).

Rather than forcing an unverified deterministic single root:
1. The engine checks for all disruptions active within $\pm 6$ hours of the cascade origin at the same facility.
2. If multiple candidate disruptions exist:
   * The primary attributed disruption receives $0.95$ confidence.
   * Concurrently active disruptions receive candidate confidence weights ($0.40$).
   * `attribution_uncertainty` is flagged as `true`.
   * Both candidates are exposed via the API and documentation to preserve analytical transparency.
