-- Canonical schema for the Cascading Delay Intelligence SQL layer.
--
-- Database: SQLite (local, reproducible; see README "SQL Analytics").
-- Table `integrated_logistics` mirrors the output of
-- pipeline.integration.build_integrated_dataset: one row per integrated
-- operational record, keyed by shipment_id with traceability columns.
--
-- Column provenance:
--   shipment scans ..... shipment_id, timestamp, warehouse_id, route_id,
--                          scan_type, status            (Design.md section 8.1)
--   delay reports ...... delay_id, delay_reason, delay_duration,
--                          reported_at                  (Design.md section 8.2)
--   warehouse transfers  transfer_id, source_warehouse,
--                          destination_warehouse, transfer_time,
--                          expected_transfer_time,
--                          actual_transfer_time          (Design.md section 8.3)
--   integration layer .. _delay_match, _transfer_match, _record_source,
--                          _source_datasets, _integration_key
--
-- Types: identifiers/timestamps as TEXT (timestamps in ISO-8601 so that
-- DATE()/ordering work lexicographically), durations as REAL.
-- The Python loader (pipeline/sql_database.py) creates this table
-- dynamically from the ACTUAL DataFrame columns using the same type
-- mapping, so this file is the canonical contract, not an invented
-- requirement: absent columns are simply not created.
-- AGGREGATION NOTE: one shipment may own several rows (one-to-many
-- joins). Record-level metrics read this table directly; shipment-level
-- metrics must aggregate via the shipment_delay_summary view (one row
-- per shipment, delay = MAX per shipment) - see views.sql.

CREATE TABLE IF NOT EXISTS integrated_logistics (
    shipment_id            TEXT,
    timestamp              TEXT,
    warehouse_id           TEXT,
    route_id               TEXT,
    scan_type              TEXT,
    status                 TEXT,
    delay_id               TEXT,
    delay_reason           TEXT,
    delay_duration         REAL,
    reported_at            TEXT,
    transfer_id            TEXT,
    source_warehouse       TEXT,
    destination_warehouse  TEXT,
    transfer_time          TEXT,
    expected_transfer_time TEXT,
    actual_transfer_time   TEXT,
    _delay_match           TEXT,
    _transfer_match        TEXT,
    _record_source         TEXT,
    _source_datasets       TEXT,
    _integration_key       TEXT
);

CREATE INDEX IF NOT EXISTS idx_logistics_shipment
    ON integrated_logistics (shipment_id);
CREATE INDEX IF NOT EXISTS idx_logistics_route
    ON integrated_logistics (route_id);
CREATE INDEX IF NOT EXISTS idx_logistics_warehouse
    ON integrated_logistics (warehouse_id);
CREATE INDEX IF NOT EXISTS idx_logistics_timestamp
    ON integrated_logistics (timestamp);
