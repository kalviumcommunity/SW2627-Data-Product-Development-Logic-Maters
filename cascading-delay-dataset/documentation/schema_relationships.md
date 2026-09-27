# Cascading Delay Intelligence - Schema Relationships & Entity Mapping

This document details the relational architecture, foreign key mappings, table joins, and cardinality for the **Cascading Delay Intelligence** dataset.

---

## 1. High-Level Entity Relationship Diagram

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

---

## 2. Mermaid Entity Relationship Model

```mermaid
erDiagram
    LOCATIONS ||--o{ SHIPMENTS : "origin / destination"
    LOCATIONS ||--o{ VEHICLES : "home depot"
    LOCATIONS ||--o{ DISRUPTIONS : "disruption site"
    LOCATIONS ||--o{ LOGISTICS_EVENTS : "scan facility"
    
    VEHICLES ||--o{ SHIPMENTS : "assigned transport"
    VEHICLES ||--o{ LOGISTICS_EVENTS : "transport scan"
    VEHICLES ||--o{ DISRUPTIONS : "affected asset"
    
    SHIPMENTS ||--o{ LOGISTICS_EVENTS : "consists of scans"
    SHIPMENTS ||--|| DELIVERIES : "fulfills order SLA"
    SHIPMENTS ||--o{ DEPENDENCIES : "upstream provider"
    SHIPMENTS ||--o{ DEPENDENCIES : "downstream consumer"
    SHIPMENTS ||--o{ CASCADE_EVENTS : "affected consignment"
    
    DELAY_REASONS ||--o{ LOGISTICS_EVENTS : "delay classification"
    
    DISRUPTIONS ||--o{ CASCADE_EVENTS : "originates cascade"
    DEPENDENCIES ||--o{ CASCADE_EVENTS : "transmits delay"

    LOCATIONS {
        string location_id PK
        string location_name
        string location_type
        string city
        string state
        string region
        float latitude
        float longitude
        int capacity
        string operating_hours
        int average_processing_time_minutes
    }

    VEHICLES {
        string vehicle_id PK
        string vehicle_type
        int capacity_kg
        string carrier
        string home_location_id FK
        float reliability_score
        float average_speed_kmph
        string status
    }

    SHIPMENTS {
        string shipment_id PK
        string order_id FK
        string origin_location_id FK
        string destination_location_id FK
        string assigned_vehicle_id FK
        string priority
        string cargo_type
        int quantity
        float weight_kg
        datetime planned_departure
        datetime actual_departure
        datetime planned_arrival
        datetime actual_arrival
        string status
        int initial_delay_minutes
        int final_delay_minutes
        string delay_status
        datetime created_at
        int will_be_delayed
        int will_cascade
        int delivery_at_risk
        string root_cause_category
        string cascade_severity
        int cascade_level
    }

    LOGISTICS_EVENTS {
        string event_id PK
        string shipment_id FK
        string location_id FK
        string vehicle_id FK
        string event_type
        datetime scheduled_timestamp
        datetime actual_timestamp
        int delay_minutes
        string delay_reason_id FK
        string event_status
        string notes
    }

    DELAY_REASONS {
        string delay_reason_id PK
        string reason_category
        string reason_name
        string description
        string severity
    }

    DEPENDENCIES {
        string dependency_id PK
        string upstream_shipment_id FK
        string downstream_shipment_id FK
        string upstream_location_id FK
        string downstream_location_id FK
        string dependency_type
        datetime planned_dependency_time
        datetime actual_dependency_time
        int dependency_delay_minutes
        string dependency_status
        string cascade_id FK
    }

    DISRUPTIONS {
        string disruption_id PK
        string disruption_type
        string location_id FK
        string vehicle_id FK
        datetime start_time
        datetime end_time
        string severity
        string description
        string root_cause
        float affected_capacity_percentage
    }

    CASCADE_EVENTS {
        string cascade_id FK
        string disruption_id FK
        string root_shipment_id FK
        string affected_shipment_id FK
        string parent_shipment_id FK
        int cascade_level
        string propagation_type
        int direct_delay_minutes
        int propagated_delay_minutes
        int total_delay_minutes
        string root_cause
        boolean is_root_cause
        boolean is_propagated
        string impact_status
    }

    DELIVERIES {
        string delivery_id PK
        string order_id FK
        string shipment_id FK
        string destination_location_id FK
        datetime promised_delivery_time
        datetime actual_delivery_time
        string delivery_status
        int delay_minutes
        boolean at_risk
        string risk_reason
    }
```

---

## 3. Relational Key Reference Table

