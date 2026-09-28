"""
Cascading Delay Intelligence - Risk Analyzer Engine
Calculates deterministic vulnerability and delay risk scores for shipments and deliveries.
Conforms strictly to verified dataset schema.
"""

import os
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

class RiskAnalyzer:
    """Calculates deterministic risk scores and identifies critical vulnerabilities."""

    def __init__(self, data_dir: str = "cascading-delay-dataset/data"):
        self.data_dir = data_dir
        self.shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv")).set_index("shipment_id", drop=False)
        self.deliveries = pd.read_csv(os.path.join(data_dir, "deliveries.csv")).set_index("shipment_id", drop=False)
        self.dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))
        self.cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))
        self.disruptions = pd.read_csv(os.path.join(data_dir, "disruptions.csv"))
        self.locations = pd.read_csv(os.path.join(data_dir, "locations.csv")).set_index("location_id", drop=False)

        # Precompute active hub disruptions
        self.active_disruptions_by_loc = self.disruptions.groupby("location_id")["disruption_id"].count().to_dict()

    def analyze_shipment_risk(self, shipment_id: str) -> Dict[str, Any]:
        """
        Evaluates risk indicators deterministically for a single shipment.
        """
        if shipment_id not in self.shipments.index:
            return {"error": f"Shipment {shipment_id} not found."}

        shp = self.shipments.loc[shipment_id]
        final_delay = int(shp["final_delay_minutes"])
        priority = str(shp["priority"]).upper()
        dest_loc = str(shp["destination_location_id"])
        orig_loc = str(shp["origin_location_id"])
        delivery_at_risk_flag = bool(shp["delivery_at_risk"] == 1)

        # Fetch delivery information
        deliv_row = None
        delivery_delay = 0
        sla_met = True
        at_risk_deliv = False
        buffer_consumed_pct = 0.0

        if shipment_id in self.deliveries.index:
            d_entry = self.deliveries.loc[shipment_id]
            if isinstance(d_entry, pd.DataFrame):
                d_entry = d_entry.iloc[0]
            deliv_row = d_entry
            delivery_delay = int(d_entry["delay_minutes"])
            at_risk_deliv = bool(d_entry["at_risk"])
            sla_met = str(d_entry["delivery_status"]) == "Delivered On Time" and delivery_delay == 0

            # Calculate buffer consumption
            try:
                promised_dt = pd.to_datetime(d_entry["promised_delivery_time"])
                planned_arr_dt = pd.to_datetime(shp["planned_arrival"])
                buffer_mins = max(15.0, (promised_dt - planned_arr_dt).total_seconds() / 60.0)
                buffer_consumed_pct = round(min((final_delay / buffer_mins) * 100.0, 150.0), 1)
            except Exception:
                buffer_consumed_pct = 100.0 if not sla_met else (50.0 if final_delay > 15 else 0.0)

        # Downstream dependencies count
        downstream_deps = self.dependencies[self.dependencies["upstream_shipment_id"] == shipment_id]
        num_downstream = len(downstream_deps)
        total_dep_delay = int(downstream_deps["dependency_delay_minutes"].sum()) if num_downstream > 0 else 0

        # Cascade participation
        casc_events = self.cascades[self.cascades["affected_shipment_id"] == shipment_id]
        cascade_depth = int(casc_events["cascade_level"].max()) if not casc_events.empty else 0
        in_cascade = not casc_events.empty

        # Hub congestion / disruptions
        has_dest_disruption = dest_loc in self.active_disruptions_by_loc
        has_orig_disruption = orig_loc in self.active_disruptions_by_loc

        # Deterministic Risk Scoring (0.00 to 1.00)
        # Factor 1: Buffer consumption / Delay severity (Weight 0.35)
        buffer_factor = min(buffer_consumed_pct / 100.0, 1.0) if buffer_consumed_pct > 0 else (min(final_delay / 90.0, 1.0) if final_delay > 0 else 0.0)

        # Factor 2: Downstream dependency fan-out (Weight 0.25)
        dep_factor = min(num_downstream / 3.0, 1.0)
        if total_dep_delay > 30 and num_downstream > 0:
            dep_factor = min(dep_factor + 0.2, 1.0)

        # Factor 3: Cascade propagation depth (Weight 0.20)
        cascade_factor = min(cascade_depth / 3.0, 1.0)

        # Factor 4: Priority & Hub risk (Weight 0.20)
        prio_base = 0.8 if priority in ["CRITICAL", "EXPRESS"] else 0.3
        hub_extra = 0.2 if (has_dest_disruption or has_orig_disruption) else 0.0
        prio_hub_factor = min(prio_base + hub_extra, 1.0)

        risk_score = (
            (buffer_factor * 0.35) +
            (dep_factor * 0.25) +
            (cascade_factor * 0.20) +
            (prio_hub_factor * 0.20)
        )
        risk_score = round(min(max(risk_score, 0.05), 1.0), 2)

        # Categorize
        if risk_score >= 0.75 or not sla_met or at_risk_deliv or delivery_at_risk_flag:
            risk_level = "CRITICAL" if not sla_met or risk_score >= 0.85 else "HIGH"
        elif risk_score >= 0.40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # Plain-English deterministic reasons
        reasons = []
        if not sla_met or delivery_delay > 0:
            reasons.append(f"Current delay has exhausted 100% of delivery buffer, breaching customer SLA window by {delivery_delay}m.")
        elif at_risk_deliv or delivery_at_risk_flag or buffer_consumed_pct >= 75.0:
            reasons.append(f"Delivery buffer is {buffer_consumed_pct}% consumed; minimal tolerance for further delays.")
        elif final_delay > 15:
            reasons.append(f"Shipment has accumulated {final_delay} minutes of operational transit delay.")

        if num_downstream > 0:
            reasons.append(f"Shipment holds up {num_downstream} downstream connecting shipments ({total_dep_delay}m transferred delay).")

        if cascade_depth >= 2:
            reasons.append(f"Actively propagating delay at cascade depth {cascade_depth}, multiplying downstream disruption.")
        elif in_cascade:
            reasons.append(f"Part of an active cascading delay chain.")

        if has_dest_disruption:
            reasons.append(f"Destination facility ({dest_loc}) has an active operational disruption.")

        if priority in ["CRITICAL", "EXPRESS"]:
            reasons.append(f"High cargo priority tier ({priority}) with zero fault tolerance.")

        if not reasons:
            reasons.append("Shipment is progressing within planned buffer tolerances with zero downstream blocks.")

        return {
            "shipment_id": shipment_id,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "is_deterministic_score": True,
            "reasons": reasons,
            "factors": {
                "buffer_erosion_score": round(buffer_factor, 2),
                "downstream_dependency_score": round(dep_factor, 2),
                "cascade_propagation_score": round(cascade_factor, 2),
                "priority_and_hub_congestion_score": round(prio_hub_factor, 2)
            },
            "metrics": {
                "current_delay_minutes": final_delay,
                "buffer_consumed_percentage": buffer_consumed_pct,
                "customer_sla_met": sla_met,
                "downstream_dependencies": num_downstream,
                "cascade_depth": cascade_depth,
                "priority": priority
            },
            "delivery_details": {
                "delivery_id": str(deliv_row["delivery_id"]) if deliv_row is not None else None,
                "order_id": str(deliv_row["order_id"]) if deliv_row is not None else None,
                "delivery_status": str(deliv_row["delivery_status"]) if deliv_row is not None else "Unknown",
                "risk_reason": str(deliv_row["risk_reason"]) if deliv_row is not None else ""
            }
        }

    def get_top_vulnerable_shipments(self, limit: int = 50, filter_level: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Scans shipments and returns the highest-risk shipments with full diagnostic context.
        """
        if not hasattr(self, "_risk_cache"):
            self._risk_cache = {}
        cache_key = (limit, filter_level)
        if cache_key in self._risk_cache:
            return self._risk_cache[cache_key]

        # Prioritize candidates by highest final delay, cascade participation, and delivery_at_risk
        top_delayed = self.shipments.sort_values(by=["delivery_at_risk", "final_delay_minutes"], ascending=[False, False])
        candidate_ids = top_delayed["shipment_id"].head(max(limit * 4, 100)).tolist()

        results = []
        for sid in candidate_ids:
            risk_obj = self.analyze_shipment_risk(sid)
            if "error" not in risk_obj:
                if filter_level and risk_obj["risk_level"] != filter_level:
                    continue
                results.append(risk_obj)

        results.sort(key=lambda x: x["risk_score"], reverse=True)
        self._risk_cache[cache_key] = results[:limit]
        return self._risk_cache[cache_key]
