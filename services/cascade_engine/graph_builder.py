"""
Cascading Delay Intelligence - Logistics Graph Builder
Constructs a directed logistics dependency graph from shipments, dependencies, and locations.
Provides graph traversal, downstream impact propagation tracing, and upstream root tracing.
"""

import os
from typing import Dict, List, Any, Optional, Set, Tuple
import pandas as pd

class LogisticsGraph:
    """Directed dependency graph representing the logistics network."""

    def __init__(self, data_dir: str = "cascading-delay-dataset/data"):
        self.data_dir = data_dir
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[str, List[Dict[str, Any]]] = {} # node_id -> list of outgoing edges
        self.reverse_edges: Dict[str, List[Dict[str, Any]]] = {} # node_id -> list of incoming edges
        self._load_and_build()

    def _load_and_build(self):
        shipments_path = os.path.join(self.data_dir, "shipments.csv")
        dependencies_path = os.path.join(self.data_dir, "dependencies.csv")
        locations_path = os.path.join(self.data_dir, "locations.csv")
        disruptions_path = os.path.join(self.data_dir, "disruptions.csv")

        shipments = pd.read_csv(shipments_path)
        dependencies = pd.read_csv(dependencies_path)
        locations = pd.read_csv(locations_path)
        disruptions = pd.read_csv(disruptions_path)

        # 1. Add Location Nodes
        for _, loc in locations.iterrows():
            loc_id = loc["location_id"]
            self.nodes[loc_id] = {
                "id": loc_id,
                "type": "location",
                "name": loc["location_name"],
                "city": loc["city"],
                "state": loc["state"],
                "region": loc["region"],
                "capacity": loc["capacity"],
                "avg_processing_time": loc["average_processing_time_minutes"],
                "delay": 0
            }
            self.edges[loc_id] = []
            self.reverse_edges[loc_id] = []

        # 2. Add Shipment Nodes
        for _, shp in shipments.iterrows():
            s_id = shp["shipment_id"]
            self.nodes[s_id] = {
                "id": s_id,
                "type": "shipment",
                "shipment_id": s_id,
                "order_id": shp["order_id"],
                "origin_location_id": shp["origin_location_id"],
                "destination_location_id": shp["destination_location_id"],
                "vehicle_id": shp["assigned_vehicle_id"],
                "priority": shp["priority"],
                "cargo_type": shp["cargo_type"],
                "planned_departure": shp["planned_departure"],
                "actual_departure": shp["actual_departure"],
                "planned_arrival": shp["planned_arrival"],
                "actual_arrival": shp["actual_arrival"],
                "initial_delay_minutes": int(shp["initial_delay_minutes"]),
                "final_delay_minutes": int(shp["final_delay_minutes"]),
                "delay_status": shp["delay_status"],
                "status": shp["status"],
                "cascade_level": int(shp["cascade_level"]),
                "will_cascade": int(shp["will_cascade"]),
                "delay": int(shp["final_delay_minutes"])
            }
            self.edges[s_id] = []
            self.reverse_edges[s_id] = []

        # 3. Add Disruption Nodes
        for _, dis in disruptions.iterrows():
            d_id = dis["disruption_id"]
            self.nodes[d_id] = {
                "id": d_id,
                "type": "disruption",
                "disruption_type": dis["disruption_type"],
                "location_id": dis["location_id"],
                "vehicle_id": dis["vehicle_id"] if pd.notna(dis["vehicle_id"]) else None,
                "start_time": dis["start_time"],
                "end_time": dis["end_time"],
                "severity": dis["severity"],
                "description": dis["description"],
                "root_cause": dis["root_cause"],
                "affected_capacity_percentage": float(dis["affected_capacity_percentage"]),
                "delay": 0
            }
            self.edges[d_id] = []
            self.reverse_edges[d_id] = []

            # Edge from Disruption -> Location
            self._add_edge(d_id, dis["location_id"], {
                "dependency_type": "Disruption Origin Site",
                "delay": 0
            })

        # 4. Add Shipment -> Location edges (Routing)
        for _, shp in shipments.iterrows():
            s_id = shp["shipment_id"]
            # Origin -> Shipment
            self._add_edge(shp["origin_location_id"], s_id, {
                "dependency_type": "Shipment Origin Dispatch",
                "planned_time": shp["planned_departure"],
                "actual_time": shp["actual_departure"],
                "delay": int(shp["initial_delay_minutes"])
            })
            # Shipment -> Destination
            self._add_edge(s_id, shp["destination_location_id"], {
                "dependency_type": "Shipment Destination Arrival",
                "planned_time": shp["planned_arrival"],
                "actual_time": shp["actual_arrival"],
                "delay": int(shp["final_delay_minutes"])
            })

        # 5. Add Operational Dependency Edges (Shipment -> Shipment)
        for _, dep in dependencies.iterrows():
            up_id = dep["upstream_shipment_id"]
            down_id = dep["downstream_shipment_id"]
            if up_id in self.nodes and down_id in self.nodes:
                self._add_edge(up_id, down_id, {
                    "dependency_id": dep["dependency_id"],
                    "dependency_type": dep["dependency_type"],
                    "upstream_location_id": dep["upstream_location_id"],
                    "downstream_location_id": dep["downstream_location_id"],
                    "planned_time": dep["planned_dependency_time"],
                    "actual_time": dep["actual_dependency_time"],
                    "delay": int(dep["dependency_delay_minutes"]),
                    "dependency_status": dep["dependency_status"],
                    "cascade_id": dep["cascade_id"] if pd.notna(dep["cascade_id"]) else None
                })

    def _add_edge(self, source_id: str, target_id: str, edge_data: Dict[str, Any]):
        edge = {
            "source": source_id,
            "target": target_id,
            **edge_data
        }
        self.edges[source_id].append(edge)
        self.reverse_edges[target_id].append(edge)

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.nodes.get(node_id)

    def get_downstream_shipments(self, shipment_id: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Returns direct downstream dependent shipments and edge metadata."""
        downstreams = []
        for edge in self.edges.get(shipment_id, []):
            target = edge["target"]
            if target in self.nodes and self.nodes[target]["type"] == "shipment":
                downstreams.append((target, edge))
        return downstreams

    def get_upstream_shipments(self, shipment_id: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Returns direct upstream shipments feeding this shipment."""
        upstreams = []
        for edge in self.reverse_edges.get(shipment_id, []):
            source = edge["source"]
            if source in self.nodes and self.nodes[source]["type"] == "shipment":
                upstreams.append((source, edge))
        return upstreams

    def trace_downstream_cascade_path(self, root_shipment_id: str, max_depth: int = 5) -> List[Dict[str, Any]]:
        """Traverses the graph downstream to trace the complete propagation tree."""
        visited: Set[str] = set()
        path: List[Dict[str, Any]] = []

        def dfs(current_id: str, current_depth: int, parent_id: Optional[str] = None):
            if current_id in visited or current_depth > max_depth:
                return
            visited.add(current_id)
            node_data = self.nodes.get(current_id, {})
            path.append({
                "shipment_id": current_id,
                "parent_id": parent_id,
                "depth": current_depth,
                "final_delay_minutes": node_data.get("final_delay_minutes", 0),
                "origin_location_id": node_data.get("origin_location_id"),
                "destination_location_id": node_data.get("destination_location_id")
            })
            for down_id, edge in self.get_downstream_shipments(current_id):
                dfs(down_id, current_depth + 1, current_id)

        dfs(root_shipment_id, 0)
        return path

    def trace_upstream_root_path(self, shipment_id: str, max_depth: int = 5) -> List[str]:
        """Traces upstream feeder line to discover the original root shipment."""
        current = shipment_id
        ancestors = [current]
        visited = {current}

        while len(ancestors) <= max_depth:
            upstreams = self.get_upstream_shipments(current)
            if not upstreams:
                break
            # Pick upstream with highest delay or earliest timestamp
            best_upstream = max(upstreams, key=lambda x: self.nodes.get(x[0], {}).get("final_delay_minutes", 0))
            next_id = best_upstream[0]
            if next_id in visited:
                break
            visited.add(next_id)
            ancestors.append(next_id)
            current = next_id

        return ancestors # [leaf, parent, grandparent, ..., root]

# Alias for compatibility
LogisticsGraphBuilder = LogisticsGraph
