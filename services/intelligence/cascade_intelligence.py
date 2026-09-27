"""
Cascading Delay Intelligence - Cascade Intelligence Service
Synthesizes root cause analysis, downstream impact propagation, risk indicators,
and deterministic human-readable narratives into a complete CascadeStory.
Conforms strictly to verified dataset schema.
"""

import os
from typing import Dict, List, Any, Optional
import pandas as pd
from datetime import datetime

from services.cascade_engine.root_cause_analyzer import RootCauseAnalyzer
from services.cascade_engine.impact_analyzer import ImpactAnalyzer
from services.cascade_engine.risk_analyzer import RiskAnalyzer
from services.cascade_engine.cascade_detector import CascadeDetector
from services.intelligence.schemas.models import (
    CascadeStory,
    CascadeSummary,
    CascadeRootCause,
    CascadeTimelineItem,
    CascadePropagationNode,
    CascadeImpact,
    CascadeExplanation
)

class CascadeIntelligence:
    """Produces end-to-end, human-readable intelligence for cascading delay networks."""

    def __init__(self, data_dir: str = "cascading-delay-dataset/data"):
        self.data_dir = data_dir
        self.rc_analyzer = RootCauseAnalyzer(data_dir=data_dir)
        self.impact_analyzer = ImpactAnalyzer(data_dir=data_dir)
        self.risk_analyzer = RiskAnalyzer(data_dir=data_dir)
        self.detector = CascadeDetector(data_dir=data_dir)

        self.locations = pd.read_csv(os.path.join(data_dir, "locations.csv")).set_index("location_id", drop=False)
        self.shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv")).set_index("shipment_id", drop=False)
        self.cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))
        self.dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))
        self.events = pd.read_csv(os.path.join(data_dir, "logistics_events.csv"))

    def _get_loc_name(self, loc_id: str) -> str:
        if loc_id in self.locations.index:
            row = self.locations.loc[loc_id]
            return f"{row['location_name']} ({row['city']})"
        return str(loc_id)

    def build_cascade_story(self, cascade_id: str) -> CascadeStory:
        """
        Builds the complete unified CascadeStory object for an identified cascade.
        """
        rc = self.rc_analyzer.analyze_cascade(cascade_id)
        if "error" in rc:
            raise ValueError(rc["error"])

        impact = self.impact_analyzer.analyze_cascade_impact(cascade_id)

        # 1. Timeline Reconstruction from Cascade Events + Shipments
        casc_subset = self.cascades[self.cascades["cascade_id"] == cascade_id].sort_values(by=["cascade_level"])
        timeline_items: List[CascadeTimelineItem] = []

        for _, row in casc_subset.iterrows():
            shp_id = str(row["affected_shipment_id"])
            shp_info = self.shipments.loc[shp_id] if shp_id in self.shipments.index else None
            loc_id = str(shp_info["origin_location_id"]) if shp_info is not None else "LOC-UNKNOWN"
            loc_name = self._get_loc_name(loc_id)
            timestamp = str(shp_info["actual_departure"]) if shp_info is not None else str(rc["root_timestamp"])
            prop_type = str(row["propagation_type"])
            tot_delay = int(row["total_delay_minutes"])
            prop_delay = int(row["propagated_delay_minutes"])
            is_root = bool(row["is_root_cause"])

            if is_root:
                desc = f"Initial disruption ({row['root_cause']}) triggered direct delay of {tot_delay}m on origin shipment {shp_id}."
            elif prop_type == "Departure Delay":
                desc = f"Shipment {shp_id} departed {loc_name} delayed by {tot_delay}m after waiting {prop_delay}m for incoming transfer."
            elif prop_type == "Customer Delivery Risk":
                desc = f"Downstream customer delivery for {shp_id} flagged with {tot_delay}m cumulative delay at destination."
            else:
                desc = f"Cross-dock transfer milestone '{prop_type}' logged at {loc_name} with {tot_delay}m delay."

            timeline_items.append(CascadeTimelineItem(
                timestamp=timestamp,
                eventType=prop_type,
                locationName=loc_name,
                shipmentId=shp_id,
                delayMinutes=tot_delay,
                description=desc
            ))

        # 2. Propagation Graph Nodes
        propagation_nodes: List[CascadePropagationNode] = []
        for shp_id in impact["affected_shipment_ids"]:
            shp_events = casc_subset[casc_subset["affected_shipment_id"] == shp_id]
            if shp_events.empty:
                continue
            rep_event = shp_events.iloc[0]
            shp_info = self.shipments.loc[shp_id] if shp_id in self.shipments.index else None

            parent_id = str(rep_event["parent_shipment_id"]) if pd.notna(rep_event["parent_shipment_id"]) else None
            dep_type = str(rep_event["propagation_type"])

            propagation_nodes.append(CascadePropagationNode(
                shipmentId=shp_id,
                depth=int(rep_event["cascade_level"]),
                originLocation=str(shp_info["origin_location_id"]) if shp_info is not None else "Unknown",
                destinationLocation=str(shp_info["destination_location_id"]) if shp_info is not None else "Unknown",
                directDelayMinutes=int(rep_event["direct_delay_minutes"]),
                propagatedDelayMinutes=int(rep_event["propagated_delay_minutes"]),
                totalDelayMinutes=int(rep_event["total_delay_minutes"]),
                parentShipmentId=parent_id if parent_id != shp_id else None,
                dependencyType=dep_type,
                status=str(shp_info["status"]) if shp_info is not None else "Delivered"
            ))

        # 3. Risks of Affected Shipments
        risks_list: List[Dict[str, Any]] = []
        for shp_id in impact["affected_shipment_ids"]:
            r_obj = self.risk_analyzer.analyze_shipment_risk(shp_id)
            if "error" not in r_obj:
                risks_list.append(r_obj)

        risks_list.sort(key=lambda x: x["risk_score"], reverse=True)

        # 4. Deterministic Natural-Language Explanations
        root_cause_type = rc["root_cause"]
        root_loc_str = rc["root_location_name"]
        root_shp = rc["root_shipment_id"]
        init_delay_fmt = rc["initial_impact_formatted"]
        aff_shp_count = impact["affected_shipments"]
        aff_loc_count = impact["affected_locations"]
        at_risk_deliv = impact["deliveries_at_risk"]
        total_deliv = impact["affected_deliveries"]
        prop_hours = round(impact["propagated_delay_minutes"] / 60.0, 1)
        tot_hours = round(impact["total_delay_minutes"] / 60.0, 1)

        second_hop_str = ""
        downstream_nodes = [n for n in propagation_nodes if n.depth == 1]
        if downstream_nodes:
            downstream_sample = downstream_nodes[0]
            second_hop_str = f" Because downstream transfers were waiting for {root_shp} at {root_loc_str}, connected leg {downstream_sample.shipmentId} absorbed {downstream_sample.propagatedDelayMinutes}m of wait time before departure."

        what_happened = (
            f"A {root_cause_type} disruption at {root_loc_str} initially delayed shipment {root_shp} by {init_delay_fmt}."
            f"{second_hop_str} The delay subsequently propagated across cross-docking transfers reaching depth {impact['cascade_depth']}."
        )

        why_it_matters = (
            f"This disruption did not remain isolated. It cascaded into {aff_shp_count} shipments across {aff_loc_count} operational facilities, "
            f"generating {prop_hours} hours of propagated delay ({tot_hours} total delay hours). {at_risk_deliv} of {total_deliv} downstream customer deliveries "
            f"breached promised SLA arrival windows."
        )

        if impact["status"] == "ACTIVE":
            current_risk = (
                f"Cascade is currently ACTIVE. {len(risks_list)} connected shipments exhibit high vulnerability scores. "
                f"Without buffer replenishment or expedited routing at transfer hubs, further downstream deliveries will experience SLA failures."
            )
            recommended_action = (
                f"Prioritize cross-dock clearance for {impact['highest_impact_shipment']['shipment_id']}. "
                f"Inject buffer recovery at {impact['most_affected_location']['location_name']} to sever downstream propagation."
            )
        else:
            current_risk = (
                f"Cascade cycle completed. {at_risk_deliv} deliveries experienced late delivery penalties. "
                f"The highest accumulated delay was {impact['highest_impact_shipment']['delay_minutes']}m on {impact['highest_impact_shipment']['shipment_id']}."
            )
            recommended_action = (
                f"Conduct post-incident review at {root_loc_str}. "
                f"Adjust transfer buffer thresholds at {impact['most_affected_location']['location_name']} to prevent future dependency lockouts."
            )

        explanation = CascadeExplanation(
            whatHappened=what_happened,
            whyItMatters=why_it_matters,
            currentRisk=current_risk,
            recommendedAction=recommended_action
        )

        # 5. Assemble CascadeStory
        story = CascadeStory(
            cascadeId=cascade_id,
            summary=CascadeSummary(
                title=f"{root_cause_type} at {rc['root_location_id']} propagating to {aff_shp_count} shipments",
                severity=impact["severity"],
                affectedShipments=aff_shp_count,
                affectedDeliveries=total_deliv,
                affectedLocations=aff_loc_count,
                propagatedDelayHours=prop_hours,
                totalDelayHours=tot_hours,
                status=impact["status"]
            ),
            rootCause=CascadeRootCause(
                type=rc["root_cause"],
                locationId=rc["root_location_id"],
                locationName=rc["root_location_name"],
                timestamp=rc["root_timestamp"],
                initialShipmentId=rc["root_shipment_id"],
                initialDelayMinutes=rc["initial_delay_minutes"],
                initialDelayFormatted=rc["initial_impact_formatted"],
                attributionUncertainty=rc["attribution_uncertainty"],
                confidenceScore=rc["confidence_score"],
                candidateCauses=rc["candidate_causes"]
            ),
            timeline=timeline_items,
            propagation=propagation_nodes,
            impact=CascadeImpact(
                score=impact["impact_score"],
                severity=impact["severity"],
                affectedShipments=impact["affected_shipments"],
                affectedDeliveries=impact["affected_deliveries"],
                deliveriesAtRisk=impact["deliveries_at_risk"],
                affectedLocations=impact["affected_locations"],
                cascadeDepth=impact["cascade_depth"],
                durationMinutes=impact["cascade_duration_minutes"],
                initialDelayMinutes=impact["initial_delay_minutes"],
                propagatedDelayMinutes=impact["propagated_delay_minutes"],
                totalDelayMinutes=impact["total_delay_minutes"],
                highestImpactShipmentId=impact["highest_impact_shipment"]["shipment_id"],
                highestImpactDelayMinutes=impact["highest_impact_shipment"]["delay_minutes"],
                mostAffectedLocationName=impact["most_affected_location"]["location_name"],
                downstreamDependenciesCount=impact["downstream_dependencies_count"]
            ),
            risks=risks_list,
            explanation=explanation
        )

        return story

    def list_all_cascade_summaries(self) -> List[Dict[str, Any]]:
        """
        Returns high-level summary cards for all cascades in the dataset.
        """
        all_ids = self.cascades["cascade_id"].unique().tolist()
        summaries = []

        for cid in all_ids:
            try:
                impact = self.impact_analyzer.analyze_cascade_impact(cid)
                rc = self.rc_analyzer.analyze_cascade(cid)
                summaries.append({
                    "cascade_id": cid,
                    "title": f"{rc['root_cause']} at {rc['root_location_name']}",
                    "severity": impact["severity"],
                    "status": impact["status"],
                    "root_cause": rc["root_cause"],
                    "origin_location": rc["root_location_name"],
                    "origin_timestamp": rc["root_timestamp"],
                    "affected_shipments": impact["affected_shipments"],
                    "affected_locations": impact["affected_locations"],
                    "affected_deliveries": impact["affected_deliveries"],
                    "deliveries_at_risk": impact["deliveries_at_risk"],
                    "propagated_delay_hours": round(impact["propagated_delay_minutes"] / 60.0, 1),
                    "total_delay_hours": round(impact["total_delay_minutes"] / 60.0, 1),
                    "impact_score": impact["impact_score"]
                })
            except Exception:
                continue

        summaries.sort(key=lambda x: x["impact_score"], reverse=True)
        return summaries
