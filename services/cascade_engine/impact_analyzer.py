"""
Cascading Delay Intelligence - Cascade Impact & Bottleneck Analyzer
Computes downstream blast radius, delay compounding, SLA breaches, and location bottleneck scores.
Conforms strictly to the verified dataset schema.
"""

import os
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

class ImpactAnalyzer:
    """Analyzes the operational and customer impact of cascades and hub bottlenecks."""

    def __init__(self, data_dir: str = "cascading-delay-dataset/data"):
        self.data_dir = data_dir
        self.shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv")).set_index("shipment_id", drop=False)
        self.locations = pd.read_csv(os.path.join(data_dir, "locations.csv")).set_index("location_id", drop=False)
        self.cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))
        self.deliveries = pd.read_csv(os.path.join(data_dir, "deliveries.csv")).set_index("delivery_id", drop=False)
        self.dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))
        self.events = pd.read_csv(os.path.join(data_dir, "logistics_events.csv"))

    def analyze_cascade_impact(self, cascade_id: str) -> Dict[str, Any]:
        """
        Computes the complete blast radius, propagated delays, and delivery SLA risks for a cascade.
        """
        casc_subset = self.cascades[self.cascades["cascade_id"] == cascade_id]
        if casc_subset.empty:
            return {"error": f"Cascade {cascade_id} not found."}

        # Filter to unique shipments in this cascade
        shipment_ids = casc_subset["affected_shipment_id"].unique().tolist()
        root_row = casc_subset.sort_values(by="cascade_level").iloc[0]
        root_cause = str(root_row["root_cause"])
        root_shipment_id = str(root_row["root_shipment_id"])

        # Delay breakdown
        # Root initial delay
        initial_delay = int(casc_subset[casc_subset["is_root_cause"] == True]["direct_delay_minutes"].max()) if not casc_subset[casc_subset["is_root_cause"] == True].empty else int(root_row["total_delay_minutes"])
        
        # Propagated delay across downstream shipments
        downstream_records = casc_subset[casc_subset["cascade_level"] > 0]
        propagated_delay = int(downstream_records["propagated_delay_minutes"].sum()) if not downstream_records.empty else 0
        total_delay = initial_delay + propagated_delay

        # Locations involved (from associated shipments)
        involved_shps = self.shipments.loc[self.shipments["shipment_id"].isin(shipment_ids)]
        locations_involved = list(set(involved_shps["origin_location_id"].tolist() + involved_shps["destination_location_id"].tolist()))

        # Associated Deliveries
        casc_deliveries = self.deliveries[self.deliveries["shipment_id"].isin(shipment_ids)]
        total_deliveries = len(casc_deliveries)
        
        # At-risk or SLA breached deliveries
        sla_breached_deliveries = casc_deliveries[
            (casc_deliveries["delivery_status"] != "Delivered On Time") |
            (casc_deliveries["at_risk"] == True) |
            (casc_deliveries["delay_minutes"] > 0)
        ]
        at_risk_count = len(sla_breached_deliveries)

        # Depths & Timing
        max_depth = int(casc_subset["cascade_level"].max())
        
        # Duration from planned departure of root to arrival of deepest shipment
        dept_ts = pd.to_datetime(involved_shps["actual_departure"]).dropna()
        arr_ts = pd.to_datetime(involved_shps["actual_arrival"]).dropna()
        if not dept_ts.empty and not arr_ts.empty:
            duration_minutes = int((arr_ts.max() - dept_ts.min()).total_seconds() / 60)
        else:
            duration_minutes = initial_delay
        duration_minutes = max(duration_minutes, initial_delay)

        # Highest impact shipment
        shp_delays = casc_subset.groupby("affected_shipment_id")["total_delay_minutes"].max()
        highest_impact_shp = shp_delays.idxmax() if not shp_delays.empty else root_shipment_id
        highest_delay_val = int(shp_delays.max()) if not shp_delays.empty else initial_delay

        # Most affected location (accumulated delay from shipments at that location)
        loc_delays = involved_shps.groupby("origin_location_id")["final_delay_minutes"].sum()
        most_affected_loc = loc_delays.idxmax() if not loc_delays.empty else involved_shps.iloc[0]["origin_location_id"]
        loc_name = self.locations.loc[most_affected_loc, "location_name"] if most_affected_loc in self.locations.index else most_affected_loc

        # Downstream dependencies count
        downstream_deps = self.dependencies[self.dependencies["upstream_shipment_id"].isin(shipment_ids)]
        downstream_deps_count = len(downstream_deps)

        # Active status check
        shp_statuses = involved_shps["status"].tolist()
        is_active = any(st in ["Delayed", "In Transit", "In Processing"] for st in shp_statuses)

        # Deterministic Impact Score (0 to 100)
        depth_score = min(max_depth * 25.0, 100.0)
        shipments_score = min(len(shipment_ids) * 12.0, 100.0)
        delay_score = min((propagated_delay / 300.0) * 100.0, 100.0)
        sla_score = min(at_risk_count * 15.0, 100.0)

        composite_impact_score = round(
            (depth_score * 0.15) + (shipments_score * 0.35) + (delay_score * 0.30) + (sla_score * 0.20), 1
        )
        composite_impact_score = min(max(composite_impact_score, 5.0), 100.0)

        severity_label = "CRITICAL" if composite_impact_score >= 75 else ("HIGH" if composite_impact_score >= 50 else ("MEDIUM" if composite_impact_score >= 25 else "LOW"))

        return {
            "cascade_id": cascade_id,
            "root_cause": root_cause,
            "root_shipment_id": root_shipment_id,
            "status": "ACTIVE" if is_active else "RESOLVED",
            "severity": severity_label,
            "impact_score": composite_impact_score,
            "score_breakdown": {
                "depth_factor": round(depth_score, 1),
                "shipment_volume_factor": round(shipments_score, 1),
                "propagated_delay_factor": round(delay_score, 1),
                "sla_breach_factor": round(sla_score, 1)
            },
            "affected_shipments": len(shipment_ids),
            "affected_shipment_ids": shipment_ids,
            "affected_locations": len(locations_involved),
            "affected_location_ids": locations_involved,
            "affected_deliveries": total_deliveries,
            "deliveries_at_risk": at_risk_count,
            "cascade_depth": max_depth,
            "cascade_duration_minutes": duration_minutes,
            "initial_delay_minutes": initial_delay,
            "propagated_delay_minutes": propagated_delay,
            "total_delay_minutes": total_delay,
            "highest_impact_shipment": {
                "shipment_id": highest_impact_shp,
                "delay_minutes": highest_delay_val
            },
            "most_affected_location": {
                "location_id": most_affected_loc,
                "location_name": loc_name,
                "accumulated_delay_minutes": int(loc_delays.max()) if not loc_delays.empty else 0
            },
            "downstream_dependencies_count": downstream_deps_count
        }

    def analyze_location_bottlenecks(self) -> List[Dict[str, Any]]:
        """
        Identifies network bottlenecks using multi-factor indicators:
        - High delay rate
        - Frequent cascade participation
        - High downstream propagated delay contribution
        - High dependency exchange volume
        """
        results = []

        # Join cascade events with shipments to get location mapping
        shp_loc_map = self.shipments[["shipment_id", "origin_location_id"]].reset_index(drop=True)
        casc_with_shp = self.cascades.merge(
            shp_loc_map,
            left_on="affected_shipment_id",
            right_on="shipment_id",
            how="left"
        )

        for loc_id, loc_row in self.locations.iterrows():
            loc_id = str(loc_id)
            loc_name = str(loc_row["location_name"])
            city = str(loc_row["city"])
            loc_type = str(loc_row["location_type"])

            origin_shps = self.shipments[self.shipments["origin_location_id"] == loc_id]
            dest_shps = self.shipments[self.shipments["destination_location_id"] == loc_id]
            total_shipments = len(origin_shps) + len(dest_shps)

            if total_shipments == 0:
                continue

            delayed_origin = origin_shps[origin_shps["final_delay_minutes"] > 15]
            delayed_count = len(delayed_origin)
            delay_rate = round(delayed_count / len(origin_shps), 3) if len(origin_shps) > 0 else 0.0
            avg_delay = round(origin_shps["final_delay_minutes"].mean(), 1) if len(origin_shps) > 0 else 0.0

            # Cascade involvement via shipments originating from this location
            loc_casc = casc_with_shp[casc_with_shp["origin_location_id"] == loc_id]
            cascade_count = loc_casc["cascade_id"].nunique()
            affected_shipments_in_cascades = loc_casc["affected_shipment_id"].nunique()
            total_propagated_delay = int(loc_casc["propagated_delay_minutes"].sum())

            # Dependency volume
            loc_deps = self.dependencies[
                (self.dependencies["upstream_location_id"] == loc_id) |
                (self.dependencies["downstream_location_id"] == loc_id)
            ]
            dep_count = len(loc_deps)
            avg_dep_delay = round(loc_deps["dependency_delay_minutes"].mean(), 1) if dep_count > 0 else 0.0

            reasons = []
            is_bottleneck = False

            if delay_rate >= 0.35:
                reasons.append(f"Elevated departure delay rate of {round(delay_rate * 100, 1)}% exceeds the network threshold (30%).")
            if cascade_count >= 15:
                reasons.append(f"Involved in {cascade_count} multi-echelon delay cascades, spreading delays across regions.")
            if total_propagated_delay >= 3000:
                reasons.append(f"Transmitted {total_propagated_delay:,} minutes of downstream delay to connected fulfillment legs.")
            if dep_count >= 300 and avg_dep_delay > 15:
                reasons.append(f"High cross-dock dependency volume ({dep_count} connections) with average dependency delay of {avg_dep_delay}m.")

            if len(reasons) >= 2:
                is_bottleneck = True

            b_score = (
                (min(delay_rate / 0.5, 1.0) * 35.0) +
                (min(cascade_count / 40.0, 1.0) * 30.0) +
                (min(total_propagated_delay / 10000.0, 1.0) * 20.0) +
                (min(dep_count / 600.0, 1.0) * 15.0)
            )
            b_score = round(min(b_score, 100.0), 1)

            results.append({
                "location_id": loc_id,
                "location_name": loc_name,
                "city": city,
                "location_type": loc_type,
                "total_shipments": total_shipments,
                "origin_shipments": len(origin_shps),
                "delayed_shipments": delayed_count,
                "delay_rate": delay_rate,
                "average_delay_minutes": avg_delay,
                "cascade_count": cascade_count,
                "affected_shipments": affected_shipments_in_cascades,
                "total_propagated_delay_minutes": total_propagated_delay,
                "dependency_volume": dep_count,
                "is_bottleneck": is_bottleneck,
                "bottleneck_score": b_score,
                "bottleneck_reasons": reasons if is_bottleneck else ["Operating within standard hub throughput limits."]
            })

        results.sort(key=lambda x: x["bottleneck_score"], reverse=True)
        return results
