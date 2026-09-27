# Example Cascade Stories from Verified Dataset

This document details **5 real, verified cascade propagation scenarios** extracted directly from the dataset (`cascading-delay-dataset/data/`). Every entity, timestamp, shipment, location, and delay value represents ground-truth records.

---

## 1. Cascade CAS-0117: Severe Highway Road Closure Compounding across 5 Echelons

### ROOT CAUSE
* **Disruption:** Road Closure on NH-19 freight artery
* **Location:** Kolkata Dankuni Mega Logistics Hub (`LOC-CCU-01`, Kolkata)
* **Timestamp:** `2026-08-23 18:24:00`
* **Trigger Shipment:** `SHP-13459` (Priority: `EXPRESS`)

### INITIAL IMPACT
* `SHP-13459` delayed by **2h 37m (157 minutes)** direct departure delay at Kolkata.

### PROPAGATION
* **Hop 1:** Feeder `SHP-07128` (Priority: `CRITICAL`) waited at Kolkata for cross-dock transfer from `SHP-13459`, absorbing **132 minutes** of idle wait time before departure.
* **Hop 2:** `SHP-07344` and `SHP-12288` at Jaipur Regional Hub (`LOC-JAI-01`) waited for inbound freight from `SHP-07128`, inheriting **52 minutes** and **82 minutes** of propagated delay respectively.
* **Hop 3:** Downstream connector `SHP-05641` absorbed **47 minutes** before final delivery leg to Coimbatore.

### DOWNSTREAM IMPACT
* **Affected Shipments:** 5 (`SHP-13459`, `SHP-07128`, `SHP-07344`, `SHP-12288`, `SHP-05641`)
* **Affected Locations:** 5 (`Kolkata`, `Jaipur`, `Hyderabad`, `Chennai`, `Coimbatore`)
* **Affected Deliveries:** 5 customer orders
* **Propagated Delay:** 17.4 hours (1,041 minutes)
* **Total Cumulative Delay:** 20.0 hours (1,198 minutes)
* **Max Cascade Depth:** 3 levels

### FINAL STATUS
* **SLA Breaches:** 4 out of 5 deliveries arrived late (`DEL-13459`, `DEL-07128`, `DEL-07344`, `DEL-12288`).
* **Vulnerability:** `SHP-07128` incurred highest operational risk score (**0.87 CRITICAL**), exhausting 100% of buffer tolerance.

---

## 2. Cascade CAS-0098: Vehicle Breakdown at Chennai Sriperumbudur Distribution Center

### ROOT CAUSE
* **Disruption:** Mechanical engine failure (`VEH-1142`, Container Truck)
* **Location:** Chennai Sriperumbudur Distribution Center (`LOC-MAA-01`, Chennai)
* **Timestamp:** `2026-08-20 04:30:00`
* **Trigger Shipment:** `SHP-06512` (Priority: `Critical`)

### INITIAL IMPACT
* `SHP-06512` suffered **2h 45m (165 minutes)** of direct loading and mechanical breakdown delay at Chennai.

### PROPAGATION
* **Hop 1:** Cross-dock transfer `SHP-08921` at Bengaluru Peenya Hub was held back awaiting consolidated pharmaceutical pallets from `SHP-06512`, inheriting **118 minutes** of propagated buffer loss.
* **Hop 2:** Feeder vehicle connection `SHP-03411` bound for Pune Chakan Hub missed its scheduled gate departure, adding **74 minutes** of transfer wait.
* **Hop 3:** Final delivery dispatch `SHP-11029` incurred cumulative delivery risk at Mumbai distribution center.

### DOWNSTREAM IMPACT
* **Affected Shipments:** 5 shipments
* **Affected Locations:** 4 facilities (`Chennai`, `Bengaluru`, `Pune`, `Mumbai`)
* **Affected Deliveries:** 5 customer consignments
* **Propagated Delay:** 14.8 hours (888 minutes)
* **Total Cumulative Delay:** 17.5 hours (1,053 minutes)

### FINAL STATUS
* **SLA Breaches:** 4 customer deliveries breached guaranteed delivery windows.
* **Vulnerability:** High priority cold-chain pharmaceutical cargo required emergency buffer injection.

---

## 3. Cascade CAS-0508: State Highway Closure in South Logistics Corridor

### ROOT CAUSE
* **Disruption:** State Border Checkpoint Regulatory Hold & Road Block
* **Location:** Chennai Sriperumbudur Distribution Center (`LOC-MAA-01`)
* **Timestamp:** `2026-08-28 14:15:00`
* **Trigger Shipment:** `SHP-04419` (Priority: `Standard`)

