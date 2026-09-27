# Cascading Delay Intelligence - Real-World Cascade Case Studies

This document presents **5 realistic, end-to-end cascading delay case studies** documented directly from actual records in the generated dataset. Every scenario includes exact IDs, timestamps, locations, vehicles, delay minutes, and delivery outcomes.

---

## Case Study 1: Multi-Echelon Feeder Chain Cascade (`CAS-0003`)
**Pattern:** Pattern 1 — Simple Multi-Hop Chain ($S_1 \to S_2 \to S_3$)  
**Root Cause:** Vehicle Breakdown (Mechanical cooling system leak)  
**Corridor:** Hyderabad $\longrightarrow$ Indore $\longrightarrow$ Coimbatore $\longrightarrow$ Lucknow  

```text
[DIS-0003: Radiator Burst]
          │
          ▼ (196 min departure delay)
   SHP-04724 (Level 0)
Hyderabad ──► Indore (Arrives 203 min late)
                  │
                  ▼ (Feeder cargo transfer breached buffer by 162 min)
           SHP-12985 (Level 1)
        Indore ──► Coimbatore (Arrives 157 min late)
                        │
                        ▼ (Transfer buffer depleted; departs 96 min late)
                 SHP-04330 (Level 2)
              Coimbatore ──► Lucknow (Arrives 98 min late)
                              │
                              ▼
                  Customer Delivery Delayed (SLA Breached)
```

### Narrative Breakdown:
1. **Root Disruption (Level 0):** On **2026-08-19 at 16:24**, vehicle `VEH-1162` (operated by TCI Freight) experienced an emergency mechanical failure—a radiator burst and coolant leak—while staging at **Hyderabad Shamshabad Cargo Logistics Hub** (`LOC-HYD-01`). Disruption `DIS-0003` was declared with `Severity = Major`.
2. **First Shipment Impact:** Consignment `SHP-04724` was scheduled to depart Hyderabad for Indore at **16:45**. Due to the emergency radiator repair, gate departure was delayed to **20:01** (initial delay: **196 minutes**). Heavy evening traffic on the Nagpur-Betul highway corridor prevented catch-up; the truck docked at Indore Pithampur Logistics Park at **14:56 on 2026-08-20** (**203 minutes late**).
3. **Propagation to Feeder (Level 1):** Downstream shipment `SHP-12985` (Indore to Coimbatore, vehicle `VEH-1348`, Safexpress) was scheduled to depart Indore at **12:30**. Because its manifest contained priority pallets arriving on `SHP-04724`, departure was stalled until inbound cargo de-palletization completed. `SHP-12985` departed at **15:12** (**162 minutes delay**). It arrived in Coimbatore at **23:31 on 2026-08-21** (**157 minutes late**).
4. **Secondary Propagation (Level 2):** In Coimbatore, connecting shipment `SHP-04330` (Coimbatore to Lucknow, vehicle `VEH-1217`, TCI Freight) was scheduled to depart at **22:15**. The scheduled transfer buffer was completely exhausted; `SHP-04330` departed at **23:51** (**96 minutes delay**).
5. **Customer SLA Impact:** `SHP-04330` arrived at Lucknow Transport Nagar Hub at **01:21 on 2026-08-24** (**98 minutes late**). While last-mile dispatch partially cushioned the final delivery, customer delivery `DEL-04330` breached the promised SLA deadline by **44 minutes** (`delivery_status = Delivered Late`).

---

## Case Study 2: Warehouse Bottleneck & Cyclonic Weather Fan-Out (`CAS-0004`)
**Pattern:** Pattern 4 / Pattern 2 — Hub Bottleneck with One-to-Many Fan-Out  
**Root Cause:** Severe Weather (Cyclonic gale winds & dock yard saturation)  
**Corridor:** Delhi Hub $\longrightarrow$ Ahmedabad Hub $\longrightarrow$ {Mumbai, Indore, Jaipur, Chennai}  

