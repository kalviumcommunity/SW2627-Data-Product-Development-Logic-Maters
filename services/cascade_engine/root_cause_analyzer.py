"""
Cascading Delay Intelligence - Root Cause Analyzer
Identifies the primary trigger, origin location, timestamp, and initial impact of delay cascades.
Preserves uncertainty if multiple potential disruptions overlap at the origin node.
"""

import os
from typing import Dict, List, Any, Optional
import pandas as pd
from datetime import datetime, timedelta

class RootCauseAnalyzer:
    """Analyzes and attributes root causes for cascades and delayed shipments."""

    def __init__(self, data_dir: str = "cascading-delay-dataset/data"):
        self.data_dir = data_dir
        self.shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv")).set_index("shipment_id", drop=False)
        self.locations = pd.read_csv(os.path.join(data_dir, "locations.csv")).set_index("location_id", drop=False)
        self.disruptions = pd.read_csv(os.path.join(data_dir, "disruptions.csv")).set_index("disruption_id", drop=False)
        self.cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))
        self.dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))

    @staticmethod
    def _format_duration(minutes: int) -> str:
        """Helper to format minutes into human-readable e.g. '2h 15m' or '45m'."""
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0 and mins > 0:
            return f"{hours}h {mins}m"
        elif hours > 0:
            return f"{hours}h"
        return f"{mins}m"

    def analyze_cascade(self, cascade_id: str) -> Dict[str, Any]:
        """
        Pinpoints the root cause, initial impact, and origin details of a cascade.
        Preserves uncertainty if multiple candidate disruptions exist at the origin hub.
        """
        casc_subset = self.cascades[self.cascades["cascade_id"] == cascade_id]
        if casc_subset.empty:
            return {"error": f"Cascade {cascade_id} not found."}

        # Root event is where is_root_cause is True or minimum cascade_level
        root_events = casc_subset[casc_subset["is_root_cause"] == True]
        if root_events.empty:
            root_events = casc_subset[casc_subset["cascade_level"] == casc_subset["cascade_level"].min()]

        root_row = root_events.iloc[0]
        root_shipment_id = str(root_row["root_shipment_id"])
        disruption_id = str(root_row["disruption_id"]) if pd.notna(root_row["disruption_id"]) else None
        primary_cause = str(root_row["root_cause"])

        # Fetch root shipment metadata for origin location and timestamp
        root_shp = self.shipments.loc[root_shipment_id] if root_shipment_id in self.shipments.index else None
        root_location_id = str(root_shp["origin_location_id"]) if root_shp is not None else "LOC-UNKNOWN"
        root_timestamp = str(root_shp["actual_departure"]) if root_shp is not None else str(root_shp["planned_departure"] if root_shp is not None else "")
        initial_delay_minutes = int(root_row["direct_delay_minutes"]) if root_row["direct_delay_minutes"] > 0 else int(root_row["total_delay_minutes"])

        # Fetch location metadata
        loc_name = self.locations.loc[root_location_id, "location_name"] if root_location_id in self.locations.index else root_location_id
        loc_city = self.locations.loc[root_location_id, "city"] if root_location_id in self.locations.index else ""

        # Fetch primary disruption info
        disruption_info = None
        if disruption_id and disruption_id in self.disruptions.index:
            disr = self.disruptions.loc[disruption_id]
            start_dt = pd.to_datetime(disr["start_time"])
            end_dt = pd.to_datetime(disr["end_time"])
            dur_mins = int((end_dt - start_dt).total_seconds() / 60.0) if pd.notna(start_dt) and pd.notna(end_dt) else 0

            disruption_info = {
                "disruption_id": disruption_id,
                "disruption_type": str(disr["disruption_type"]),
                "severity": str(disr["severity"]),
                "description": str(disr["description"]),
                "start_time": str(disr["start_time"]),
                "end_time": str(disr["end_time"]),
                "duration_minutes": dur_mins
            }

        # Check for overlapping disruptions to preserve uncertainty
        candidate_causes = []
        root_dt = None
        try:
            root_dt = datetime.fromisoformat(root_timestamp)
        except Exception:
            pass

        if root_dt:
            window_start = (root_dt - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
            window_end = (root_dt + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
            
            # Find disruptions at the same location within the window
            nearby_disruptions = self.disruptions[
                (self.disruptions["location_id"] == root_location_id) &
                (self.disruptions["start_time"] <= window_end) &
                (self.disruptions["end_time"] >= window_start)
            ]

            for _, d_row in nearby_disruptions.iterrows():
                is_attributed = (d_row["disruption_id"] == disruption_id)
                candidate_causes.append({
                    "disruption_id": d_row["disruption_id"],
                    "cause": d_row["disruption_type"],
                    "description": d_row["description"],
                    "severity": d_row["severity"],
                    "confidence": 0.95 if is_attributed else 0.40,
                    "attributed_primary": bool(is_attributed)
                })

        if not candidate_causes and primary_cause:
            candidate_causes.append({
                "disruption_id": disruption_id,
                "cause": primary_cause,
                "description": disruption_info["description"] if disruption_info else f"Disruption logged as {primary_cause}",
                "severity": disruption_info["severity"] if disruption_info else "Major",
                "confidence": 0.95,
                "attributed_primary": True
            })

        has_uncertainty = len(candidate_causes) > 1

        # Calculate high level scope
        affected_shipments = casc_subset["affected_shipment_id"].nunique()
        affected_shp_ids = casc_subset["affected_shipment_id"].unique()
        affected_locations = self.shipments.loc[self.shipments["shipment_id"].isin(affected_shp_ids), "origin_location_id"].nunique()

        return {
            "cascade_id": cascade_id,
            "root_cause": primary_cause,
            "root_location_id": root_location_id,
            "root_location_name": f"{loc_name} ({loc_city})" if loc_city else loc_name,
            "root_timestamp": root_timestamp,
            "root_shipment_id": root_shipment_id,
            "initial_delay_minutes": initial_delay_minutes,
            "initial_impact_formatted": self._format_duration(initial_delay_minutes),
            "disruption_details": disruption_info,
            "candidate_causes": candidate_causes,
            "attribution_uncertainty": has_uncertainty,
            "confidence_score": 0.95 if not has_uncertainty else 0.85,
            "affected_shipments_count": affected_shipments,
            "affected_locations_count": affected_locations,
            "summary": (
                f"Cascade originated at {loc_name} on {root_timestamp} impacting {root_shipment_id} "
                f"with an initial delay of {self._format_duration(initial_delay_minutes)} due to {primary_cause}."
            )
        }

    def trace_shipment_root_cause(self, shipment_id: str) -> Dict[str, Any]:
        """
        Traces back the original root cause for an individual delayed shipment.
        Identifies whether the shipment is the root or downstream beneficiary of delay.
        """
        if shipment_id not in self.shipments.index:
            return {"error": f"Shipment {shipment_id} not found."}

        shp = self.shipments.loc[shipment_id]
        final_delay = int(shp["final_delay_minutes"])
        
        if final_delay <= 15:
            return {
                "shipment_id": shipment_id,
                "is_delayed": False,
                "delay_minutes": final_delay,
                "root_cause": "N/A - Shipment on time"
            }

        # Check cascade membership
        casc_records = self.cascades[self.cascades["affected_shipment_id"] == shipment_id]
        if not casc_records.empty:
            primary_rec = casc_records.sort_values(by="cascade_level").iloc[0]
            cascade_id = primary_rec["cascade_id"]
            is_root = bool(primary_rec["is_root_cause"])
            root_analysis = self.analyze_cascade(cascade_id)

            return {
                "shipment_id": shipment_id,
                "is_delayed": True,
                "final_delay_minutes": final_delay,
                "is_root_cause": is_root,
                "cascade_id": cascade_id,
                "cascade_depth": int(primary_rec["cascade_level"]),
                "direct_delay_minutes": int(primary_rec["direct_delay_minutes"]),
                "propagated_delay_minutes": int(primary_rec["propagated_delay_minutes"]),
                "root_cause": root_analysis["root_cause"],
                "origin_shipment_id": root_analysis["root_shipment_id"],
                "origin_location": root_analysis["root_location_name"],
                "origin_timestamp": root_analysis["root_timestamp"],
                "attribution_summary": (
                    f"Shipment is the primary root cause of Cascade {cascade_id} ({root_analysis['root_cause']})."
                    if is_root else
                    f"Delayed by upstream Cascade {cascade_id} originating from {root_analysis['root_shipment_id']} at {root_analysis['root_location_name']}."
                )
            }

        # Isolated delay
        primary_reason = str(shp["root_cause_category"]) if pd.notna(shp["root_cause_category"]) else "Local Operational Delay"
        return {
            "shipment_id": shipment_id,
            "is_delayed": True,
            "final_delay_minutes": final_delay,
            "is_root_cause": False,
            "cascade_id": None,
            "cascade_depth": 0,
            "direct_delay_minutes": final_delay,
            "propagated_delay_minutes": 0,
            "root_cause": primary_reason,
            "origin_shipment_id": shipment_id,
            "origin_location": str(shp["origin_location_id"]),
            "origin_timestamp": str(shp["actual_departure"]),
            "attribution_summary": f"Independent local delay of {self._format_duration(final_delay)} caused by {primary_reason} with no upstream cascade."
        }
