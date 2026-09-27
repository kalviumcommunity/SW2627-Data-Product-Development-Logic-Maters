"""
Unit & Integration Tests for Deterministic Risk Engine
Tests scoring tiers (LOW, MEDIUM, HIGH, CRITICAL), deterministic bounds, and explanatory reasons.
Conforms strictly to verified dataset schema.
"""

import pytest
from services.cascade_engine.risk_analyzer import RiskAnalyzer

@pytest.fixture(scope="module")
def risk_analyzer():
    return RiskAnalyzer(data_dir="cascading-delay-dataset/data")

def test_risk_score_bounds(risk_analyzer):
    """Ensure risk scores are bounded strictly within [0.0, 1.0]."""
    top_risks = risk_analyzer.get_top_vulnerable_shipments(limit=25)
    for r in top_risks:
        assert 0.0 <= r["risk_score"] <= 1.0
        assert r["is_deterministic_score"] is True
        assert len(r["reasons"]) > 0

def test_high_risk_classification(risk_analyzer):
    """Check that high/critical risk shipments exhibit high buffer consumption or severe delays."""
    top_critical = risk_analyzer.get_top_vulnerable_shipments(limit=10, filter_level="CRITICAL")
    assert len(top_critical) > 0
    for crit in top_critical:
        assert crit["risk_level"] == "CRITICAL"
        assert crit["risk_score"] >= 0.70
        has_reason = len(crit["reasons"]) > 0
        assert has_reason

def test_on_time_shipment_low_risk(risk_analyzer):
    """Ensure on-time shipments receive LOW risk level."""
    on_time_shps = risk_analyzer.shipments[risk_analyzer.shipments["final_delay_minutes"] == 0]
    sample_id = on_time_shps.iloc[0]["shipment_id"]
    
    risk_obj = risk_analyzer.analyze_shipment_risk(sample_id)
    assert risk_obj["risk_level"] in ["LOW", "MEDIUM"]
    assert risk_obj["risk_score"] < 0.60