```text
[DIS-0004: Cyclonic Gale Winds at Delhi Central FC]
                         │
                         ▼ (237 min departure delay)
                  SHP-06805 (Level 0)
               Delhi ──► Ahmedabad (Arrives 246 min late)
                         │
        ┌────────────────┼────────────────┬────────────────┐
        ▼                ▼                ▼                ▼
   SHP-03399        SHP-11530        SHP-12693        SHP-08402
(Ahmedabad-Mumbai)(Ahmedabad-Indore)(Ahmedabad-Jaipur)(Ahmedabad-Chennai)
   130m delay       127m delay       89m delay        109m delay
        │                │                │                │
        ▼                ▼                ▼                ▼
   SLA Delay: 89m   SLA Delay: 62m   SLA Delay: 78m   SLA Delay: 97m
```

### Narrative Breakdown:
1. **Root Disruption (Level 0):** On **2026-08-17 at 09:33**, severe cyclonic weather with gale winds struck **Delhi Central Fulfillment Center** (`LOC-DEL-01`). Container truck loading and yard crane operations were halted under safety protocol `DIS-0004` (`Severity = Critical`).
2. **Linehaul Delay:** Trunkline shipment `SHP-06805` (vehicle `VEH-1302`, Gati KWE) was scheduled to depart Delhi for Ahmedabad at **10:00**. Operations resumed after wind speeds dropped, allowing departure at **13:57** (**237 minutes delay**). In-transit weather detours pushed arrival at Ahmedabad Changodar Warehouse to **11:15 on 2026-08-18** (**246 minutes late**).
3. **One-to-Many Fan-Out (Level 1):** The late arrival of this massive 25-ton trailer backed up Ahmedabad's receiving bays. Because four regional distribution feeders were holding dispatch for transferred e-commerce parcels, the delay fanned out across Gujarat, Maharashtra, Rajasthan, and Tamil Nadu:
   - **`SHP-03399` (Ahmedabad to Mumbai):** Scheduled departure **08:00** was delayed to **10:10** (**130 min delay**). Arrived in Mumbai at **00:38** (**140 min late**). Final customer delivery `DEL-03399` was delayed by **89 minutes** (`At Risk = True`).
   - **`SHP-11530` (Ahmedabad to Indore):** Scheduled departure **08:15** delayed to **10:22** (**127 min delay**). Arrived in Indore at **21:07** (**122 min late**). Delivery delayed by **62 minutes**.
   - **`SHP-12693` (Ahmedabad to Jaipur):** Scheduled departure **08:15** delayed to **09:44** (**89 min delay**). Arrived in Jaipur at **04:48** (**94 min late**). Delivery delayed by **78 minutes**.
   - **`SHP-08402` (Ahmedabad to Chennai):** Scheduled departure **10:00** delayed to **11:49** (**109 min delay**). Arrived in Chennai at **06:56 on 2026-08-20** (**107 min late**). Delivery delayed by **97 minutes**.
4. **Summary:** A single weather delay at the Delhi gateway triggered **4 distinct downstream late deliveries** across 4 different states.

---

## Case Study 3: Deep Multi-Level Branching with Buffer Absorption (`CAS-0017`)
**Pattern:** Pattern 3 — Multi-Level Cascade with Echelon Damping  
**Root Cause:** Equipment Failure (Automated High-Bay Sorter Hydraulic Breakdown)  
**Corridor:** Jaipur $\longrightarrow$ Delhi $\longrightarrow$ Ahmedabad $\longrightarrow$ {Kolkata $\to$ Chandigarh, Coimbatore}  

```text
[DIS-0017: Sorter Hydraulic Failure at Jaipur Warehouse]
                          │
                          ▼ (126 min departure delay)
                   SHP-11913 (Level 0)
                Jaipur ──► Delhi (Arrives 127 min late)
                          │
                          ▼ (80 min departure delay)
                   SHP-08260 (Level 1)
                Delhi ──► Ahmedabad (Arrives 84 min late)
                          │
        ┌─────────────────┴─────────────────┐
        ▼ (Branch A)                        ▼ (Branch B)
   SHP-05881 (Level 2)                 SHP-10024 (Level 2)
Ahmedabad ──► Kolkata               Ahmedabad ──► Coimbatore
   (Departs 36m late)                  (Departs 16m late)
   (Arrives 34m late)                  (Arrives 15m late)
        │                                   │
        ▼                                   ▼
   SHP-09829 (Level 3)              Buffer Absorbed (SLA: On Time)
Kolkata ──► Chandigarh
   (Departs 16m late)
   (Arrives 11m late)
        │
        ▼
Buffer Absorbed (SLA: On Time)
```

