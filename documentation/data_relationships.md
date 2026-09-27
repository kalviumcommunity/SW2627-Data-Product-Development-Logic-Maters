# Data Relationships & Graph Topologies

This document explains the **actual relational and causal relationships** connecting tables in the **Cascading Delay Intelligence** dataset.

---

## 1. Relational Map & Cardinality Matrix

```text
                  +---------------------------+
                  |         locations         |
                  +---------------------------+
                     ^                     ^
                     | (origin/dest)       | (home_location_id)
                     |                     |
+--------------------+----+         +------+--------------------+
|        shipments        | <-----> |          vehicles         |
+--------------------+----+         +---------------------------+
   |        |        |
   |        |        +-----------------------------------+
   |        |                                            |
   |        v                                            v
   |   +-------------------+                     +--------------------+
   |   | logistics_events  |                     |    dependencies    |
   |   +-------------------+                     +--------------------+
   |            |                                          |
   |            v (delay_reason_id)                        |
   |   +-------------------+                               |
   |   |   delay_reasons   |                               v
   |   +-------------------+                     +--------------------+
   |                                             |   cascade_events   |
   v                                             +--------------------+
+--------------------+                                     ^
|     deliveries     |                                     |
+--------------------+                                     |
                                                 +--------------------+
                                                 |    disruptions     |
                                                 +--------------------+
```

### Table Relationships Matrix

| Source Table | Source Key | Target Table | Target Key | Cardinality | Physical Meaning |
|---|---|---|---|---|---|
| `shipments` | `origin_location_id` | `locations` | `location_id` | N : 1 | Departure terminal where cargo is staged and loaded. |
| `shipments` | `destination_location_id` | `locations` | `location_id` | N : 1 | Arrival terminal where cargo is de-palletized and transferred. |
| `shipments` | `assigned_vehicle_id` | `vehicles` | `vehicle_id` | N : 1 | The truck, mini-truck, or van executing the transport leg. |
| `shipments` | `order_id` | `deliveries` | `order_id` | 1 : 1 | Customer order fulfilling this shipment. |
| `logistics_events` | `shipment_id` | `shipments` | `shipment_id` | N : 1 | Chronological scan events composing this shipment. |
| `logistics_events` | `location_id` | `locations` | `location_id` | N : 1 | Geographic hub where milestone scan occurred. |
| `logistics_events` | `vehicle_id` | `vehicles` | `vehicle_id` | N : 1 | Fleet asset active at milestone scan. |
| `logistics_events` | `delay_reason_id` | `delay_reasons` | `delay_reason_id` | N : 1 (nullable) | Standardized delay cause if milestone was delayed. |
| `dependencies` | `upstream_shipment_id` | `shipments` | `shipment_id` | N : 1 | The feeder shipment providing connecting cargo or asset. |
| `dependencies` | `downstream_shipment_id` | `shipments` | `shipment_id` | N : 1 | The succeeding shipment dependent on the feeder. |
| `dependencies` | `upstream_location_id` | `locations` | `location_id` | N : 1 | Hub where transfer connection takes place. |
| `dependencies` | `downstream_location_id` | `locations` | `location_id` | N : 1 | Hub where downstream shipment departs. |
| `dependencies` | `cascade_id` | `cascade_events` | `cascade_id` | N : 1 (nullable) | Active cascade tree linkage (null for on-time transfers). |
| `disruptions` | `location_id` | `locations` | `location_id` | N : 1 | Hub or terminal where disruption incident occurred. |
| `disruptions` | `vehicle_id` | `vehicles` | `vehicle_id` | N : 1 (nullable) | Transport asset affected by breakdown (null for facility events). |
| `cascade_events` | `disruption_id` | `disruptions` | `disruption_id` | N : 1 | The root disruption incident initiating the cascade. |
| `cascade_events` | `root_shipment_id` | `shipments` | `shipment_id` | N : 1 | Initial shipment directly delayed by disruption (Level 0). |
| `cascade_events` | `affected_shipment_id` | `shipments` | `shipment_id` | N : 1 | Shipment impacted at this node of the cascade tree. |
| `cascade_events` | `parent_shipment_id` | `shipments` | `shipment_id` | N : 1 (nullable) | Direct predecessor shipment that transmitted the delay. |
| `deliveries` | `shipment_id` | `shipments` | `shipment_id` | 1 : 1 | Physical linehaul shipment linked to customer delivery SLA. |
| `deliveries` | `destination_location_id` | `locations` | `location_id` | N : 1 | Final delivery depot. |

---

## 2. Causal Delay Propagation Topology

In a logistics network, delays travel through **directed acyclic graphs (DAGs)** formed by temporal dependencies:

$$\text{Disruption}(D) \xrightarrow{\text{causes}} S_{\text{root}} \xrightarrow{\text{transfer at } L_1} S_1 \xrightarrow{\text{transfer at } L_2} S_2 \xrightarrow{\text{delivery}} \text{Customer SLA}$$

### Propagation Physics:
1. **Root Delay:** Introduced directly onto $S_{\text{root}}$ at Level 0:
   $$\text{Initial Delay} = t_{\text{actual departure}} - t_{\text{planned departure}}$$
2. **Buffer Slack:** Between $S_{\text{upstream}}$ arrival and $S_{\text{downstream}}$ departure:
   $$\text{Buffer} = t_{\text{planned departure}}^{\text{downstream}} - t_{\text{planned arrival}}^{\text{upstream}}$$
3. **Propagation Condition:** Delay propagates if and only if upstream actual arrival breaches the planned downstream departure:
   $$\text{Propagated Delay} = \max\left(0, t_{\text{actual arrival}}^{\text{upstream}} - t_{\text{planned departure}}^{\text{downstream}}\right)$$
4. **Buffer Absorption:** If $t_{\text{actual arrival}}^{\text{upstream}} \le t_{\text{planned departure}}^{\text{downstream}}$, the buffer completely absorbs the upstream delay. The downstream shipment departs on time, and the cascade halts naturally (`dependency_status = 'Delayed - Absorbed'`).

---

## 3. Join Graphs for Analytical Queries

### A. Root Cause Attribution
```sql
SELECT 
    d.disruption_id,
    d.disruption_type,
    d.description,
    c.cascade_id,
    c.cascade_level,
    s.shipment_id,
    s.origin_location_id,
    s.destination_location_id,
    s.final_delay_minutes
FROM disruptions d
JOIN cascade_events c ON d.disruption_id = c.disruption_id
JOIN shipments s ON c.affected_shipment_id = s.shipment_id
ORDER BY c.cascade_id, c.cascade_level;
```

### B. Upstream-to-Downstream Handover Tracking
```sql
SELECT 
    dep.dependency_id,
    dep.dependency_type,
    s_up.shipment_id AS upstream_id,
    s_up.actual_arrival AS upstream_arrival,
    s_up.final_delay_minutes AS upstream_delay,
    s_down.shipment_id AS downstream_id,
    s_down.actual_departure AS downstream_departure,
    dep.dependency_delay_minutes,
    dep.dependency_status
FROM dependencies dep
JOIN shipments s_up ON dep.upstream_shipment_id = s_up.shipment_id
JOIN shipments s_down ON dep.downstream_shipment_id = s_down.shipment_id
WHERE dep.dependency_status != 'Resolved On-Time';
```
