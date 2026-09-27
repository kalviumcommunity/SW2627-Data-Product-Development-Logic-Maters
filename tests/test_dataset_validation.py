"""
Unit & Integration Tests for Dataset Validation Engine
Tests referential integrity, timestamp ordering, delay discrepancy flagging, and cascade topology.
Conforms strictly to verified dataset schema.
"""

import pytest
import pandas as pd
from scripts.validate_dataset import DatasetValidator

@pytest.fixture(scope="module")
def validator():
    return DatasetValidator(data_dir="cascading-delay-dataset/data")

def test_validation_execution(validator):
    """Ensure the validator runs and returns a passed status."""
    report = validator.run_all_checks()
    assert report["status"] == "passed"
    assert report["total_checks"] == 25
    assert report["passed"] >= 23
    assert report["failed"] == 0

def test_referential_integrity_check(validator):
    """Verify referential checks on foreign keys."""
    deliv_shps = set(validator.deliveries["shipment_id"])
    valid_shps = set(validator.shipments["shipment_id"])
    invalid = deliv_shps - valid_shps
    assert len(invalid) == 0, f"Found orphan shipments in deliveries: {invalid}"

def test_timestamp_integrity(validator):
    """Check actual departure time <= actual arrival time for shipments."""
    dept = pd.to_datetime(validator.shipments["actual_departure"])
    arr = pd.to_datetime(validator.shipments["actual_arrival"])
    invalid_rows = validator.shipments[dept > arr]
    assert len(invalid_rows) == 0, f"Found {len(invalid_rows)} shipments with departure > arrival."

def test_delay_calculation_integrity(validator):
    """Verify calculated delay matches stored delay."""
    planned_arr = pd.to_datetime(validator.shipments["planned_arrival"])
    actual_arr = pd.to_datetime(validator.shipments["actual_arrival"])
    calculated_delay = ((actual_arr - planned_arr).dt.total_seconds() / 60.0).round().astype(int)
    stored_delay = validator.shipments["final_delay_minutes"]
    diff = (calculated_delay - stored_delay).abs()
    assert (diff <= 1).all(), "Delay calculations deviate by more than 1 minute."

def test_cascade_root_cause_validity(validator):
    """Ensure every cascade has an identified root cause."""
    cascades = validator.cascades
    missing_causes = cascades[cascades["root_cause"].isna()]
    assert len(missing_causes) == 0, "Found cascades with missing root cause."