| Primary Table | Primary Key | Foreign Table | Foreign Key | Cardinality | Relationship Description |
|---|---|---|---|---|---|
| `locations` | `location_id` | `shipments` | `origin_location_id` | 1 : N | Origin departure facility for shipments. |
| `locations` | `location_id` | `shipments` | `destination_location_id` | 1 : N | Destination receiving facility for shipments. |
| `locations` | `location_id` | `vehicles` | `home_location_id` | 1 : N | Maintenance home depot for fleet assets. |
| `locations` | `location_id` | `logistics_events`| `location_id` | 1 : N | Facility where an operational scan occurred. |
| `locations` | `location_id` | `disruptions` | `location_id` | 1 : N | Site where an operational disruption originated. |
| `vehicles` | `vehicle_id` | `shipments` | `assigned_vehicle_id` | 1 : N | Transport vehicle hauling the consignment. |
| `vehicles` | `vehicle_id` | `logistics_events`| `vehicle_id` | 1 : N | Transport vehicle active during milestone scan. |
| `vehicles` | `vehicle_id` | `disruptions` | `vehicle_id` | 1 : N (nullable) | Transport asset affected by breakdown or inspection hold. |
| `shipments` | `shipment_id` | `logistics_events`| `shipment_id` | 1 : N | Operational milestone scans for the shipment. |
| `shipments` | `shipment_id` | `deliveries` | `shipment_id` | 1 : 1 | Final customer delivery task for the shipment. |
| `shipments` | `order_id` | `deliveries` | `order_id` | 1 : 1 | Customer order reference link. |
| `shipments` | `shipment_id` | `dependencies` | `upstream_shipment_id` | 1 : N | Upstream shipment providing connecting cargo. |
| `shipments` | `shipment_id` | `dependencies` | `downstream_shipment_id` | 1 : N | Downstream shipment receiving transferred cargo. |
| `shipments` | `shipment_id` | `cascade_events` | `affected_shipment_id` | 1 : N | Shipment participant impacted within a cascade tree. |
| `delay_reasons` | `delay_reason_id` | `logistics_events` | `delay_reason_id` | 1 : N (nullable) | Standardized delay cause attributed to an event. |
| `disruptions` | `disruption_id` | `cascade_events` | `disruption_id` | 1 : N | Root incident that triggered the propagation tree. |

---

## 4. Key Analytical Join Paths & Query Patterns

### A. Trace Complete Delay Chain from Root Disruption to Final Customer Delivery
To trace why a customer delivery was late back to the original root cause disruption:

```sql
SELECT 
    d.delivery_id,
    d.order_id,
    d.delivery_status,
    d.delay_minutes AS customer_sla_delay,
    s.shipment_id AS final_shipment_id,
    c.cascade_id,
    c.cascade_level,
    c.propagation_type,
    c.root_cause,
    dis.disruption_type,
    dis.description AS root_incident,
    loc_orig.city AS disruption_city,
    s_root.shipment_id AS root_shipment_id
FROM deliveries d
JOIN shipments s ON d.shipment_id = s.shipment_id
JOIN cascade_events c ON s.shipment_id = c.affected_shipment_id
JOIN disruptions dis ON c.disruption_id = dis.disruption_id
JOIN locations loc_orig ON dis.location_id = loc_orig.location_id
JOIN shipments s_root ON c.root_shipment_id = s_root.shipment_id
WHERE d.delivery_status = 'Delivered Late'
  AND c.propagation_type = 'Customer Delivery Risk';
```

### B. Reconstruct Hub Transfer Connection & Buffer Absorption
To determine whether an inbound shipment's delay was successfully absorbed by the transfer buffer or cascaded into the downstream departure:

```sql
SELECT 
    dep.dependency_id,
    dep.dependency_type,
    dep.upstream_shipment_id,
    s_up.final_delay_minutes AS upstream_arrival_delay,
    dep.downstream_shipment_id,
    s_down.initial_delay_minutes AS downstream_departure_delay,
    dep.dependency_delay_minutes,
    dep.dependency_status,
    loc.city AS transfer_hub
FROM dependencies dep
JOIN shipments s_up ON dep.upstream_shipment_id = s_up.shipment_id
JOIN shipments s_down ON dep.downstream_shipment_id = s_down.shipment_id
JOIN locations loc ON dep.upstream_location_id = loc.location_id
WHERE s_up.final_delay_minutes > 15;
```

### C. Identify Bottleneck Warehouses with Maximum Outbound Cascade Failures
To find which warehouses generate the highest volume of cascading delays:

```sql
SELECT 
    loc.location_id,
    loc.location_name,
    loc.city,
    loc.location_type,
    COUNT(DISTINCT c.cascade_id) AS total_cascades_initiated,
    COUNT(DISTINCT c.affected_shipment_id) AS total_downstream_shipments_affected,
    ROUND(AVG(c.total_delay_minutes), 1) AS avg_delay_minutes
FROM cascade_events c
JOIN shipments s ON c.affected_shipment_id = s.shipment_id
JOIN locations loc ON s.origin_location_id = loc.location_id
WHERE c.is_root_cause = TRUE
GROUP BY loc.location_id, loc.location_name, loc.city, loc.location_type
ORDER BY total_downstream_shipments_affected DESC;
```
