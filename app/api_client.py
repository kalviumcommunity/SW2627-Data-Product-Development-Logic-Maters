"""Cascade Intelligence - API service layer.

Single point of access to the FastAPI intelligence backend. All frontend
views consume real API data through this module — never CSVs, never mocks.

Strategy
--------
1. Prefer HTTP against a running FastAPI server (``API_BASE_URL`` env var,
   default ``http://127.0.0.1:8000``) so the Streamlit frontend is a true
   API client of ``services/api.py``.
2. Transparently fall back to direct in-process calls into the same
   intelligence services when no server is reachable (e.g. Streamlit Cloud,
   single-process runs). The fallback uses the *identical* service classes
   and dataset, so data is still real — just without the HTTP hop.

Every public helper returns plain ``dict``/``list`` objects decoded from
the verified Pydantic schemas (see
``services/intelligence/schemas/models.py``).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

API_BASE_URL = os.environ.get("CASCADE_API_URL", os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")

# Generous default: the two heavy endpoints (overview, cascade list) can take
# ~2 min cold on first computation; the server now caches them process-wide
# so warm calls return in milliseconds. Env override: CASCADE_API_TIMEOUT.
_HTTP_TIMEOUT = float(os.environ.get("CASCADE_API_TIMEOUT", "300"))


# ---------------------------------------------------------------------------
# Low-level transport
# ---------------------------------------------------------------------------

def _http_get(path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """GET ``path`` from the FastAPI server. Returns parsed JSON or None."""
    try:
        import httpx  # type: ignore

        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(f"{API_BASE_URL}{path}", params=params or {})
            if resp.status_code == 404:
                return {"__not_found__": True}
            resp.raise_for_status()
            return resp.json()
    except ImportError:
        try:
            import requests  # type: ignore

            resp = requests.get(f"{API_BASE_URL}{path}", params=params or {}, timeout=_HTTP_TIMEOUT)
            if resp.status_code == 404:
                return {"__not_found__": True}
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None
    except Exception:
        return None


def is_api_reachable() -> bool:
    """True when a live FastAPI server answers ``GET /``."""
    data = _http_get("/")
    return isinstance(data, dict) and data.get("status") == "operational"


# ---------------------------------------------------------------------------
# Direct (in-process) fallback — same services, same dataset, no mocks
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _direct_services() -> Dict[str, Any]:
    from services.intelligence.cascade_intelligence import CascadeIntelligence
    from services.intelligence.shipment_intelligence import ShipmentIntelligence
    from services.intelligence.location_intelligence import LocationIntelligence
    from services.cascade_engine.risk_analyzer import RiskAnalyzer

    data_dir = os.environ.get("CASCADE_DATA_DIR", "cascading-delay-dataset/data")
    return {
        "cascades": CascadeIntelligence(data_dir=data_dir),
        "shipments": ShipmentIntelligence(data_dir=data_dir),
        "locations": LocationIntelligence(data_dir=data_dir),
        "risks": RiskAnalyzer(data_dir=data_dir),
    }


def _direct_call(fn_name: str, *args: Any, **kwargs: Any) -> Any:
    """Invoke an intelligence service method and normalise Pydantic -> dict."""
    svc = _direct_services()
    table = {
        "overview": ("cascades", None),  # handled specially
        "list_cascades": ("cascades", "list_all_cascade_summaries"),
        "cascade_story": ("cascades", "build_cascade_story"),
        "shipment_story": ("shipments", "build_shipment_story"),
        "list_locations": ("locations", "list_all_locations"),
        "location_story": ("locations", "build_location_story"),
        "risks": ("risks", "get_top_vulnerable_shipments"),
    }
    group, method = table[fn_name]
    if fn_name == "overview":
        raise RuntimeError("_direct_call overview handled separately")
    service = svc[group]
    result = getattr(service, method)(*args, **kwargs)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, list):
        return [r.model_dump() if hasattr(r, "model_dump") else r for r in result]
    return result


def _direct_overview() -> Dict[str, Any]:
    """Mirror of GET /api/dashboard/overview without HTTP."""
    import pandas as pd

    data_dir = os.environ.get("CASCADE_DATA_DIR", "cascading-delay-dataset/data")
    svc = _direct_services()
    all_cascades = svc["cascades"].list_all_cascade_summaries()
    major = all_cascades[:5]
    bottlenecks = svc["locations"].list_all_locations()
    critical_hubs = [b for b in bottlenecks if b.get("is_bottleneck")]
    top_risks = svc["risks"].get_top_vulnerable_shipments(limit=100)
    high_risks = [r for r in top_risks if r.get("risk_level") in ("HIGH", "CRITICAL")]

    cascades_df = pd.read_csv(os.path.join(data_dir, "cascade_events.csv"))
    shipments_df = pd.read_csv(os.path.join(data_dir, "shipments.csv"))
    deliveries_df = pd.read_csv(os.path.join(data_dir, "deliveries.csv"))
    disruptions_df = pd.read_csv(os.path.join(data_dir, "disruptions.csv"))

    total_prop = cascades_df[cascades_df["cascade_level"] > 0]["propagated_delay_minutes"].sum()
    breached = len(
        deliveries_df[
            (deliveries_df["delivery_status"] != "Delivered On Time")
            | (deliveries_df["at_risk"] == True)  # noqa: E712
            | (deliveries_df["delay_minutes"] > 0)
        ]
    )
    aff = cascades_df["affected_shipment_id"].unique()
    aff_locs = shipments_df[shipments_df["shipment_id"].isin(aff)]["origin_location_id"].nunique()
    active = [c for c in all_cascades if c.get("status") == "ACTIVE"]
    status = "ELEVATED_RISK" if (active or len(critical_hubs) > 2) else "STABLE"
    return {
        "networkStatus": status,
        "totalShipmentsTracked": len(shipments_df),
        "activeDisruptions": len(disruptions_df),
        "shipmentsAtRisk": len(high_risks),
        "deliveriesAtRisk": breached,
        "affectedLocations": int(aff_locs),
        "totalPropagatedDelayHours": round(float(total_prop) / 60.0, 1),
        "bottleneckHubsCount": len(critical_hubs),
        "majorActiveCascades": major,
    }


def _direct_explorer(entity_type: str, limit: int, offset: int, search: Optional[str]) -> Dict[str, Any]:
    """Mirror of GET /api/explorer/{entity} without HTTP (same narratives)."""
    import pandas as pd

    data_dir = os.environ.get("CASCADE_DATA_DIR", "cascading-delay-dataset/data")
    entity = entity_type.lower()

    def _load(name: str) -> pd.DataFrame:
        return pd.read_csv(os.path.join(data_dir, name))

    records: List[Dict[str, Any]] = []
    if entity == "shipments":
        df = _load("shipments.csv")
        if search:
            df = df[df["shipment_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        for _, row in df.iloc[offset : offset + limit].iterrows():
            sid, delay, status = str(row["shipment_id"]), int(row["final_delay_minutes"]), str(row["status"])
            expl = (
                f"Shipment {sid} from {row['origin_location_id']} to {row['destination_location_id']} "
                f"completed on-time ({status})."
                if delay <= 15
                else f"Shipment {sid} arrived {delay} minutes late at {row['destination_location_id']} "
                f"with priority {row['priority']}."
            )
            raw = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            records.append({"entityType": "shipment", "entityId": sid, "timestamp": str(row["actual_departure"]),
                            "status": status, "raw": raw, "humanExplanation": expl})
    elif entity == "events":
        df = _load("logistics_events.csv")
        if search:
            df = df[df["shipment_id"].str.contains(search, case=False, na=False)
                    | df["event_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        for _, row in df.iloc[offset : offset + limit].iterrows():
            delay = int(row["delay_minutes"])
            expl = (f"Event '{row['event_type']}' completed on schedule at facility {row['location_id']}."
                    if delay <= 0 else f"The shipment experienced a {delay}m delay during "
                    f"'{row['event_type']}' at facility {row['location_id']} ({row['event_status']}).")
            raw = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            ts = row["actual_timestamp"] if pd.notna(row["actual_timestamp"]) else row["scheduled_timestamp"]
            records.append({"entityType": "event", "entityId": str(row["event_id"]), "timestamp": str(ts),
                            "status": str(row["event_status"]), "raw": raw, "humanExplanation": expl})
    elif entity == "dependencies":
        df = _load("dependencies.csv")
        if search:
            df = df[df["upstream_shipment_id"].str.contains(search, case=False, na=False)
                    | df["downstream_shipment_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        for _, row in df.iloc[offset : offset + limit].iterrows():
            delay = int(row["dependency_delay_minutes"])
            expl = (f"Downstream shipment {row['downstream_shipment_id']} at {row['upstream_location_id']} "
                    f"waited {delay}m for incoming feeder shipment {row['upstream_shipment_id']} "
                    f"({row['dependency_status']})." if delay > 0 else
                    f"Transferred successfully on time: Shipment {row['downstream_shipment_id']} "
                    f"connected with {row['upstream_shipment_id']} at {row['upstream_location_id']}.")
            raw = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            records.append({"entityType": "dependency", "entityId": str(row["dependency_id"]),
                            "timestamp": str(row["planned_dependency_time"]),
                            "status": str(row["dependency_status"]), "raw": raw, "humanExplanation": expl})
    elif entity == "cascades":
        df = _load("cascade_events.csv")
        if search:
            df = df[df["cascade_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        for _, row in df.iloc[offset : offset + limit].iterrows():
            expl = (f"Cascade {row['cascade_id']} at level {int(row['cascade_level'])}: Shipment "
                    f"{row['affected_shipment_id']} suffered {int(row['total_delay_minutes'])}m "
                    f"cumulative delay originating from {row['root_cause']}.")
            raw = {k: (None if pd.isna(v) else (bool(v) if isinstance(v, bool) else v))
                   for k, v in row.to_dict().items()}
            records.append({"entityType": "cascade", "entityId": f"{row['cascade_id']}-{row['affected_shipment_id']}",
                            "timestamp": None, "status": "Root" if row["is_root_cause"] else "Propagated",
                            "raw": raw, "humanExplanation": expl})
    elif entity == "deliveries":
        df = _load("deliveries.csv")
        if search:
            df = df[df["delivery_id"].str.contains(search, case=False, na=False)
                    | df["shipment_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        for _, row in df.iloc[offset : offset + limit].iterrows():
            delay = int(row["delay_minutes"])
            expl = (f"Customer delivery {row['delivery_id']} completed on time within agreed SLA window "
                    f"({row['delivery_status']})." if str(row["delivery_status"]) == "Delivered On Time" and delay == 0
                    else f"Delivery {row['delivery_id']} missed promised SLA window by {delay} minutes "
                    f"({row['delivery_status']}). Risk: {row['risk_reason']}.")
            raw = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            records.append({"entityType": "delivery", "entityId": str(row["delivery_id"]),
                            "timestamp": str(row["actual_delivery_time"]),
                            "status": str(row["delivery_status"]), "raw": raw, "humanExplanation": expl})
    elif entity == "locations":
        df = _load("locations.csv")
        if search:
            df = df[df["location_name"].str.contains(search, case=False, na=False)
                    | df["location_id"].str.contains(search, case=False, na=False)]
        total = len(df)
        for _, row in df.iloc[offset : offset + limit].iterrows():
            expl = (f"{row['location_type']} facility '{row['location_name']}' operating in "
                    f"{row['city']}, serving regional distribution and sorting.")
            raw = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            records.append({"entityType": "location", "entityId": str(row["location_id"]), "timestamp": None,
                            "status": "Active", "raw": raw, "humanExplanation": expl})
    elif entity == "disruptions":
        df = _load("disruptions.csv")
        if search:
            df = df[df["disruption_id"].str.contains(search, case=False, na=False)
                    | df["description"].str.contains(search, case=False, na=False)]
        total = len(df)
        for _, row in df.iloc[offset : offset + limit].iterrows():
            expl = (f"{row['severity']} severity {row['disruption_type']} logged at {row['location_id']}. "
                    f"Description: {row['description']}.")
            raw = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            records.append({"entityType": "disruption", "entityId": str(row["disruption_id"]),
                            "timestamp": str(row["start_time"]), "status": "Active",
                            "raw": raw, "humanExplanation": expl})
    else:
        raise ValueError(f"Unknown entity type '{entity_type}'.")
    return {"entity_type": entity, "total_records": total, "offset": offset, "limit": limit, "records": records}


def _direct_disruptions(disruption_type: Optional[str], severity: Optional[str]) -> Dict[str, Any]:
    import pandas as pd

    data_dir = os.environ.get("CASCADE_DATA_DIR", "cascading-delay-dataset/data")
    df = pd.read_csv(os.path.join(data_dir, "disruptions.csv"))
    if disruption_type:
        df = df[df["disruption_type"].str.contains(disruption_type, case=False, na=False)]
    if severity:
        df = df[df["severity"].str.upper() == severity.upper()]
    records = []
    for _, d in df.iterrows():
        start_dt, end_dt = pd.to_datetime(d["start_time"]), pd.to_datetime(d["end_time"])
        dur = int((end_dt - start_dt).total_seconds() / 60.0) if pd.notna(start_dt) and pd.notna(end_dt) else 0
        records.append({"disruption_id": str(d["disruption_id"]), "location_id": str(d["location_id"]),
                        "vehicle_id": str(d["vehicle_id"]) if pd.notna(d["vehicle_id"]) else None,
                        "disruption_type": str(d["disruption_type"]), "severity": str(d["severity"]),
                        "start_time": str(d["start_time"]), "end_time": str(d["end_time"]),
                        "duration_minutes": dur, "description": str(d["description"]),
                        "root_cause": str(d["root_cause"]),
                        "affected_capacity_percentage": float(d["affected_capacity_percentage"])})
    return {"total": len(records), "disruptions": records}


# ---------------------------------------------------------------------------
# Public API — every helper prefers HTTP, falls back to direct services
# ---------------------------------------------------------------------------

class NotFoundError(Exception):
    """Raised when the backend answers 404 for a cascade/shipment/location."""


def _raise_if_not_found(payload: Any, label: str) -> None:
    if isinstance(payload, dict) and payload.get("__not_found__"):
        raise NotFoundError(f"{label} not found.")


def get_overview() -> Dict[str, Any]:
    data = _http_get("/api/dashboard/overview")
    if isinstance(data, dict) and "networkStatus" in data:
        return data
    return _direct_overview()


def list_cascades(status: Optional[str] = None, severity: Optional[str] = None) -> Dict[str, Any]:
    params = {}
    if status:
        params["status"] = status
    if severity:
        params["severity"] = severity
    data = _http_get("/api/cascades", params=params or None)
    if isinstance(data, dict) and "cascades" in data:
        return data
    cascades = _direct_call("list_cascades")
    if status:
        cascades = [c for c in cascades if str(c.get("status", "")).upper() == status.upper()]
    if severity:
        cascades = [c for c in cascades if str(c.get("severity", "")).upper() == severity.upper()]
    return {"total": len(cascades), "cascades": cascades}


def get_cascade(cascade_id: str) -> Dict[str, Any]:
    data = _http_get(f"/api/cascades/{cascade_id}")
    _raise_if_not_found(data, f"Cascade {cascade_id}")
    if isinstance(data, dict) and "cascadeId" in data:
        return data
    try:
        return _direct_call("cascade_story", cascade_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc


def get_shipment(shipment_id: str) -> Dict[str, Any]:
    data = _http_get(f"/api/shipments/{shipment_id}")
    _raise_if_not_found(data, f"Shipment {shipment_id}")
    if isinstance(data, dict) and "shipmentId" in data:
        return data
    try:
        return _direct_call("shipment_story", shipment_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc


def list_locations(bottlenecks_only: bool = False) -> Dict[str, Any]:
    data = _http_get("/api/locations", params={"bottlenecks_only": str(bottlenecks_only).lower()} if bottlenecks_only else None)
    if isinstance(data, dict) and "locations" in data:
        return data
    locations = _direct_call("list_locations")
    if bottlenecks_only:
        locations = [loc for loc in locations if loc.get("is_bottleneck")]
    return {"total": len(locations), "locations": locations}


def get_location(location_id: str) -> Dict[str, Any]:
    data = _http_get(f"/api/locations/{location_id}")
    _raise_if_not_found(data, f"Location {location_id}")
    if isinstance(data, dict) and "locationId" in data:
        return data
    try:
        return _direct_call("location_story", location_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc


def list_disruptions(disruption_type: Optional[str] = None, severity: Optional[str] = None) -> Dict[str, Any]:
    params = {}
    if disruption_type:
        params["disruption_type"] = disruption_type
    if severity:
        params["severity"] = severity
    data = _http_get("/api/disruptions", params=params or None)
    if isinstance(data, dict) and "disruptions" in data:
        return data
    return _direct_disruptions(disruption_type, severity)


def get_risks(limit: int = 50, risk_level: Optional[str] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": limit}
    if risk_level:
        params["risk_level"] = risk_level
    data = _http_get("/api/risks", params=params)
    if isinstance(data, dict) and "shipments" in data:
        return data
    results = _direct_call("risks", limit=limit, filter_level=risk_level)
    return {"total": len(results), "shipments": results}


def explore(entity_type: str, limit: int = 25, offset: int = 0, search: Optional[str] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search
    data = _http_get(f"/api/explorer/{entity_type}", params=params)
    if isinstance(data, dict) and "records" in data:
        return data
    try:
        return _direct_explorer(entity_type, limit, offset, search)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc


EXPLORER_ENTITIES = ["shipments", "events", "dependencies", "cascades", "disruptions", "deliveries", "locations"]


def fetch_parallel(calls: Dict[str, Any]) -> Dict[str, Any]:
    """Run independent API fetches concurrently (single-threaded server-safe).

    ``calls`` maps a result key to a zero-argument callable. Returns a dict
    of key -> result. Exceptions propagate from the failing callable.
    """
    import concurrent.futures

    results: Dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(calls), 6)) as pool:
        future_map = {pool.submit(fn): key for key, fn in calls.items()}
        for future in concurrent.futures.as_completed(future_map):
            results[future_map[future]] = future.result()
    return results