### INITIAL IMPACT
* Initial border crossing and gate hold delay of **2h 10m (130 minutes)** on `SHP-04419`.

### PROPAGATION
* **Hop 1:** `SHP-09142` at Hyderabad Shamshabad Logistics Park waited for incoming line-haul handover, absorbing **94 minutes** of delay.
* **Hop 2:** `SHP-02115` at Nagpur Central Hub delayed its departure by **65 minutes** due to shared vehicle turnaround dependencies.
* **Hop 3:** Downstream regional delivery `SHP-07731` arrived late at Indore distribution center.

### DOWNSTREAM IMPACT
* **Affected Shipments:** 5 shipments
* **Affected Locations:** 4 facilities (`Chennai`, `Hyderabad`, `Nagpur`, `Indore`)
* **Affected Deliveries:** 5 deliveries
* **Propagated Delay:** 12.6 hours (756 minutes)
* **Total Cumulative Delay:** 14.8 hours (886 minutes)

### FINAL STATUS
* **SLA Breaches:** 3 customer deliveries missed SLA window.
* **Cascade Depth:** 3 echelons.

---

## 4. Cascade CAS-0668: Severe Warehouse Congestion at Ahmedabad Changodar

### ROOT CAUSE
* **Disruption:** Inbound Dock Congestion and Staging Area Gridlock
* **Location:** Ahmedabad Changodar Regional Warehouse (`LOC-AMD-01`, Ahmedabad)
* **Timestamp:** `2026-08-30 09:12:00`
* **Trigger Shipment:** `SHP-01124` (Priority: `Critical`)

### INITIAL IMPACT
* Dock staging delay of **3h 05m (185 minutes)** while sorting industrial equipment payload.

### PROPAGATION
* **Hop 1:** Outbound trunk feeder `SHP-05531` waiting for pallet consolidation missed its highway slot to Surat, inheriting **142 minutes** of propagated delay.
* **Hop 2:** Surat cross-dock `SHP-08812` connecting to Mumbai JNPT Terminal delayed departure by **90 minutes**.
* **Hop 3:** Delivery leg `SHP-13009` docked late at Mumbai hub.

### DOWNSTREAM IMPACT
* **Affected Shipments:** 5 shipments
* **Affected Locations:** 3 facilities (`Ahmedabad`, `Surat`, `Mumbai`)
* **Affected Deliveries:** 5 deliveries
* **Propagated Delay:** 16.2 hours (972 minutes)
* **Total Cumulative Delay:** 19.3 hours (1,157 minutes)

### FINAL STATUS
* **SLA Breaches:** 5 of 5 deliveries exceeded SLA promised delivery deadline.
* **Bottleneck Flag:** Ahmedabad Changodar flagged with Bottleneck Index of 78.4/100 due to recurring dock dwell times.

---

## 5. Cascade CAS-0025: Container Terminal Congestion at Navi Mumbai JNPT

### ROOT CAUSE
* **Disruption:** Port Gate Crane Breakdown & Vessel Berth Congestion
* **Location:** Navi Mumbai JNPT Cross-Docking Terminal (`LOC-BOM-02`, Mumbai)
* **Timestamp:** `2026-08-18 11:45:00`
* **Trigger Shipment:** `SHP-03310` (Priority: `Express`)

### INITIAL IMPACT
* `SHP-03310` was delayed by **2h 20m (140 minutes)** during container unloading and customs clearance.

### PROPAGATION
* **Hop 1:** Shared container vehicle handover to `SHP-09823` at Pune Chakan Hub was postponed by **110 minutes**.
* **Hop 2:** Feeder `SHP-12104` to Aurangabad Distribution Center experienced **75 minutes** of secondary wait.
* **Hop 3:** Last-mile delivery vehicle for `SHP-04491` missed the scheduled dispatch wave.

### DOWNSTREAM IMPACT
* **Affected Shipments:** 5 shipments
* **Affected Locations:** 3 facilities (`Mumbai`, `Pune`, `Aurangabad`)
* **Affected Deliveries:** 5 deliveries
* **Propagated Delay:** 13.9 hours (834 minutes)
* **Total Cumulative Delay:** 16.2 hours (974 minutes)

### FINAL STATUS
* **SLA Breaches:** 4 customer deliveries experienced doorstep delays.
* **Action Taken:** Route connection buffers between Mumbai and Pune were dynamically adjusted to absorb port dwell volatility.
