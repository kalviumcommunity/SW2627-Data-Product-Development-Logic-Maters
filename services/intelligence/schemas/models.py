"""
Cascading Delay Intelligence - Pydantic Schemas for Intelligence Models
Provides unified contracts for cascades, shipments, locations, dashboard, and explorer.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# --- Cascade Intelligence Schemas ---

class CascadeSummary(BaseModel):
    title: str
    severity: str
    affectedShipments: int
    affectedDeliveries: int
    affectedLocations: int
    propagatedDelayHours: float
    totalDelayHours: float
    status: str

class CascadeRootCause(BaseModel):
    type: str
    locationId: str
    locationName: str
    timestamp: str
    initialShipmentId: str
    initialDelayMinutes: int
    initialDelayFormatted: str
    attributionUncertainty: bool = False
    confidenceScore: float = 1.0
    candidateCauses: List[Dict[str, Any]] = []

class CascadeTimelineItem(BaseModel):
    timestamp: str
    eventType: str
    locationName: str
    shipmentId: str
    delayMinutes: int
    description: str

class CascadePropagationNode(BaseModel):
    shipmentId: str
    depth: int
    originLocation: str
    destinationLocation: str
    directDelayMinutes: int
    propagatedDelayMinutes: int
    totalDelayMinutes: int
    parentShipmentId: Optional[str] = None
    dependencyType: Optional[str] = None
    status: str

class CascadeImpact(BaseModel):
    score: float
    severity: str
    affectedShipments: int
    affectedDeliveries: int
    deliveriesAtRisk: int
    affectedLocations: int
    cascadeDepth: int
    durationMinutes: int
    initialDelayMinutes: int
    propagatedDelayMinutes: int
    totalDelayMinutes: int
    highestImpactShipmentId: str
    highestImpactDelayMinutes: int
    mostAffectedLocationName: str
    downstreamDependenciesCount: int

class CascadeExplanation(BaseModel):
    whatHappened: str
    whyItMatters: str
    currentRisk: str
    recommendedAction: str

class CascadeStory(BaseModel):
    cascadeId: str
    summary: CascadeSummary
    rootCause: CascadeRootCause
    timeline: List[CascadeTimelineItem]
    propagation: List[CascadePropagationNode]
    impact: CascadeImpact
    risks: List[Dict[str, Any]]
    explanation: CascadeExplanation

# --- Shipment Intelligence Schemas ---

class ShipmentTimelineEvent(BaseModel):
    eventId: str
    eventType: str
    locationName: str
    timestamp: str
    delayMinutes: int
    status: str
    humanExplanation: str

class ShipmentStory(BaseModel):
    shipmentId: str
    originLocation: str
    destinationLocation: str
    plannedDeparture: str
    actualDeparture: str
    plannedArrival: str
    actualArrival: str
    status: str
    priority: str
    delayNature: str # Root Delay, Propagated Delay, Independent Delay, On-Time
    finalDelayMinutes: int
    delayExplanation: str
    cascadeId: Optional[str] = None
    timeline: List[ShipmentTimelineEvent]
    upstreamDependencies: List[Dict[str, Any]]
    downstreamDependencies: List[Dict[str, Any]]
    deliveryStatus: Dict[str, Any]
    riskProfile: Dict[str, Any]

# --- Location Intelligence Schemas ---

class LocationStory(BaseModel):
    locationId: str
    locationName: str
    city: str
    state: str
    locationType: str
    totalShipments: int
    delayedShipments: int
    delayRate: float
    averageDelayMinutes: float
    cascadeInvolvementCount: int
    propagatedDelayMinutes: int
    dependencyVolume: int
    isBottleneck: bool
    bottleneckScore: float
    bottleneckReasons: List[str]
    activeCascades: List[str]
    operationalSummary: str

# --- Dashboard Overview Schema ---

class DashboardOverview(BaseModel):
    networkStatus: str
    totalShipmentsTracked: int
    activeDisruptions: int
    shipmentsAtRisk: int
    deliveriesAtRisk: int
    affectedLocations: int
    totalPropagatedDelayHours: float
    bottleneckHubsCount: int
    majorActiveCascades: List[Dict[str, Any]]

# --- Data Explorer Schema ---

class DataExplorerRecord(BaseModel):
    entityType: str
    entityId: str
    timestamp: Optional[str] = None
    status: Optional[str] = None
    raw: Dict[str, Any]
    humanExplanation: str
