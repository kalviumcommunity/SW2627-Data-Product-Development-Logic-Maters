"""
Cascading Delay Intelligence - Shipment Intelligence Service
Generates deep operational narratives, delay attribution, and event histories for individual shipments.
Conforms strictly to verified dataset schema.
"""

import os
from typing import Dict, List, Any, Optional
import pandas as pd

from services.cascade_engine.cascade_detector import CascadeDetector
from services.cascade_engine.root_cause_analyzer import RootCauseAnalyzer
from services.cascade_engine.risk_analyzer import RiskAnalyzer
from services.intelligence.schemas.models import ShipmentStory, ShipmentTimelineEvent

class ShipmentIntelligence:
    """Provides complete context, causal breakdown, and narrative explanation for any shipment."""

    def __init__(self, data_dir: str = "cascading-delay-dataset/data"):
        self.data_dir = data_dir
        self.detector = CascadeDetector(data_dir=data_dir)
        self.rc_analyzer = RootCauseAnalyzer(data_dir=data_dir)
        self.risk_analyzer = RiskAnalyzer(data_dir=data_dir)

        self.shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv")).set_index("shipment_id", drop=False)
        self.events = pd.read_csv(os.path.join(data_dir, "logistics_events.csv"))
        self.locations = pd.read_csv(os.path.join(data_dir, "locations.csv")).set_index("location_id", drop=False)
        self.dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))
        self.deliveries = pd.read_csv(os.path.join(data_dir, "deliveries.csv")).set_index("shipment_id", drop=False)
        self.cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))

    def _get_loc_name(self, loc_id: str) -> str:
        if loc_id in self.locations.index:
            row = self.locations.loc[loc_id]
            return f"{row['location_name']} ({row['city']})"
        return str(loc_id)

    def build_shipment_story(self, shipment_id: str) -> ShipmentStory:
        """
        Builds a comprehensive ShipmentStory with event timeline, causal attribution, and risks.
        """
        if shipment_id not in self.shipments.index:
            raise ValueError(f"Shipment {shipment_id} not found.")

        shp = self.shipments.loc[shipment_id]
        final_delay = int(shp["final_delay_minutes"])
        
        # 1. Causal delay nature
        nature_info = self.detector.classify_delay_nature(shipment_id)
        delay_nature = nature_info["nature"]
        cascade_id = nature_info.get("cascade_id")

        # 2. Reconstruct event timeline
        shp_events = self.events[self.events["shipment_id"] == shipment_id].sort_values(by="scheduled_timestamp")
        timeline: List[ShipmentTimelineEvent] = []

        for _, ev in shp_events.iterrows():
            loc_str = self._get_loc_name(ev["location_id"])
            ev_type = str(ev["event_type"])
            ev_delay = int(ev["delay_minutes"])
            ev_status = str(ev["event_status"])

            if ev_delay <= 0:
                explanation = f"Completed {ev_type.lower()} on schedule at {loc_str}."
            elif ev_delay <= 15:
                explanation = f"Completed {ev_type.lower()} at {loc_str} with minor {ev_delay}m delay, within operational buffer."
            else:
                hours = ev_delay // 60
                mins = ev_delay % 60
                time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
                explanation = f"{ev_type} at {loc_str} delayed by {time_str} ({ev_status})."

            timeline.append(ShipmentTimelineEvent(
                eventId=str(ev["event_id"]),
                eventType=ev_type,
                locationName=loc_str,
                timestamp=str(ev["actual_timestamp"] if pd.notna(ev["actual_timestamp"]) else ev["scheduled_timestamp"]),
                delayMinutes=ev_delay,
                status=ev_status,
                humanExplanation=explanation
            ))

        # 3. Upstream & Downstream Dependencies
        upstream_deps = []
        for _, u in self.dependencies[self.dependencies["downstream_shipment_id"] == shipment_id].iterrows():
            upstream_deps.append({
                "upstream_shipment_id": str(u["upstream_shipment_id"]),
                "dependency_type": str(u["dependency_type"]),
                "transfer_location": self._get_loc_name(u["upstream_location_id"]),
                "planned_time": str(u["planned_dependency_time"]),
                "actual_time": str(u["actual_dependency_time"]),
                "dependency_delay_minutes": int(u["dependency_delay_minutes"]),
                "dependency_status": str(u["dependency_status"])
            })

        downstream_deps = []
        for _, d in self.dependencies[self.dependencies["upstream_shipment_id"] == shipment_id].iterrows():
            downstream_deps.append({
                "downstream_shipment_id": str(d["downstream_shipment_id"]),
                "dependency_type": str(d["dependency_type"]),
                "transfer_location": self._get_loc_name(d["downstream_location_id"]),
                "planned_time": str(d["planned_dependency_time"]),
                "actual_time": str(d["actual_dependency_time"]),
                "dependency_delay_minutes": int(d["dependency_delay_minutes"]),
                "dependency_status": str(d["dependency_status"])
            })

        # 4. Delivery Status & SLA
        delivery_info = {}
        if shipment_id in self.deliveries.index:
            d_row = self.deliveries.loc[shipment_id]
            if isinstance(d_row, pd.DataFrame):
                d_row = d_row.iloc[0]
            deliv_delay = int(d_row["delay_minutes"])
            delivery_info = {
                "delivery_id": str(d_row["delivery_id"]),
                "order_id": str(d_row["order_id"]),
                "promised_delivery_time": str(d_row["promised_delivery_time"]),
                "actual_delivery_time": str(d_row["actual_delivery_time"]),
                "delivery_status": str(d_row["delivery_status"]),
                "customer_sla_met": str(d_row["delivery_status"]) == "Delivered On Time" and deliv_delay == 0,
                "at_risk": bool(d_row["at_risk"]),
                "delay_minutes": deliv_delay,
                "risk_reason": str(d_row["risk_reason"])
            }

        # 5. Risk Assessment
        risk_profile = self.risk_analyzer.analyze_shipment_risk(shipment_id)

        # 6. Overall Narrative Delay Explanation
        if delay_nature == "On-Time":
            delay_narrative = f"Shipment arrived on time with a variance of {final_delay}m, successfully meeting delivery promises."
        elif delay_nature == "Root Delay":
            root_info = self.rc_analyzer.trace_shipment_root_cause(shipment_id)
            delay_narrative = (
                f"Shipment is the root trigger of Cascade {cascade_id}. Primary cause was {root_info['root_cause']}, "
                f"introducing {final_delay}m of direct delay that propagated downstream to connecting legs."
            )
        elif delay_nature == "Propagated Delay":
            root_info = self.rc_analyzer.trace_shipment_root_cause(shipment_id)
            delay_narrative = (
                f"Shipment suffered {final_delay}m of delay as part of Cascade {cascade_id}. It was delayed primarily by waiting "
                f"for upstream feeder shipment at transfer points, absorbing {nature_info.get('transmitted_delay_minutes', 0)}m of propagated delay."
            )
        else:
            delay_narrative = f"Shipment incurred an independent local delay of {final_delay}m without significant upstream cascade dependencies."

        return ShipmentStory(
            shipmentId=shipment_id,
            originLocation=self._get_loc_name(shp["origin_location_id"]),
            destinationLocation=self._get_loc_name(shp["destination_location_id"]),
            plannedDeparture=str(shp["planned_departure"]),
            actualDeparture=str(shp["actual_departure"]),
            plannedArrival=str(shp["planned_arrival"]),
            actualArrival=str(shp["actual_arrival"]),
            status=str(shp["status"]),
            priority=str(shp["priority"]),
            delayNature=delay_nature,
            finalDelayMinutes=final_delay,
            delayExplanation=delay_narrative,
            cascadeId=cascade_id,
            timeline=timeline,
            upstreamDependencies=upstream_deps,
            downstreamDependencies=downstream_deps,
            deliveryStatus=delivery_info,
            riskProfile=risk_profile
        )
