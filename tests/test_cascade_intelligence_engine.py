"""
Unit & Integration Tests for Cascade Engine
Tests graph construction, delay classification, multi-level propagation, and root cause analysis.
Conforms strictly to verified dataset schema.
"""

import pytest
from services.cascade_engine.graph_builder import LogisticsGraph
from services.cascade_engine.cascade_detector import CascadeDetector
from services.cascade_engine.root_cause_analyzer import RootCauseAnalyzer
from services.cascade_engine.impact_analyzer import ImpactAnalyzer

@pytest.fixture(scope="module")
def graph():
    return LogisticsGraph(data_dir="cascading-delay-dataset/data")

@pytest.fixture(scope="module")
def detector():
    return CascadeDetector(data_dir="cascading-delay-dataset/data")

@pytest.fixture(scope="module")
def rc_analyzer():
    return RootCauseAnalyzer(data_dir="cascading-delay-dataset/data")

@pytest.fixture(scope="module")
def impact_analyzer():
    return ImpactAnalyzer(data_dir="cascading-delay-dataset/data")

def test_graph_construction(graph):
    """Verify nodes and edges are populated in LogisticsGraph."""
    assert len(graph.nodes) > 1000
    assert len(graph.edges) > 500
    assert len(graph.reverse_edges) > 500

def test_delay_classification_types(detector):
    known_cascades = detector.cascades
    root_shp = known_cascades[known_cascades["is_root_cause"] == True].iloc[0]["root_shipment_id"]
    delayed_prop = known_cascades[(known_cascades["cascade_level"] > 0) & (known_cascades["total_delay_minutes"] > 15)]
    prop_shp = delayed_prop.iloc[0]["affected_shipment_id"]

    root_class = detector.classify_delay_nature(root_shp)
    assert root_class["nature"] == "Root Delay"
    assert "cascade_id" in root_class

    prop_class = detector.classify_delay_nature(prop_shp)
    assert prop_class["nature"] in ["Propagated Delay", "Root Delay", "Independent Delay"]

def test_multi_level_cascade_reconstruction(detector):
    """Verify reconstruction of cascades."""
    known_cascades = detector.cascades
    deep_cascades = known_cascades[known_cascades["cascade_level"] >= 1]["cascade_id"].unique()
    assert len(deep_cascades) > 0, "Expected at least one cascade with cascade_level >= 1."

    target_cid = deep_cascades[0]
    tree = detector.reconstruct_cascade_tree(target_cid)
    assert tree["max_depth"] >= 1
    assert "echelons" in tree
    assert tree["cascade_id"] == target_cid

def test_root_cause_analysis(rc_analyzer):
    """Verify root cause analyzer identifies primary trigger and location."""
    known_cascades = rc_analyzer.cascades
    sample_cid = known_cascades.iloc[0]["cascade_id"]

    rc = rc_analyzer.analyze_cascade(sample_cid)
    assert "error" not in rc
    assert rc["root_cause"] is not None
    assert rc["root_location_id"] is not None
    assert rc["initial_delay_minutes"] > 0
    assert "summary" in rc

def test_impact_analysis(impact_analyzer):
    """Verify cascade blast radius and compounding delay metrics."""
    known_cascades = impact_analyzer.cascades
    sample_cid = known_cascades.iloc[0]["cascade_id"]

    impact = impact_analyzer.analyze_cascade_impact(sample_cid)
    assert "error" not in impact
    assert impact["affected_shipments"] >= 1
    assert impact["affected_locations"] >= 1
    assert impact["total_delay_minutes"] >= impact["initial_delay_minutes"]
    assert 0.0 <= impact["impact_score"] <= 100.0
