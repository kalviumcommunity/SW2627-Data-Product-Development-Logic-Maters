-- Reusable analytical views (SQLite). `{table}` is rendered by
-- pipeline/sql_database.py. All views read canonical columns from
-- sql/schema.sql; delay status is delay_duration > 0 throughout.
-- No thresholds or cascade rules appear here.

-- One row per shipment: immune to one-to-many row duplication.
CREATE VIEW IF NOT EXISTS shipment_delay_summary AS
SELECT
    shipment_id,
    COUNT(*) AS records,
    SUM(CASE WHEN delay_duration > 0 THEN 1 ELSE 0 END) AS delayed_records,
    MAX(CASE WHEN delay_duration > 0 THEN 1 ELSE 0 END) AS delay_flag,
    MAX(delay_duration) AS shipment_delay,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
FROM {table}
GROUP BY shipment_id;

-- Per-route factual delay metrics.
CREATE VIEW IF NOT EXISTS route_delay_metrics AS
SELECT
    route_id AS route,
    COUNT(*) AS records,
    COUNT(DISTINCT shipment_id) AS shipments,
    COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END) AS delayed_shipments,
    100.0 * COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END)
        / NULLIF(COUNT(DISTINCT shipment_id), 0) AS delay_rate,
    AVG(CASE WHEN delay_duration > 0 THEN delay_duration END) AS avg_delay,
    SUM(CASE WHEN delay_duration > 0 THEN delay_duration ELSE 0 END) AS total_delay
FROM {table}
GROUP BY route_id;

-- Per-warehouse factual delay metrics.
CREATE VIEW IF NOT EXISTS warehouse_delay_metrics AS
SELECT
    warehouse_id AS warehouse,
    COUNT(*) AS records,
    COUNT(DISTINCT shipment_id) AS shipments,
    COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END) AS delayed_shipments,
    100.0 * COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END)
        / NULLIF(COUNT(DISTINCT shipment_id), 0) AS delay_rate,
    AVG(CASE WHEN delay_duration > 0 THEN delay_duration END) AS avg_delay,
    SUM(CASE WHEN delay_duration > 0 THEN delay_duration ELSE 0 END) AS total_delay
FROM {table}
GROUP BY warehouse_id;

-- Daily delay metrics (day extracted from the ISO timestamp text).
CREATE VIEW IF NOT EXISTS daily_delay_metrics AS
SELECT
    DATE(timestamp) AS day,
    COUNT(*) AS records,
    COUNT(DISTINCT shipment_id) AS shipments,
    COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END) AS delayed_shipments,
    100.0 * COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END)
        / NULLIF(COUNT(DISTINCT shipment_id), 0) AS delay_rate,
    AVG(CASE WHEN delay_duration > 0 THEN delay_duration END) AS avg_delay
FROM {table}
WHERE timestamp IS NOT NULL
GROUP BY DATE(timestamp);
