"""
Cascading Delay Intelligence - Comprehensive Dataset Profiling Script
Calculates metrics across:
1. Shipment metrics
2. Event metrics
3. Disruption metrics
4. Dependency metrics
5. Cascade metrics
6. Delivery metrics
7. Location-level statistics

Generates: reports/dataset_profile.json
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

DATA_DIR = os.environ.get("DATA_DIR", "cascading-delay-dataset/data")
REPORT_PATH = "reports/dataset_profile.json"

def profile_dataset(data_dir=DATA_DIR, report_path=REPORT_PATH):
    print(f"Profiling dataset from: {data_dir}...")
    
    shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv"))
    events = pd.read_csv(os.path.join(data_dir, "logistics_events.csv"))
    locations = pd.read_csv(os.path.join(data_dir, "locations.csv"))
    vehicles = pd.read_csv(os.path.join(data_dir, "vehicles.csv"))
    dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))
    disruptions = pd.read_csv(os.path.join(data_dir, "disruptions.csv"))
    cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))
    deliveries = pd.read_csv(os.path.join(data_dir, "deliveries.csv"))

    # 1. SHIPMENT METRICS
    total_shipments = len(shipments)
    ontime_shipments = int((shipments["final_delay_minutes"] <= 15).sum())
    delayed_shipments = int((shipments["final_delay_minutes"] > 15).sum())
    severely_delayed_shipments = int((shipments["final_delay_minutes"] > 180).sum())
    avg_delay = float(round(shipments["final_delay_minutes"].mean(), 2))
    median_delay = float(round(shipments["final_delay_minutes"].median(), 2))
    max_delay = int(shipments["final_delay_minutes"].max())
    delay_percentage = float(round((delayed_shipments / total_shipments) * 100, 2))

    shipment_metrics = {
        "total_shipments": total_shipments,
        "ontime_shipments": ontime_shipments,
        "delayed_shipments": delayed_shipments,
        "severely_delayed_shipments": severely_delayed_shipments,
        "average_delay_minutes": avg_delay,
        "median_delay_minutes": median_delay,
        "maximum_delay_minutes": max_delay,
        "delay_percentage": delay_percentage,
        "priority_distribution": shipments["priority"].value_counts().to_dict(),
        "cargo_type_distribution": shipments["cargo_type"].value_counts().to_dict()
    }

    # 2. EVENT METRICS
    total_events = len(events)
    events_by_type = events["event_type"].value_counts().to_dict()
    events_by_loc = events["location_id"].value_counts().to_dict()
    avg_event_delay = float(round(events["delay_minutes"].mean(), 2))
    most_common_event_types = list(events["event_type"].value_counts().head(5).index)

    event_metrics = {
        "total_events": total_events,
        "events_by_type": events_by_type,
        "events_by_location": events_by_loc,
        "average_event_delay_minutes": avg_event_delay,
        "most_common_event_types": most_common_event_types
    }

    # 3. DISRUPTION METRICS
    total_disruptions = len(disruptions)
    disr_types = disruptions["disruption_type"].value_counts().to_dict()
    disr_by_loc = disruptions["location_id"].value_counts().to_dict()
    
    # Calculate disruption duration
    d_start = pd.to_datetime(disruptions["start_time"])
    d_end = pd.to_datetime(disruptions["end_time"])
    durations = (d_end - d_start).dt.total_seconds() / 60.0
    avg_disr_duration = float(round(durations.mean(), 2))
    disr_severity_dist = disruptions["severity"].value_counts().to_dict()

    disruption_metrics = {
        "total_disruptions": total_disruptions,
        "disruption_types": disr_types,
        "disruptions_by_location": disr_by_loc,
        "average_disruption_duration_minutes": avg_disr_duration,
        "disruption_severity_distribution": disr_severity_dist,
        "average_affected_capacity_percentage": float(round(disruptions["affected_capacity_percentage"].mean(), 2))
    }

    # 4. DEPENDENCY METRICS
    total_dependencies = len(dependencies)
    deps_by_type = dependencies["dependency_type"].value_counts().to_dict()
    avg_dep_delay = float(round(dependencies["dependency_delay_minutes"].mean(), 2))
    deps_by_loc = dependencies["upstream_location_id"].value_counts().to_dict()
    top_dep_locations = list(dependencies["upstream_location_id"].value_counts().head(5).index)
    dep_status_dist = dependencies["dependency_status"].value_counts().to_dict()

    dependency_metrics = {
        "total_dependencies": total_dependencies,
        "dependencies_by_type": deps_by_type,
        "average_dependency_delay_minutes": avg_dep_delay,
        "dependency_status_distribution": dep_status_dist,
        "locations_with_highest_dependency_volume": top_dep_locations
    }

    # 5. CASCADE METRICS
    total_cascades = int(cascades["cascade_id"].nunique())
    cascading_shipments = int(cascades["affected_shipment_id"].nunique())
    isolated_delays = delayed_shipments - cascading_shipments
    
    cascade_groups = cascades.groupby("cascade_id")
    cascade_depths = cascade_groups["cascade_level"].max()
    avg_cascade_depth = float(round(cascade_depths.mean(), 2))
    max_cascade_depth = int(cascade_depths.max())
    
    shps_per_cascade = cascade_groups["affected_shipment_id"].nunique()
    avg_aff_shps = float(round(shps_per_cascade.mean(), 2))
    max_aff_shps = int(shps_per_cascade.max())
    
    total_prop_delay = int(cascades["propagated_delay_minutes"].sum())
    avg_prop_delay = float(round(cascades[cascades["is_propagated"] == True]["propagated_delay_minutes"].mean(), 2))

    cascade_metrics = {
        "total_cascades": total_cascades,
        "cascading_shipments": cascading_shipments,
        "isolated_delays": isolated_delays,
        "average_cascade_depth": avg_cascade_depth,
        "maximum_cascade_depth": max_cascade_depth,
        "average_affected_shipments_per_cascade": avg_aff_shps,
        "maximum_affected_shipments_per_cascade": max_aff_shps,
        "total_propagated_delay_minutes": total_prop_delay,
        "average_propagated_delay_minutes": avg_prop_delay,
        "echelon_level_distribution": cascades["cascade_level"].value_counts().to_dict()
    }

    # 6. DELIVERY METRICS
    total_deliveries = len(deliveries)
    ontime_deliv = int((deliveries["delivery_status"] == "Delivered On Time").sum())
    late_deliv = int((deliveries["delivery_status"] == "Delivered Late").sum())
    at_risk_deliv = int(deliveries["at_risk"].sum())
    failed_deliv = int((deliveries["delivery_status"] == "Failed Delivery").sum())

    delivery_metrics = {
        "total_deliveries": total_deliveries,
        "ontime_deliveries": ontime_deliv,
        "late_deliveries": late_deliv,
        "at_risk_deliveries": at_risk_deliv,
        "failed_deliveries": failed_deliv,
        "status_distribution": deliveries["delivery_status"].value_counts().to_dict()
    }

    # 7. LOCATION-LEVEL STATISTICS & BOTTLENECK ANALYSIS
    loc_stats = {}
    loc_names = locations.set_index("location_id")["location_name"].to_dict()
    loc_cities = locations.set_index("location_id")["city"].to_dict()
    loc_types = locations.set_index("location_id")["location_type"].to_dict()
    loc_caps = locations.set_index("location_id")["capacity"].to_dict()
    
    # Pre-map cascades by origin location
    shp_loc_map = shipments.set_index("shipment_id")["origin_location_id"].to_dict()
    cas_origins = {}
    for _, r in cascades.iterrows():
        s_orig = shp_loc_map.get(r["affected_shipment_id"])
        if s_orig:
            cas_origins[s_orig] = cas_origins.get(s_orig, 0) + 1

    for lid in locations["location_id"]:
        orig_ships = shipments[shipments["origin_location_id"] == lid]
        dest_ships = shipments[shipments["destination_location_id"] == lid]
        tot_ships = len(orig_ships) + len(dest_ships)
        del_orig = (orig_ships["final_delay_minutes"] > 15).sum()
        del_dest = (dest_ships["final_delay_minutes"] > 15).sum()
        del_rate = float(round(((del_orig + del_dest) / max(1, tot_ships)) * 100, 2))
        avg_loc_delay = float(round(orig_ships["final_delay_minutes"].mean(), 2))
        cas_involvement = cas_origins.get(lid, 0)
        
        # Bottleneck score: combination of delay rate, cascade volume, and capacity utilization
        is_bottleneck = bool(del_rate > 38.0 and cas_involvement > 180)
        
        loc_stats[lid] = {
            "location_name": loc_names.get(lid, lid),
            "city": loc_cities.get(lid, ""),
            "location_type": loc_types.get(lid, ""),
            "capacity": loc_caps.get(lid, 0),
            "total_shipments_handled": tot_ships,
            "origin_shipments": len(orig_ships),
            "destination_shipments": len(dest_ships),
            "delayed_shipments": int(del_orig + del_dest),
            "delay_rate_percentage": del_rate,
            "average_delay_minutes": avg_loc_delay,
            "cascade_events_involved": cas_involvement,
            "is_bottleneck": is_bottleneck
        }

    # Consolidated Profile
    profile = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_directory": data_dir,
        "shipment_metrics": shipment_metrics,
        "event_metrics": event_metrics,
        "disruption_metrics": disruption_metrics,
        "dependency_metrics": dependency_metrics,
        "cascade_metrics": cascade_metrics,
        "delivery_metrics": delivery_metrics,
        "location_metrics": loc_stats
    }

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    print("\n" + "="*70)
    print(f"PROFILING COMPLETE: Profile saved to: {report_path}")
    print(f"Total Shipments: {total_shipments:,} | Cascading: {cascading_shipments:,} | On-Time: {ontime_shipments:,}")
    print(f"Total Events: {total_events:,} | Total Cascades: {total_cascades} | Max Depth: {max_cascade_depth}")
    print("="*70)
    return profile

if __name__ == "__main__":
    profile_dataset()
