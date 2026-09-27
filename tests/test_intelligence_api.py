"""
Unit & Integration Tests for Intelligence API & Unified Schemas
Validates FastAPI endpoints and response schemas using Starlette/HTTPX TestClient.
"""

import pytest
from starlette.testclient import TestClient
from services.api import app

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

def test_api_root(client):
    """Test root status endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"

def test_dashboard_overview(client):
    """Test dashboard overview endpoint."""
    response = client.get("/api/dashboard/overview")
    assert response.status_code == 200
    data = response.json()
    assert "networkStatus" in data
    assert data["totalShipmentsTracked"] > 0
    assert "majorActiveCascades" in data

def test_cascades_list(client):
    """Test cascade list endpoint."""
    response = client.get("/api/cascades")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert data["total"] > 0
    assert len(data["cascades"]) > 0

def test_cascade_detail_story(client):
    """Test full cascade story endpoint and schema conformity."""
    # First get a valid cascade id
    list_res = client.get("/api/cascades")
    cid = list_res.json()["cascades"][0]["cascade_id"]

    response = client.get(f"/api/cascades/{cid}")
    assert response.status_code == 200
    story = response.json()
    assert story["cascadeId"] == cid
    assert "summary" in story
    assert "rootCause" in story
    assert "timeline" in story
    assert "propagation" in story
    assert "impact" in story
    assert "explanation" in story
    assert len(story["explanation"]["whatHappened"]) > 10
    assert len(story["explanation"]["whyItMatters"]) > 10

def test_shipment_detail_story(client):
    """Test shipment story endpoint and schema conformity."""
    response = client.get("/api/shipments/SHP-00001")
    assert response.status_code == 200
    shp_story = response.json()
    assert shp_story["shipmentId"] == "SHP-00001"
    assert "delayNature" in shp_story
    assert "timeline" in shp_story
    assert "riskProfile" in shp_story

def test_location_detail_story(client):
    """Test location story endpoint and schema conformity."""
    response = client.get("/api/locations/LOC-DEL-01")
    assert response.status_code == 200
    loc_story = response.json()
    assert loc_story["locationId"] == "LOC-DEL-01"
    assert "bottleneckScore" in loc_story
    assert "operationalSummary" in loc_story

def test_disruptions_endpoint(client):
    """Test disruptions endpoint."""
    response = client.get("/api/disruptions")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert len(data["disruptions"]) > 0

def test_risks_endpoint(client):
    """Test risk engine endpoint."""
    response = client.get("/api/risks?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["shipments"]) <= 10
    for s in data["shipments"]:
        assert "risk_score" in s
        assert "reasons" in s

def test_data_explorer_dual_representation(client):
    """Test Data Explorer endpoint ensuring both raw and human explanations are returned."""
    response = client.get("/api/explorer/shipments?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["entity_type"] == "shipments"
    assert len(data["records"]) == 5
    for rec in data["records"]:
        assert "raw" in rec
        assert "humanExplanation" in rec
        assert len(rec["humanExplanation"]) > 5

def test_not_found_handling(client):
    """Verify clean 404 responses for missing entities."""
    response = client.get("/api/cascades/NON_EXISTENT_CASCADE")
    assert response.status_code == 404
    response = client.get("/api/shipments/NON_EXISTENT_SHIPMENT")
    assert response.status_code == 404
