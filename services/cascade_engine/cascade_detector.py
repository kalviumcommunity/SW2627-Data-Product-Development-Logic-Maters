"""
Cascading Delay Intelligence - Cascade Detection & Propagation Engine
Detects, classifies, and reconstructs delay propagation chains.
Distinguishes:
1. Root Delay: Initiated directly by an operational or external disruption.
2. Propagated Delay: Transmitted downstream across an operational dependency.
3. Independent Delay: Local operational variance without upstream dependency evidence.
"""

import os
from typing import Dict, List, Any, Optional, Set
import pandas as pd
from datetime import datetime

class CascadeDetector:
    """Detection engine for cascading delays across dependencies."""

    def __init__(self, data_dir: str = "cascading-delay-dataset/data"):
        self.data_dir = data_dir
        self.shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv")).set_index("shipment_id", drop=False)
        self.dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))
        self.disruptions = pd.read_csv(os.path.join(data_dir, "disruptions.csv")).set_index("disruption_id", drop=False)
        self.cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))

    def classify_delay_nature(self, shipment_id: str) -> Dict[str, Any]:
        """
        Classifies whether a shipment's delay is Root, Propagated, or Independent.
        Requires evidence:
        1. Upstream delay exists (> 15m)
        2. Downstream depends on upstream
        3. Downstream departure happens after upstream arrival
        4. Dependency delay explains the downstream delay
        """
        if shipment_id not in self.shipments.index:
            return {"nature": "Unknown", "shipment_id": shipment_id, "explanation": "Shipment not found."}

        shp = self.shipments.loc[shipment_id]
        final_delay = int(shp["final_delay_minutes"])
        initial_delay = int(shp["initial_delay_minutes"])

        if final_delay <= 15:
            return {
                "nature": "On-Time",
                "shipment_id": shipment_id,
                "delay_minutes": final_delay,
                "explanation": "Shipment completed on time within standard operational tolerances."
            }

        # Check if shipment is part of cascade_events
        cas_records = self.cascades[self.cascades["affected_shipment_id"] == shipment_id]
        if not cas_records.empty:
            root_rec = cas_records[cas_records["is_root_cause"] == True]
            if not root_rec.empty:
                r = root_rec.iloc[0]
                return {
                    "nature": "Root Delay",
                    "shipment_id": shipment_id,
                    "delay_minutes": final_delay,
                    "cascade_id": r["cascade_id"],
                    "disruption_id": r["disruption_id"],
                    "root_cause": r["root_cause"],
                    "explanation": f"Delay of {final_delay}m originated from primary disruption ({r['root_cause']})."
                }
            prop_rec = cas_records[cas_records["is_propagated"] == True]
            if not prop_rec.empty:
                p = prop_rec.iloc[0]
                parent_id = p["parent_shipment_id"] if pd.notna(p["parent_shipment_id"]) else None
                return {
                    "nature": "Propagated Delay",
                    "shipment_id": shipment_id,
                    "delay_minutes": final_delay,
                    "parent_shipment_id": parent_id,
                    "cascade_id": p["cascade_id"],
                    "cascade_depth": int(p["cascade_level"]),
                    "cascade_level": int(p["cascade_level"]),
                    "transmitted_delay_minutes": int(p["propagated_delay_minutes"]),
                    "explanation": f"Delay of {final_delay}m was inherited from upstream cascade {p['cascade_id']} (parent: {parent_id})."
                }

        # Check incoming dependencies
        incoming_deps = self.dependencies[self.dependencies["downstream_shipment_id"] == shipment_id]
        for _, dep in incoming_deps.iterrows():
            up_id = dep["upstream_shipment_id"]
            if up_id in self.shipments.index:
                up_shp = self.shipments.loc[up_id]
                up_delay = int(up_shp["final_delay_minutes"])
                dep_delay = int(dep["dependency_delay_minutes"])

                # Causal test: Upstream was delayed AND imparted delay to downstream
                if up_delay > 15 and dep_delay > 0:
                    cas_id = dep["cascade_id"] if pd.notna(dep["cascade_id"]) else None
                    return {
                        "nature": "Propagated Delay",
                        "shipment_id": shipment_id,
                        "delay_minutes": final_delay,
                        "parent_shipment_id": up_id,
                        "upstream_delay_minutes": up_delay,
                        "transmitted_delay_minutes": dep_delay,
                        "dependency_type": dep["dependency_type"],
                        "cascade_id": cas_id,
                        "explanation": f"Delay of {final_delay}m was inherited from upstream feeder {up_id} via {dep['dependency_type']}."
                    }

        # If delayed but no upstream dependency explains it, it's an Independent Delay
        return {
            "nature": "Independent Delay",
            "shipment_id": shipment_id,
            "delay_minutes": final_delay,
            "explanation": f"Localized delay of {final_delay}m occurred without upstream dependency transmission."
        }

    def reconstruct_cascade_tree(self, cascade_id: str) -> Optional[Dict[str, Any]]:
        """Reconstructs the full multi-echelon propagation tree for a cascade."""
        cas_rows = self.cascades[self.cascades["cascade_id"] == cascade_id]
        if cas_rows.empty:
            return None

        disr_id = cas_rows["disruption_id"].iloc[0]
        disr_row = self.disruptions.loc[disr_id] if disr_id in self.disruptions.index else None
        root_shipment_id = cas_rows["root_shipment_id"].iloc[0]

        # Organize by echelon level
        levels_map: Dict[int, List[Dict[str, Any]]] = {}
        affected_shipments = cas_rows["affected_shipment_id"].unique()

        for sid in affected_shipments:
            s_rows = cas_rows[cas_rows["affected_shipment_id"] == sid]
            lvl = int(s_rows["cascade_level"].iloc[0])
            if lvl not in levels_map:
                levels_map[lvl] = []

            shp_row = self.shipments.loc[sid] if sid in self.shipments.index else {}
            parent_id = s_rows["parent_shipment_id"].dropna().iloc[0] if len(s_rows["parent_shipment_id"].dropna()) > 0 else None

            levels_map[lvl].append({
                "shipment_id": sid,
                "parent_shipment_id": parent_id,
                "cascade_level": lvl,
                "origin_location_id": shp_row.get("origin_location_id") if isinstance(shp_row, dict) else shp_row["origin_location_id"],
                "destination_location_id": shp_row.get("destination_location_id") if isinstance(shp_row, dict) else shp_row["destination_location_id"],
                "total_delay_minutes": int(s_rows["total_delay_minutes"].iloc[0]),
                "primary_propagation_type": s_rows["propagation_type"].iloc[0]
            })

        return {
            "cascade_id": cascade_id,
            "disruption_id": disr_id,
            "root_cause": disr_row["root_cause"] if disr_row is not None else cas_rows["root_cause"].iloc[0],
            "root_shipment_id": root_shipment_id,
            "max_depth": int(cas_rows["cascade_level"].max()),
            "total_affected_shipments": len(affected_shipments),
            "echelons": levels_map
        }

    def detect_all_cascades(self) -> List[Dict[str, Any]]:
        """Returns summarized metadata for all active cascade trees in the dataset."""
        unique_cascades = self.cascades["cascade_id"].unique()
        summaries = []
        for cid in sorted(unique_cascades):
            tree = self.reconstruct_cascade_tree(cid)
            if tree:
                summaries.append(tree)
        return summaries
