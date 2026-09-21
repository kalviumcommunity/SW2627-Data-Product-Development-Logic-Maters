-- Business analytical queries (SQLite). `{table}` is rendered by
-- pipeline/sql_database.py; every section is `-- query: <name>`.
-- All groupings use actual canonical columns; HAVING only excludes NULL
-- groups (no business thresholds - those belong to later work, if ever).
-- Window functions answer real needs: ranking entities, ordering each
-- shipment's events, measuring gaps to the previous event, and rolling
-- daily averages.

-- query: top_delayed_routes
-- Routes with the most delayed shipments (limit is presentational).
SELECT route, shipments, delayed_shipments, delay_rate, avg_delay
FROM route_delay_metrics
ORDER BY delayed_shipments DESC, delay_rate DESC
LIMIT 10;

-- query: busiest_warehouses
-- Warehouses handling the most shipments.
SELECT warehouse, shipments, records, delayed_shipments, delay_rate
FROM warehouse_delay_metrics
ORDER BY shipments DESC, warehouse ASC
LIMIT 10;

-- query: delay_reasons_ranked
-- Most frequent delay reasons with their average duration.
SELECT
    delay_reason,
    COUNT(*) AS records,
    100.0 * COUNT(*) / (SELECT NULLIF(COUNT(*), 0) FROM {table}) AS pct_of_records,
    AVG(delay_duration) AS avg_delay
FROM {table}
WHERE delay_reason IS NOT NULL
GROUP BY delay_reason
HAVING delay_reason IS NOT NULL
ORDER BY records DESC;

-- query: routes_with_repeated_delays
-- Routes ordered by delayed-shipment volume (repeated delay activity).
SELECT route, shipments, delayed_shipments, delay_rate
FROM route_delay_metrics
WHERE delayed_shipments > 0
ORDER BY delayed_shipments DESC, delay_rate DESC;

-- query: route_ranking
-- Rank routes by delay rate (RANK leaves gaps on ties).
SELECT
    route, shipments, delayed_shipments, delay_rate,
    RANK() OVER (ORDER BY delay_rate DESC) AS delay_rate_rank
FROM route_delay_metrics;

-- query: warehouse_ranking
-- Rank warehouses by shipment volume (DENSE_RANK: no gaps on ties).
SELECT
    warehouse, shipments, delayed_shipments, delay_rate,
    DENSE_RANK() OVER (ORDER BY shipments DESC) AS volume_rank
FROM warehouse_delay_metrics;

-- query: shipment_event_order
-- Order each shipment's operational records chronologically.
SELECT
    shipment_id,
    timestamp,
    warehouse_id,
    route_id,
    delay_duration,
    ROW_NUMBER() OVER (
        PARTITION BY shipment_id ORDER BY timestamp ASC
    ) AS event_sequence
FROM {table}
WHERE timestamp IS NOT NULL
ORDER BY shipment_id ASC, event_sequence ASC;

-- query: previous_event_gap
-- For each event, the previous event's timestamp and the gap in minutes.
-- Sequencing foundation only: no judgement about cascades is made here.
SELECT
    shipment_id,
    timestamp AS event_time,
    LAG(timestamp) OVER (
        PARTITION BY shipment_id ORDER BY timestamp ASC
    ) AS previous_event_time,
    (JULIANDAY(timestamp) - JULIANDAY(LAG(timestamp) OVER (
        PARTITION BY shipment_id ORDER BY timestamp ASC
    ))) * 24.0 * 60.0 AS gap_minutes
FROM {table}
WHERE timestamp IS NOT NULL
ORDER BY shipment_id ASC, event_time ASC;

-- query: rolling_7d_avg_delay_rate
-- 7-day rolling average of the daily delay rate over calendar days.
-- Requires a full 7-day window (matches analysis/delay_analysis.py
-- min_periods = window); early/sparse days yield NULL, not partial means.
SELECT
    day,
    delay_rate,
    CASE
        WHEN COUNT(*) OVER (
            ORDER BY day ASC ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) = 7 THEN AVG(delay_rate) OVER (
            ORDER BY day ASC ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )
    END AS rolling_7d_avg_delay_rate
FROM daily_delay_metrics
ORDER BY day ASC;
