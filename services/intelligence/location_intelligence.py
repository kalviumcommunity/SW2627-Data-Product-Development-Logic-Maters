"""
Cascading Delay Intelligence - Location Intelligence Service
Calculates hub performance KPIs, bottleneck diagnoses, and operational health narratives.
"""

import os
from typing import Dict, List, Any, Optional
import pandas as pd

from services.cascade_engine.impact_analyzer import ImpactAnalyzer
from services.intelligence.schemas.models import LocationStory

class LocationIntelligence:
    """Generates deep hub analytics, bottleneck classifications, and operational narratives."""

    def __init__(self, data_dir: str = "cascading-delay-dataset/data"):
        self.data_dir = data_dir
        self.impact_analyzer = ImpactAnalyzer(data_dir=data_dir)
        self.locations = pd.read_csv(os.path.join(data_dir, "locations.csv")).set_index("location_id", drop=False)
        self.shipments = pd.read_csv(os.path.join(data_dir, "shipments.csv"))
        self.cascades = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))
        self.disruptions = pd.read_csv(os.path.join(data_dir, "disruptions.csv"))
        self.dependencies = pd.read_csv(os.path.join(data_dir, "dependencies.csv"))

    def build_location_story(self, location_id: str) -> LocationStory:
        """
        Builds a comprehensive LocationStory with bottleneck scoring and narrative diagnostic.
        """
        if location_id not in self.locations.index:
            raise ValueError(f"Location {location_id} not found.")

        loc = self.locations.loc[location_id]
        loc_name = str(loc["location_name"])
        city = str(loc["city"])
        state = str(loc["state"])
        loc_type = str(loc["location_type"])

        # Fetch bottleneck analysis list
        bottlenecks = self.impact_analyzer.analyze_location_bottlenecks()
        loc_bn = next((b for b in bottlenecks if b["location_id"] == location_id), None)

        if not loc_bn:
            raise ValueError(f"Unable to compute bottleneck profile for {location_id}.")

        # Find active or historical cascades via shipments originating from this location
        loc_shps = self.shipments[self.shipments["origin_location_id"] == location_id]["shipment_id"]
        loc_cascades = self.cascades[self.cascades["affected_shipment_id"].isin(loc_shps)]["cascade_id"].unique().tolist()

        # Operational summary narrative
        if loc_bn["is_bottleneck"]:
            reasons_str = " ".join(loc_bn["bottleneck_reasons"])
            operational_summary = (
                f"{loc_name} ({city}) is currently classified as a CRITICAL BOTTLENECK with a risk index of {loc_bn['bottleneck_score']}/100. "
                f"The facility handles {loc_bn['total_shipments']:,} shipments with an elevated delay rate of {round(loc_bn['delay_rate']*100, 1)}%. "
                f"{reasons_str}"
            )
        else:
            operational_summary = (
                f"{loc_name} ({city}) is operating normally with a stable throughput of {loc_bn['total_shipments']:,} shipments "
                f"and an acceptable delay rate of {round(loc_bn['delay_rate']*100, 1)}%. Cross-dock transfer slack is within planned tolerance."
            )

        return LocationStory(
            locationId=location_id,
            locationName=loc_name,
            city=city,
            state=state,
            locationType=loc_type,
            totalShipments=loc_bn["total_shipments"],
            delayedShipments=loc_bn["delayed_shipments"],
            delayRate=loc_bn["delay_rate"],
            averageDelayMinutes=loc_bn["average_delay_minutes"],
            cascadeInvolvementCount=loc_bn["cascade_count"],
            propagatedDelayMinutes=loc_bn["total_propagated_delay_minutes"],
            dependencyVolume=loc_bn["dependency_volume"],
            isBottleneck=loc_bn["is_bottleneck"],
            bottleneckScore=loc_bn["bottleneck_score"],
            bottleneckReasons=loc_bn["bottleneck_reasons"],
            activeCascades=loc_cascades,
            operationalSummary=operational_summary
        )

    def list_all_locations(self) -> List[Dict[str, Any]]:
        """
        Lists all locations with bottleneck indicators and summary metrics.
        """
        if getattr(self, "_cached_locations", None) is not None:
            return self._cached_locations
        self._cached_locations = self.impact_analyzer.analyze_location_bottlenecks()
        return self._cached_locations
