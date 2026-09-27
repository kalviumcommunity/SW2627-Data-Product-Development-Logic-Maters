"""
Cascading Delay Intelligence - REST API Service
Exposes the Data Intelligence Layer via FastAPI for downstream clients, dashboards, and explorer.
Conforms strictly to verified dataset schema.
"""

import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Dict, List, Any, Optional
import asyncio
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from services.intelligence.cascade_intelligence import CascadeIntelligence
from services.intelligence.shipment_intelligence import ShipmentIntelligence
from services.intelligence.location_intelligence import LocationIntelligence
from services.cascade_engine.risk_analyzer import RiskAnalyzer
from services.cascade_engine.impact_analyzer import ImpactAnalyzer
from services.intelligence.schemas.models import (
    CascadeStory,
    ShipmentStory,
    LocationStory,
    DashboardOverview,
    DataExplorerRecord
)

async def _warm_caches() -> None:
    """Pre-compute the expensive static payloads in a worker thread (opt-in).

    Enabled only with CASCADE_WARMUP=1 so unit tests never pay warmup cost.
    Safe because the underlying dataset is static: cached results stay valid
    for the process lifetime.
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, get_cached_cascade_summaries)
    await loop.run_in_executor(None, get_cached_dashboard_overview)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("CASCADE_WARMUP", "0") == "1":
        asyncio.create_task(_warm_caches())
    yield


app = FastAPI(
    title="Cascading Delay Intelligence API",
    description="Operational delay attribution, graph propagation modeling, and risk intelligence engine.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = "cascading-delay-dataset/data"

cascade_service = CascadeIntelligence(data_dir=DATA_DIR)
shipment_service = ShipmentIntelligence(data_dir=DATA_DIR)
location_service = LocationIntelligence(data_dir=DATA_DIR)
risk_analyzer = RiskAnalyzer(data_dir=DATA_DIR)
impact_analyzer = ImpactAnalyzer(data_dir=DATA_DIR)

disruptions_df = pd.read_csv(os.path.join(DATA_DIR, "disruptions.csv"))
shipments_df = pd.read_csv(os.path.join(DATA_DIR, "shipments.csv"))
events_df = pd.read_csv(os.path.join(DATA_DIR, "logistics_events.csv"))
dependencies_df = pd.read_csv(os.path.join(DATA_DIR, "dependencies.csv"))
deliveries_df = pd.read_csv(os.path.join(DATA_DIR, "deliveries.csv"))
locations_df = pd.read_csv(os.path.join(DATA_DIR, "locations.csv"))
cascades_df = pd.read_csv(os.path.join(DATA_DIR, "cascade_events.csv"))

# ---------------------------------------------------------------------------
# Response caches (additive performance layer — no logic changes below).
# The dataset is static for the process lifetime, so caching these expensive
# aggregations indefinitely is correct. Endpoints keep identical schemas.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_cached_cascade_summaries() -> List[Dict[str, Any]]:
    """All cascade summaries (~90s to compute cold; instant when cached)."""
    return cascade_service.list_all_cascade_summaries()


@lru_cache(maxsize=1)
def get_cached_location_bottlenecks() -> List[Dict[str, Any]]:
    return location_service.list_all_locations()


@lru_cache(maxsize=1)
def get_cached_dashboard_overview() -> DashboardOverview:
    """Executive summary payload (dominated by the cascade-summary scan)."""
    all_cascades = get_cached_cascade_summaries()
    active_cascades = [c for c in all_cascades if c["status"] == "ACTIVE"]
    major_cascades = all_cascades[:5]

    bottlenecks = get_cached_location_bottlenecks()
    critical_hubs = [b for b in bottlenecks if b["is_bottleneck"]]

    top_risks = risk_analyzer.get_top_vulnerable_shipments(limit=100)
    high_risks = [r for r in top_risks if r["risk_level"] in ["HIGH", "CRITICAL"]]

    total_prop_mins = cascades_df[cascades_df["cascade_level"] > 0]["propagated_delay_minutes"].sum()
    breached_deliveries = len(deliveries_df[
        (deliveries_df["delivery_status"] != "Delivered On Time") |
        (deliveries_df["at_risk"] == True) |
        (deliveries_df["delay_minutes"] > 0)
    ])

    aff_shps = cascades_df["affected_shipment_id"].unique()
    aff_locs_count = shipments_df[shipments_df["shipment_id"].isin(aff_shps)]["origin_location_id"].nunique()

    status = "ELEVATED_RISK" if len(active_cascades) > 0 or len(critical_hubs) > 2 else "STABLE"

    return DashboardOverview(
        networkStatus=status,
        totalShipmentsTracked=len(shipments_df),
        activeDisruptions=len(disruptions_df),
        shipmentsAtRisk=len(high_risks),
        deliveriesAtRisk=breached_deliveries,
        affectedLocations=aff_locs_count,
        totalPropagatedDelayHours=round(float(total_prop_mins) / 60.0, 1),
        bottleneckHubsCount=len(critical_hubs),
        majorActiveCascades=major_cascades
    )

@app.get("/")
def root():
    return {
        "service": "Cascading Delay Intelligence API",
        "status": "operational",
        "version": "1.0.0",
        "documentation": "/docs"
    }

@app.get("/api/dashboard/overview", response_model=DashboardOverview)
def get_dashboard_overview():
    """
    Returns executive summary of logistics network health, active cascades, and high-risk nodes.
    Served from a process-level cache (dataset is static); identical schema.
    """
    return get_cached_dashboard_overview()

@app.get("/api/cascades")
def list_cascades(
    status: Optional[str] = Query(None, description="Filter by status (ACTIVE/RESOLVED)"),
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL/HIGH/MEDIUM/LOW)")
):
    """
    Returns all detected delay cascades in the network with summary metrics.
    Served from a process-level cache (dataset is static); filters apply per request.
    """
    cascades = list(get_cached_cascade_summaries())
    if status:
        cascades = [c for c in cascades if c["status"].upper() == status.upper()]
    if severity:
        cascades = [c for c in cascades if c["severity"].upper() == severity.upper()]
    return {"total": len(cascades), "cascades": cascades}

@app.get("/api/cascades/{cascade_id}", response_model=CascadeStory)
def get_cascade_detail(cascade_id: str):
    """
    Returns deep-dive intelligence story for a single cascade with root cause, timeline, and impact.
    """
    try:
        return cascade_service.build_cascade_story(cascade_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/shipments/{shipment_id}", response_model=ShipmentStory)
def get_shipment_detail(shipment_id: str):
    """
    Returns comprehensive journey history, causal delay attribution, and risk diagnosis for a shipment.
    """
    try:
        return shipment_service.build_shipment_story(shipment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/locations")
def list_locations(bottlenecks_only: bool = Query(False, description="Filter for flagged bottleneck hubs")):
    """
    Returns performance metrics and bottleneck indicators for all logistics nodes.
    Served from a process-level cache (dataset is static); filter applies per request.
    """
    locations = list(get_cached_location_bottlenecks())
    if bottlenecks_only:
        locations = [l for l in locations if l["is_bottleneck"]]
    return {"total": len(locations), "locations": locations}

@app.get("/api/locations/{location_id}", response_model=LocationStory)
def get_location_detail(location_id: str):
    """
    Returns in-depth throughput, delay analysis, and bottleneck reasons for a specific facility.
    """
    try:
        return location_service.build_location_story(location_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/disruptions")
def list_disruptions(
    disruption_type: Optional[str] = Query(None, description="Filter by disruption type"),
    severity: Optional[str] = Query(None, description="Filter by severity level")
):
    """
    Lists operational disruptions with duration, location, and impact metrics.
    """
    subset = disruptions_df
    if disruption_type:
        subset = subset[subset["disruption_type"].str.contains(disruption_type, case=False, na=False)]
    if severity:
        subset = subset[subset["severity"].str.upper() == severity.upper()]

    records = []
    for _, d in subset.iterrows():
        start_dt = pd.to_datetime(d["start_time"])
        end_dt = pd.to_datetime(d["end_time"])
        dur = int((end_dt - start_dt).total_seconds() / 60.0) if pd.notna(start_dt) and pd.notna(end_dt) else 0

        records.append({
            "disruption_id": str(d["disruption_id"]),
            "location_id": str(d["location_id"]),
            "vehicle_id": str(d["vehicle_id"]) if pd.notna(d["vehicle_id"]) else None,
            "disruption_type": str(d["disruption_type"]),
            "severity": str(d["severity"]),
            "start_time": str(d["start_time"]),
            "end_time": str(d["end_time"]),
            "duration_minutes": dur,
            "description": str(d["description"]),
            "root_cause": str(d["root_cause"]),
            "affected_capacity_percentage": float(d["affected_capacity_percentage"])
        })
    return {"total": len(records), "disruptions": records}

@app.get("/api/risks")
def get_risk_analysis(
    limit: int = Query(50, ge=1, le=500),
    risk_level: Optional[str] = Query(None, description="Filter by risk level (CRITICAL/HIGH/MEDIUM/LOW)")
):
    """
    Returns prioritized vulnerable shipments with deterministic risk scores and explanatory drivers.
    """
    results = risk_analyzer.get_top_vulnerable_shipments(limit=limit, filter_level=risk_level)
    return {"total": len(results), "shipments": results}

@app.get("/api/explorer/{entity_type}")
def explore_dataset(
    entity_type: str,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search term for ID or name")
):
    """
    Data Explorer endpoint returning both raw database records and deterministic human explanations.
    Supported entities: shipments, events, dependencies, cascades, disruptions, deliveries, locations.
    """
    entity_lower = entity_type.lower()
    items: List[DataExplorerRecord] = []
    total = 0

    if entity_lower == "shipments":
        df = shipments_df
        if search:
            df = df[df["shipment_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        slice_df = df.iloc[offset : offset + limit]

        for _, row in slice_df.iterrows():
            sid = str(row["shipment_id"])
            delay = int(row["final_delay_minutes"])
            status = str(row["status"])
            if delay <= 15:
                expl = f"Shipment {sid} from {row['origin_location_id']} to {row['destination_location_id']} completed on-time ({status})."
            else:
                expl = f"Shipment {sid} arrived {delay} minutes late at {row['destination_location_id']} with priority {row['priority']}."

            items.append(DataExplorerRecord(
                entityType="shipment",
                entityId=sid,
                timestamp=str(row["actual_departure"]),
                status=status,
                raw=row.to_dict(),
                humanExplanation=expl
            ))

    elif entity_lower == "events":
        df = events_df
        if search:
            df = df[df["shipment_id"].str.contains(search, case=False, na=False) | df["event_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        slice_df = df.iloc[offset : offset + limit]

        for _, row in slice_df.iterrows():
            eid = str(row["event_id"])
            ev_type = str(row["event_type"])
            delay = int(row["delay_minutes"])
            loc = str(row["location_id"])
            status = str(row["event_status"])

            if delay <= 0:
                expl = f"Event '{ev_type}' completed on schedule at facility {loc}."
            else:
                hours = delay // 60
                mins = delay % 60
                time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
                expl = f"The shipment experienced a {time_str} delay during '{ev_type}' at facility {loc} ({status})."

            items.append(DataExplorerRecord(
                entityType="event",
                entityId=eid,
                timestamp=str(row["actual_timestamp"] if pd.notna(row["actual_timestamp"]) else row["scheduled_timestamp"]),
                status=status,
                raw=row.to_dict(),
                humanExplanation=expl
            ))

    elif entity_lower == "dependencies":
        df = dependencies_df
        if search:
            df = df[df["upstream_shipment_id"].str.contains(search, case=False, na=False) | df["downstream_shipment_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        slice_df = df.iloc[offset : offset + limit]

        for _, row in slice_df.iterrows():
            dep_id = str(row["dependency_id"])
            up = str(row["upstream_shipment_id"])
            down = str(row["downstream_shipment_id"])
            delay = int(row["dependency_delay_minutes"])
            loc = str(row["upstream_location_id"])
            status = str(row["dependency_status"])

            if delay > 0:
                expl = f"Downstream shipment {down} at {loc} waited {delay}m for incoming feeder shipment {up} ({status})."
            else:
                expl = f"Transferred successfully on time: Shipment {down} connected with {up} at {loc}."

            items.append(DataExplorerRecord(
                entityType="dependency",
                entityId=dep_id,
                timestamp=str(row["planned_dependency_time"]),
                status=status,
                raw=row.to_dict(),
                humanExplanation=expl
            ))

    elif entity_lower == "cascades":
        df = cascades_df
        if search:
            df = df[df["cascade_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        slice_df = df.iloc[offset : offset + limit]

        for _, row in slice_df.iterrows():
            cid = str(row["cascade_id"])
            shp = str(row["affected_shipment_id"])
            level = int(row["cascade_level"])
            tot_del = int(row["total_delay_minutes"])
            cause = str(row["root_cause"])

            expl = f"Cascade {cid} at level {level}: Shipment {shp} suffered {tot_del}m cumulative delay originating from {cause}."

            items.append(DataExplorerRecord(
                entityType="cascade",
                entityId=f"{cid}-{shp}",
                timestamp=None,
                status="Root" if row["is_root_cause"] else "Propagated",
                raw=row.to_dict(),
                humanExplanation=expl
            ))

    elif entity_lower == "deliveries":
        df = deliveries_df
        if search:
            df = df[df["delivery_id"].str.contains(search, case=False, na=False) | df["shipment_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        slice_df = df.iloc[offset : offset + limit]

        for _, row in slice_df.iterrows():
            did = str(row["delivery_id"])
            status = str(row["delivery_status"])
            at_risk = bool(row["at_risk"])
            delay = int(row["delay_minutes"])

            if status == "Delivered On Time" and delay == 0:
                expl = f"Customer delivery {did} completed on time within agreed SLA window ({status})."
            else:
                expl = f"Delivery {did} missed promised SLA window by {delay} minutes ({status}). Risk: {row['risk_reason']}."

            items.append(DataExplorerRecord(
                entityType="delivery",
                entityId=did,
                timestamp=str(row["actual_delivery_time"]),
                status=status,
                raw=row.to_dict(),
                humanExplanation=expl
            ))

    elif entity_lower == "locations":
        df = locations_df
        if search:
            df = df[df["location_name"].str.contains(search, case=False, na=False) | df["location_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        slice_df = df.iloc[offset : offset + limit]

        for _, row in slice_df.iterrows():
            lid = str(row["location_id"])
            name = str(row["location_name"])
            city = str(row["city"])
            ltype = str(row["location_type"])
            expl = f"{ltype} facility '{name}' operating in {city}, serving regional distribution and sorting."

            items.append(DataExplorerRecord(
                entityType="location",
                entityId=lid,
                timestamp=None,
                status="Active",
                raw=row.to_dict(),
                humanExplanation=expl
            ))

    elif entity_lower == "disruptions":
        df = disruptions_df
        if search:
            df = df[df["disruption_id"].str.contains(search, case=False, na=False) | df["description"].str.contains(search, case=False, na=False)]
        total = len(df)
        slice_df = df.iloc[offset : offset + limit]

        for _, row in slice_df.iterrows():
            did = str(row["disruption_id"])
            dtype = str(row["disruption_type"])
            sev = str(row["severity"])
            loc = str(row["location_id"])
            desc = str(row["description"])

            expl = f"{sev} severity {dtype} logged at {loc}. Description: {desc}."

            items.append(DataExplorerRecord(
                entityType="disruption",
                entityId=did,
                timestamp=str(row["start_time"]),
                status="Active",
                raw=row.to_dict(),
                humanExplanation=expl
            ))

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown entity type '{entity_type}'. Supported entities: shipments, events, dependencies, cascades, disruptions, deliveries, locations."
        )

    return {
        "entity_type": entity_lower,
        "total_records": total,
        "offset": offset,
        "limit": limit,
        "records": items
    }
