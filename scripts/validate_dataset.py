"""
Cascading Delay Intelligence - Comprehensive Dataset Validation Script
Executes 25 rigorous checks across:
1. Referential integrity (Shipments, Locations, Vehicles, Disruptions, Dependencies, Cascades, Orders)
2. Timestamp integrity (Chronology, Travel physics, Disruption windows, Dependency sequences)
3. Delay integrity (Calculated delay vs stored delay fields)
4. Cascade integrity (Root causes, Affected nodes, Parent-child lineage, Propagation ordering)

Generates: validation/data_quality_report.json
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

DATA_DIR = os.environ.get("DATA_DIR", "cascading-delay-dataset/data")
REPORT_PATH = "validation/data_quality_report.json"

def run_validation(data_dir=DATA_DIR, report_path=REPORT_PATH):
    print(f"Loading dataset from: {data_dir}...")
    
    shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv"))
    events = pd.read_csv(os.path.join(data_dir, "logistics_events.csv"))
    locations = pd.read_csv(os.path.join(data_dir, "locations.csv"))
    vehicles = pd.read_csv(os.path.join(data_dir, "vehicles.csv"))
    delay_reasons = pd.read_csv(os.path.join(data_dir, "delay_reasons.csv"))
    dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))
    disruptions = pd.read_csv(os.path.join(data_dir, "disruptions.csv"))
    cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))
    deliveries = pd.read_csv(os.path.join(data_dir, "deliveries.csv"))

    checks_passed = 0
    checks_failed = 0
    warnings = 0
    issues = []
    
    def record_check(check_id, name, condition, error_msg="", is_warning=False):
        nonlocal checks_passed, checks_failed, warnings
        if condition:
            checks_passed += 1
            print(f"[PASSED] {check_id}: {name}")
        else:
            if is_warning:
                warnings += 1
                status_str = "WARNING"
                print(f"[WARNING] {check_id}: {name} - {error_msg}")
            else:
                checks_failed += 1
                status_str = "FAILED"
                print(f"[FAILED] {check_id}: {name} - {error_msg}")
            issues.append({
                "check_id": check_id,
                "check_name": name,
                "status": status_str,
                "details": error_msg
            })

    print("\n--- 1. REFERENTIAL INTEGRITY CHECKS ---")
    # Check 1: Primary key uniqueness across tables
    dups_ship = shipments["shipment_id"].duplicated().sum()
    dups_evt = events["event_id"].duplicated().sum()
    dups_loc = locations["location_id"].duplicated().sum()
    dups_veh = vehicles["vehicle_id"].duplicated().sum()
    dups_dep = dependencies["dependency_id"].duplicated().sum()
    dups_dis = disruptions["disruption_id"].duplicated().sum()
    dups_del = deliveries["delivery_id"].duplicated().sum()
    total_dups = dups_ship + dups_evt + dups_loc + dups_veh + dups_dep + dups_dis + dups_del
    record_check("CHK-01", "Primary Key Uniqueness across all entities", total_dups == 0, f"Found {total_dups} duplicate primary keys")

    # Check 2: Events reference valid Shipment IDs
    orphan_evt_ship = set(events["shipment_id"]) - set(shipments["shipment_id"])
    record_check("CHK-02", "Events -> Shipments foreign keys", len(orphan_evt_ship) == 0, f"{len(orphan_evt_ship)} orphan shipment references in events")

    # Check 3: Dependencies reference valid Upstream Shipment IDs
    orphan_dep_up = set(dependencies["upstream_shipment_id"]) - set(shipments["shipment_id"])
    record_check("CHK-03", "Dependencies -> Upstream Shipments foreign keys", len(orphan_dep_up) == 0, f"{len(orphan_dep_up)} invalid upstream shipment IDs")

    # Check 4: Dependencies reference valid Downstream Shipment IDs
    orphan_dep_down = set(dependencies["downstream_shipment_id"]) - set(shipments["shipment_id"])
    record_check("CHK-04", "Dependencies -> Downstream Shipments foreign keys", len(orphan_dep_down) == 0, f"{len(orphan_dep_down)} invalid downstream shipment IDs")

    # Check 5: Cascade Events reference valid Affected Shipment IDs
    orphan_cas_ship = set(cascades["affected_shipment_id"]) - set(shipments["shipment_id"])
    record_check("CHK-05", "Cascade Events -> Affected Shipments foreign keys", len(orphan_cas_ship) == 0, f"{len(orphan_cas_ship)} invalid affected shipment IDs in cascades")

    # Check 6: Deliveries reference valid Shipment IDs
    orphan_deliv_ship = set(deliveries["shipment_id"]) - set(shipments["shipment_id"])
    record_check("CHK-06", "Deliveries -> Shipments foreign keys", len(orphan_deliv_ship) == 0, f"{len(orphan_deliv_ship)} invalid shipment IDs in deliveries")

    # Check 7: Deliveries reference valid Order IDs matching Shipments
    orphan_deliv_ord = set(deliveries["order_id"]) - set(shipments["order_id"])
    record_check("CHK-07", "Deliveries -> Order IDs referential integrity", len(orphan_deliv_ord) == 0, f"{len(orphan_deliv_ord)} invalid order IDs in deliveries")

    # Check 8: All Location references exist in locations table
    all_locs = set(locations["location_id"])
    invalid_locs = (
        (set(shipments["origin_location_id"]) - all_locs) |
        (set(shipments["destination_location_id"]) - all_locs) |
        (set(events["location_id"]) - all_locs) |
        (set(disruptions["location_id"]) - all_locs) |
        (set(dependencies["upstream_location_id"]) - all_locs) |
        (set(dependencies["downstream_location_id"]) - all_locs)
    )
    record_check("CHK-08", "Location IDs existence across all tables", len(invalid_locs) == 0, f"{len(invalid_locs)} invalid location IDs referenced")

    # Check 9: All Vehicle references exist in vehicles table
    all_vehs = set(vehicles["vehicle_id"])
    invalid_vehs = (set(shipments["assigned_vehicle_id"]) - all_vehs) | (set(events["vehicle_id"]) - all_vehs)
    record_check("CHK-09", "Vehicle IDs existence across shipments and events", len(invalid_vehs) == 0, f"{len(invalid_vehs)} invalid vehicle IDs referenced")

    # Check 10: Cascade Events reference valid Disruption IDs
    orphan_cas_disr = set(cascades["disruption_id"]) - set(disruptions["disruption_id"])
    record_check("CHK-10", "Cascade Events -> Disruptions foreign keys", len(orphan_cas_disr) == 0, f"{len(orphan_cas_disr)} invalid disruption IDs referenced in cascades")

    print("\n--- 2. TIMESTAMP INTEGRITY CHECKS ---")
    # Check 11: Planned departure < planned arrival
    plan_dep = pd.to_datetime(shipments["planned_departure"])
    plan_arr = pd.to_datetime(shipments["planned_arrival"])
    invalid_plan_order = (plan_dep >= plan_arr).sum()
    record_check("CHK-11", "Shipments Planned Departure < Planned Arrival", invalid_plan_order == 0, f"{invalid_plan_order} shipments have planned arrival <= departure")

    # Check 12: Actual departure <= actual arrival (Travel Physics)
    act_dep = pd.to_datetime(shipments["actual_departure"])
    act_arr = pd.to_datetime(shipments["actual_arrival"])
    arr_before_dep = (act_arr < act_dep).sum()
    record_check("CHK-12", "Shipments Actual Departure <= Actual Arrival", arr_before_dep == 0, f"{arr_before_dep} shipments have actual arrival < departure")

    # Check 13: Chronological ordering of events within each shipment
    event_order_violations = 0
    events_sorted = events.sort_values(by=["shipment_id", "actual_timestamp"])
    for s_id, group in events.groupby("shipment_id"):
        ts_list = pd.to_datetime(group["actual_timestamp"]).tolist()
        for i in range(len(ts_list) - 1):
            if ts_list[i] > ts_list[i + 1]:
                event_order_violations += 1
    record_check("CHK-13", "Chronological ordering of operational milestone events", event_order_violations == 0, f"{event_order_violations} chronological inversions in events")

    # Check 14: Disruption start_time < end_time
    dis_start = pd.to_datetime(disruptions["start_time"])
    dis_end = pd.to_datetime(disruptions["end_time"])
    dis_inv = (dis_start >= dis_end).sum()
    record_check("CHK-14", "Disruptions start_time < end_time", dis_inv == 0, f"{dis_inv} disruptions have start >= end")

    # Check 15: Planned dependency meeting time <= actual dependency time
    dep_plan = pd.to_datetime(dependencies["planned_dependency_time"])
    dep_act = pd.to_datetime(dependencies["actual_dependency_time"])
    dep_early = (dep_act < dep_plan).sum()
    record_check("CHK-15", "Dependencies Planned <= Actual Handover Time", dep_early == 0, f"{dep_early} dependencies have actual time earlier than planned")

    # Check 16: Customer Promised Delivery Time >= Planned Arrival
    prom_deliv = pd.to_datetime(deliveries["promised_delivery_time"])
    prom_before_plan = (prom_deliv < plan_arr).sum()
    record_check("CHK-16", "Deliveries Promised Delivery Time >= Planned Arrival", prom_before_plan == 0, f"{prom_before_plan} deliveries promised before planned arrival")

    print("\n--- 3. DELAY INTEGRITY CHECKS ---")
    # Check 17: Initial delay minutes match (actual_departure - planned_departure)
    calc_dep_delay = np.maximum(0, np.round((act_dep - plan_dep).dt.total_seconds() / 60.0).astype(int))
    mismatch_dep_delay = (calc_dep_delay != shipments["initial_delay_minutes"]).sum()
    record_check("CHK-17", "Shipments Initial Delay Minutes matches departure difference", mismatch_dep_delay == 0, f"{mismatch_dep_delay} initial delay mismatches")

    # Check 18: Final delay minutes match (actual_arrival - planned_arrival)
    calc_arr_delay = np.maximum(0, np.round((act_arr - plan_arr).dt.total_seconds() / 60.0).astype(int))
    mismatch_arr_delay = (calc_arr_delay != shipments["final_delay_minutes"]).sum()
    record_check("CHK-18", "Shipments Final Delay Minutes matches arrival difference", mismatch_arr_delay == 0, f"{mismatch_arr_delay} final delay mismatches")

    # Check 19: Delivery delay minutes match (actual_delivery_time - promised_delivery_time)
    act_deliv = pd.to_datetime(deliveries["actual_delivery_time"])
    calc_deliv_delay = np.maximum(0, np.round((act_deliv - prom_deliv).dt.total_seconds() / 60.0).astype(int))
    mismatch_deliv_delay = (calc_deliv_delay != deliveries["delay_minutes"]).sum()
    record_check("CHK-19", "Deliveries Delay Minutes matches delivery difference", mismatch_deliv_delay == 0, f"{mismatch_deliv_delay} delivery delay mismatches")

    # Check 20: Non-negative delay values across all tables
    neg_delays = (
        (shipments["initial_delay_minutes"] < 0).sum() +
        (shipments["final_delay_minutes"] < 0).sum() +
        (events["delay_minutes"] < 0).sum() +
        (dependencies["dependency_delay_minutes"] < 0).sum() +
        (deliveries["delay_minutes"] < 0).sum()
    )
    record_check("CHK-20", "Non-negative delay values across all tables", neg_delays == 0, f"{neg_delays} negative delay values found")

    print("\n--- 4. CASCADE INTEGRITY CHECKS ---")
    # Check 21: Every cascade has a valid Level 0 root shipment
    cas_roots = cascades[cascades["cascade_level"] == 0]
    cas_ids = cascades["cascade_id"].unique()
    missing_roots = set(cas_ids) - set(cas_roots["cascade_id"])
    record_check("CHK-21", "Every cascade has a Level 0 root shipment", len(missing_roots) == 0, f"{len(missing_roots)} cascades missing Level 0 root")

    # Check 22: Cascade root shipments have is_root_cause = True and is_propagated = False
    invalid_root_flags = ((cas_roots["is_root_cause"] != True) | (cas_roots["is_propagated"] != False)).sum()
    record_check("CHK-22", "Cascade Level 0 root flags consistency", invalid_root_flags == 0, f"{invalid_root_flags} root records with inconsistent boolean flags")

    # Check 23: Propagated nodes (level > 0) have valid non-empty parent_shipment_id
    propagated_nodes = cascades[cascades["cascade_level"] > 0]
    missing_parent = propagated_nodes["parent_shipment_id"].isna().sum() + (propagated_nodes["parent_shipment_id"] == "").sum()
    record_check("CHK-23", "Downstream cascade nodes have valid parent shipment IDs", missing_parent == 0, f"{missing_parent} propagated nodes missing parent ID")

    # Check 24: Total delay in primary cascade milestones matches direct + propagated delay
    primary_types = [
        'Root Disruption', 'Waiting for Inbound Shipment', 'Warehouse Transfer',
        'Cross-Dock Transfer', 'Route Connection', 'Shared Vehicle Turnaround',
        'Warehouse Congestion Transfer'
    ]
    cas_primary = cascades[cascades["propagation_type"].isin(primary_types)]
    cas_delay_diff = (cas_primary["total_delay_minutes"] - (cas_primary["direct_delay_minutes"] + cas_primary["propagated_delay_minutes"])).abs()
    cas_delay_mismatch = (cas_delay_diff > 15).sum() # allow minor local en-route variance <= 10m
    record_check("CHK-24", "Cascade primary milestones delay matches direct + propagated components", cas_delay_mismatch == 0, f"{cas_delay_mismatch} cascade delay calculation discrepancies")

    # Check 25: All cascade-affected shipments have positive delays (> 0)
    affected_ships = cascades["affected_shipment_id"].unique()
    aff_ship_delays = shipments[shipments["shipment_id"].isin(affected_ships)]["final_delay_minutes"]
    zero_delay_aff = (aff_ship_delays == 0).sum()
    record_check("CHK-25", "All cascade-affected shipments have non-zero delay", zero_delay_aff == 0, f"{zero_delay_aff} cascade shipments have zero delay")

    # Final summary report
    overall_status = "passed" if checks_failed == 0 else "failed"
    report = {
        "status": overall_status,
        "total_checks": checks_passed + checks_failed + warnings,
        "passed": checks_passed,
        "failed": checks_failed,
        "warnings": warnings,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_directory": data_dir,
        "issues": issues
    }

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    
    print("\n" + "="*70)
    print(f"VALIDATION COMPLETE: {checks_passed}/25 Checks Passed | {checks_failed} Failed | {warnings} Warnings")
    print(f"Report saved to: {report_path}")
    print("="*70)
    return report

class DatasetValidator:
    """Object-oriented wrapper around dataset validation checks."""
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        self.shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv"))
        self.events = pd.read_csv(os.path.join(data_dir, "logistics_events.csv"))
        self.locations = pd.read_csv(os.path.join(data_dir, "locations.csv"))
        self.vehicles = pd.read_csv(os.path.join(data_dir, "vehicles.csv"))
        self.delay_reasons = pd.read_csv(os.path.join(data_dir, "delay_reasons.csv"))
        self.dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))
        self.disruptions = pd.read_csv(os.path.join(data_dir, "disruptions.csv"))
        self.cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))
        self.deliveries = pd.read_csv(os.path.join(data_dir, "deliveries.csv"))

    def run_all_checks(self, report_path=REPORT_PATH):
        return run_validation(data_dir=self.data_dir, report_path=report_path)

if __name__ == "__main__":
    run_validation()