### Narrative Breakdown:
1. **Root Disruption (Level 0):** On **2026-08-24 at 06:30**, the automated sortation high-bay hydraulic system at **Jaipur Sitapura Regional Warehouse** (`LOC-JAI-01`) jammed under heavy morning load (`DIS-0017`, `Severity = Major`).
2. **Initial Shipment Impact:** Express consignment `SHP-11913` (vehicle `VEH-1393`, V-Trans Express) was scheduled to depart for Delhi at **06:45**, but manual floor-sorting delayed dispatch until **08:51** (**126 minutes delay**). The shipment docked at Delhi Central FC at **16:56** (**127 minutes late**).
3. **First Downstream Tier (Level 1):** In Delhi, linehaul shipment `SHP-08260` (Delhi to Ahmedabad, vehicle `VEH-1301`) had a scheduled departure of **16:00**. Waiting for `SHP-11913` delayed departure to **17:20** (**80 minutes delay**). It arrived in Ahmedabad at **13:10 on 2026-08-25** (**84 minutes late**).
4. **Second Downstream Tier (Level 2 Branches):**
   - **Branch A (`SHP-05881`, Ahmedabad to Kolkata):** Planned departure **12:45** was held until **13:21** (**36 minutes delay**). It arrived in Kolkata at **06:35 on 2026-08-27** (**34 minutes late**).
   - **Branch B (`SHP-10024`, Ahmedabad to Coimbatore):** Planned departure **14:00** was held until **14:16** (**16 minutes delay**). It arrived in Coimbatore at **09:49 on 2026-08-27** (**15 minutes late**).
5. **Third Downstream Tier (Level 3) & Buffer Damping:** In Kolkata, shipment `SHP-09829` (Kolkata to Chandigarh, vehicle `VEH-1136`) was delayed departing from **08:45** to **09:01** (**16 minutes delay**). It reached Chandigarh at **05:10 on 2026-08-29** (**11 minutes late**).
6. **Delivery SLA Outcome:** Crucially, both `SHP-09829` and `SHP-10024` carried 90-minute customer SLA buffers. Because the propagated delay was damped from 127m $\to$ 84m $\to$ 34m $\to$ 11m, **both final deliveries were completed within the promised customer delivery window** (`delivery_status = Delivered On Time`). This illustrates how buffer capacity halts delay cascading in well-engineered supply chains.

---

## Case Study 4: Shared Vehicle Handover & Turnaround Cascade (`CAS-0006`)
**Pattern:** Pattern 5 — Shared Vehicle Fleet Asset Turnaround  
**Root Cause:** Inbound Dock Queue Gridlock at Mega Fulfillment Center  
**Corridor:** Bengaluru $\longrightarrow$ Surat $\longrightarrow$ Noida  

```text
[DIS-0006: Yard Gridlock at Bengaluru Nelamangala FC]
                        │
                        ▼ (175 min departure delay)
                 SHP-03377 (Level 0)
              Vehicle: VEH-1480 (Delhivery)
       Bengaluru ──► Surat (Arrives 176 min late at 19:40)
                        │
                        ▼ [Shared Asset: VEH-1480 scheduled to haul SHP-09999 at 18:45]
                 SHP-09999 (Level 1)
              Vehicle: VEH-1480 (Delhivery)
          Surat ──► Noida (Departs 79 min late at 20:04)
                        │
                        ▼ (Arrives Noida 76 min late)
          Customer Delivery Delayed (SLA Delay: 58m)
```

