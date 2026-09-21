-- Business KPI queries for Cascading Delay Intelligence (SQLite).
--
-- Conventions:
--   * `{table}` is replaced with the integrated table name by
--     pipeline/sql_database.py; every section is `-- query: <name>`.
--   * Assumes the canonical columns from sql/schema.sql. Delay status is
--     defined as delay_duration > 0 (same rule as the Pandas engine's
--     duration_gt_zero method) so SQL/Pandas comparisons are like-for-like.
--   * Zero denominators yield NULL via NULLIF, never a divide-by-zero.
--   * AGGREGATION LEVELS: sections ending in `_record` read integrated
--     rows directly; `shipment_*` sections aggregate one row per shipment
--     (MAX per shipment is robust to one-to-many duplication) - see the
--     header note in sql/schema.sql. Do NOT use SUM(delay_duration) for
--     shipment-level totals; use shipment_delay_total.

-- query: shipment_kpis
-- Shipment-level counts and rates (one row per shipment grain).
SELECT
    COUNT(DISTINCT shipment_id) AS total_shipments,
    COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END) AS delayed_shipments,
    COUNT(DISTINCT shipment_id)
        - COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END) AS on_time_shipments,
    100.0 * COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END)
        / NULLIF(COUNT(DISTINCT shipment_id), 0) AS delay_rate,
    100.0 - (
        100.0 * COUNT(DISTINCT CASE WHEN delay_duration > 0 THEN shipment_id END)
        / NULLIF(COUNT(DISTINCT shipment_id), 0)
    ) AS on_time_rate
FROM {table};

-- query: delay_kpis_record
-- Delay-duration stats over delayed RECORDS (matches analysis/kpis.py).
SELECT
    COUNT(*) AS delayed_records,
    AVG(delay_duration) AS average_delay,
    MAX(delay_duration) AS max_delay,
    MIN(delay_duration) AS min_delay,
    SUM(delay_duration) AS total_delay_record_level
FROM {table}
WHERE delay_duration > 0;

-- query: delay_median_record
-- Median over delayed records via window functions (SQLite has no
-- MEDIAN aggregate). Averages the two middle rows for even counts.
SELECT AVG(delay_duration) AS median_delay
FROM (
    SELECT
        delay_duration,
        ROW_NUMBER() OVER (ORDER BY delay_duration) AS rn,
        COUNT(*) OVER () AS n
    FROM {table}
    WHERE delay_duration > 0
)
WHERE rn IN (CAST((n + 1) / 2 AS INTEGER), CAST((n + 2) / 2 AS INTEGER));

-- query: shipment_delay_kpis
-- Shipment-grain durations: per-shipment delay = MAX(delay_duration),
-- immune to one-to-many row duplication.
SELECT
    COUNT(*) AS delayed_shipments,
    AVG(shipment_delay) AS average_delay_per_shipment,
    MAX(shipment_delay) AS max_delay_per_shipment,
    MIN(shipment_delay) AS min_delay_per_shipment,
    SUM(shipment_delay) AS total_delay_shipment_level
FROM (
    SELECT shipment_id, MAX(delay_duration) AS shipment_delay
    FROM {table}
    GROUP BY shipment_id
    HAVING MAX(delay_duration) > 0
);

-- query: operational_kpis
-- Integration coverage from traceability columns written by the
-- integration layer ('both' = matched to a source record).
SELECT
    COUNT(*) AS total_records,
    SUM(CASE WHEN _delay_match = 'both' THEN 1 ELSE 0 END) AS rows_with_delay_report_match,
    100.0 * SUM(CASE WHEN _delay_match = 'both' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS delay_report_match_rate,
    SUM(CASE WHEN _transfer_match = 'both' THEN 1 ELSE 0 END) AS rows_with_transfer_match,
    100.0 * SUM(CASE WHEN _transfer_match = 'both' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS transfer_match_rate,
    1.0 * COUNT(*) / NULLIF(COUNT(DISTINCT shipment_id), 0) AS records_per_shipment
FROM {table};

-- query: route_delay_rates
-- Per-route metrics (validates analysis/route_analysis.py output).
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
GROUP BY route_id
ORDER BY delay_rate DESC, route ASC;

-- query: warehouse_delay_rates
-- Per-warehouse metrics (validates analysis/warehouse_analysis.py output).
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
GROUP BY warehouse_id
ORDER BY delay_rate DESC, warehouse ASC;