### Narrative Breakdown:
1. **Root Disruption (Level 0):** On **2026-08-07 at 15:15**, extreme yard gridlock at **Bengaluru Nelamangala Mega Fulfillment Center** (`LOC-BLR-01`) caused by a 30-trailer simultaneous arrival surge blocked outbound exit gates (`DIS-0006`).
2. **First Shipment Delay:** Heavy truck `VEH-1480` (Delhivery Express) assigned to consignment `SHP-03377` (Bengaluru to Surat) was trapped in the loading bay. Scheduled to depart at **16:00**, it cleared gates at **18:55** (**175 minutes delay**). Cruising across Maharashtra along NH-48, it arrived at Surat Sachin Industrial Logistics Hub at **19:40 on 2026-08-08** (**176 minutes late**, planned: **16:44**).
3. **Turnaround Cascading to Second Shipment (Level 1):** In Surat, vehicle `VEH-1480` was scheduled for a rapid turnaround to haul consignment `SHP-09999` (Surat to Noida) departing at **18:45**. Because the vehicle physically arrived at **19:40**, mandatory post-trip mechanical inspection and reloading delayed `SHP-09999`'s departure to **20:04** (**79 minutes delay**).
4. **Final Customer Impact:** `SHP-09999` arrived at Noida Sector-62 Distribution Hub at **20:02 on 2026-08-09** (**76 minutes late**). Final customer delivery `DEL-09999` breached its promised SLA deadline by **58 minutes** (`delivery_status = Delivered Late`, `at_risk = True`).

---

## Case Study 5: Highway Route Closure with Buffer Absorption (`CAS-0005`)
**Pattern:** Pattern 6 — Route Disruption with Slack Buffer Containment  
**Root Cause:** Emergency Culvert Highway Diversion  
**Corridor:** Kolkata $\longrightarrow$ Chennai $\longrightarrow$ Lucknow  

```text
[DIS-0005: Highway Culvert Repair Diversion near Howrah Hub]
                        │
                        ▼ (195 min departure delay)
                 SHP-00799 (Level 0)
              Vehicle: VEH-1269 (Delhivery)
       Kolkata ──► Chennai (Arrives 200 min late at 08:51)
                        │
                        ▼ [Scheduled Chennai Departure: 10:00 (69 min buffer remaining)]
                 SHP-08425 (Level 1)
              Vehicle: VEH-1558 (TCI Freight)
        Chennai ──► Lucknow (Departs only 20 min late at 10:20)
                        │
                        ▼ (Arrives Lucknow 28 min late)
          Customer Delivery Fulfilled On-Time (SLA Buffer Absorbed)
```

### Narrative Breakdown:
1. **Root Disruption (Level 0):** On **2026-08-07 at 06:00**, an emergency culvert highway collapse on the freight corridor outside **Howrah Freight Consolidation Center** (`LOC-CCU-02`) forced heavy freight onto a 40 km single-lane rural bypass (`DIS-0005`, `Severity = Major`).
2. **Initial Transit Delay:** Long-haul shipment `SHP-00799` (vehicle `VEH-1269`, Delhivery Express) carrying industrial equipment from Kolkata to Chennai was scheduled to depart at **06:30**. Gate clearance and initial detour navigation delayed departure to **09:45** (**195 minutes delay**). The 1,600 km coastal corridor transit ended at Chennai Madhavaram Hub at **08:51 on 2026-08-09** (**200 minutes late**, planned: **05:31**).
3. **Connecting Feeder & Slack Buffer:** In Chennai, connecting feeder shipment `SHP-08425` (Chennai to Lucknow, vehicle `VEH-1558`, TCI Freight) was scheduled to depart at **10:00**. Because `SHP-00799` arrived at **08:51**, exactly **69 minutes of transfer buffer** remained before `SHP-08425`'s planned departure.
4. **Buffer Containment:** Expedited cross-dock handling allowed the Chennai dock crew to transfer and inspect the pallets in **89 minutes**. `SHP-08425` departed Chennai at **10:20**—incurring a minor **20-minute departure delay**, absorbing **180 minutes** of the upstream delay.
5. **Customer SLA Outcome:** `SHP-08425` reached Lucknow at **08:32 on 2026-08-11** (**28 minutes late**). The customer order carried a standard 60-minute SLA buffer. The consignment was successfully delivered to the customer bay with **0 minutes SLA breach** (`delivery_status = Delivered On Time`, `at_risk = False`).
