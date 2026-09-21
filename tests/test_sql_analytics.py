"""Tests for the SQL analytics layer (temporary SQLite DBs only).

Uses a realistic integrated-like fixture (no production dependence).
Hand-computed expectations are documented per test.
"""

from pathlib import Path

import pandas as pd
import pytest

from analysis.kpis import compute_delay_kpis, compute_shipment_kpis
from analysis.route_analysis import route_metrics
from analysis.warehouse_analysis import warehouse_metrics
from pipeline.sql_database import (
    apply_views,
    execute_query,
    execute_sql_file,
    execute_sql_script,
    get_connection,
    get_sql_kpis,
    load_integrated_dataset,
    split_sql_sections,
    table_columns,
    validate_sql_vs_pandas,
)

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def integrated_fixture() -> pd.DataFrame:
    """5 rows / 4 shipments; hand-computed facts used across tests.

    Delayed shipments: S1 (30), S2 (60), S4 (20) -> delay_rate 75%.
    Delayed-record durations [30, 30, 60, 20]: avg 35, median 30,
    total (record level) 140; shipment-level total 110 (30+60+20).
    """
    return pd.DataFrame(
        {
            "shipment_id": ["S1", "S1", "S2", "S3", "S4"],
            "timestamp": [
                "2024-01-01 08:00:00",
                "2024-01-01 12:00:00",
                "2024-01-02 09:00:00",
                "2024-01-03 10:00:00",
                "2024-01-04 11:00:00",
            ],
            "warehouse_id": ["W1", "W2", "W1", "W1", "W2"],
            "route_id": ["R1", "R1", "R2", "R1", "R2"],
            "scan_type": ["pickup", "transfer", "pickup", "pickup", "delivery"],
            "status": ["in-transit", "in-transit", "delayed", "delivered", "delayed"],
            "delay_reason": ["traffic", "traffic", "weather", None, "customs"],
            "delay_duration": [30.0, 30.0, 60.0, 0.0, 20.0],
            "reported_at": [
                "2024-01-01 13:00:00",
                "2024-01-01 13:00:00",
                "2024-01-02 10:00:00",
                None,
                "2024-01-04 12:00:00",
            ],
            "transfer_id": ["T1", "T1", None, None, "T2"],
            "source_warehouse": ["W1", "W1", None, None, "W2"],
            "destination_warehouse": ["W2", "W2", None, None, "W1"],
            "_delay_match": ["both", "both", "both", "left-only", "both"],
            "_transfer_match": ["both", "both", "left-only", "left-only", "both"],
            "_record_source": ["scans"] * 5,
            "_source_datasets": ["scans+delays+transfers"] * 5,
            "_integration_key": ["S1", "S1", "S2", "S3", "S4"],
        }
    )


def loaded_db(fixture: pd.DataFrame | None = None):
    """Return (connection, fixture) with views applied; caller must close."""
    df = integrated_fixture() if fixture is None else fixture
    conn, report = load_integrated_dataset(df)
    assert report["inserted_rows"] == len(df)
    views = apply_views(conn)
    assert {
        "shipment_delay_summary",
        "route_delay_metrics",
        "warehouse_delay_metrics",
        "daily_delay_metrics",
    } <= set(views)
    return conn, df


def test_schema_sql_executes_with_expected_objects() -> None:
    conn = get_connection()
    try:
        execute_sql_script(conn, SQL_DIR / "schema.sql")
        columns = table_columns(conn, "integrated_logistics")
        for expected in (
            "shipment_id", "route_id", "warehouse_id", "delay_duration",
            "delay_reason", "timestamp", "_delay_match", "_transfer_match",
        ):
            assert expected in columns
        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        assert "idx_logistics_shipment" in indexes
    finally:
        conn.close()


def test_load_validates_row_count_and_preserves_source() -> None:
    df = integrated_fixture()
    before = df.copy(deep=True)
    conn, _ = loaded_db(df)
    try:
        count = execute_query(conn, 'SELECT COUNT(*) AS n FROM "integrated_logistics"')
        assert int(count.iloc[0]["n"]) == 5
    finally:
        conn.close()
    pd.testing.assert_frame_equal(df, before)


def test_load_refuses_columnless_frame() -> None:
    with pytest.raises(ValueError, match="no columns"):
        load_integrated_dataset(pd.DataFrame())


def test_datetime_columns_stored_as_iso_text(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "shipment_id": ["S1"],
            "timestamp": pd.to_datetime(["2024-01-01 08:00:00"], utc=True),
            "delay_duration": [10.0],
        }
    )
    db_file = tmp_path / "test.db"
    conn, _ = load_integrated_dataset(df, db_path=db_file)
    try:
        value = execute_query(conn, 'SELECT "timestamp" AS t FROM "integrated_logistics"')
        assert str(value.iloc[0]["t"]).startswith("2024-01-01")
        assert db_file.is_file()
    finally:
        conn.close()


def test_shipment_kpis_match_hand_computed() -> None:
    conn, _ = loaded_db()
    try:
        kpis = get_sql_kpis(conn)["shipment_kpis"].iloc[0]
    finally:
        conn.close()

    assert int(kpis["total_shipments"]) == 4
    assert int(kpis["delayed_shipments"]) == 3
    assert int(kpis["on_time_shipments"]) == 1
    assert float(kpis["delay_rate"]) == pytest.approx(75.0)
    assert float(kpis["on_time_rate"]) == pytest.approx(25.0)


def test_record_and_shipment_delay_kpis() -> None:
    conn, _ = loaded_db()
    try:
        kpis = get_sql_kpis(conn)
        record = kpis["delay_kpis_record"].iloc[0]
        median = kpis["delay_median_record"].iloc[0]["median_delay"]
        ship = kpis["shipment_delay_kpis"].iloc[0]
    finally:
        conn.close()

    # Record level over [30, 30, 60, 20].
    assert int(record["delayed_records"]) == 4
    assert float(record["average_delay"]) == pytest.approx(35.0)
    assert float(record["max_delay"]) == pytest.approx(60.0)
    assert float(record["min_delay"]) == pytest.approx(20.0)
    assert float(record["total_delay_record_level"]) == pytest.approx(140.0)
    assert float(median) == pytest.approx(30.0)
    # Shipment level over per-shipment MAX [30, 60, 20]: immune to S1's
    # duplicated 30 across its two integrated rows.
    assert int(ship["delayed_shipments"]) == 3
    assert float(ship["average_delay_per_shipment"]) == pytest.approx(110.0 / 3)
    assert float(ship["total_delay_shipment_level"]) == pytest.approx(110.0)


def test_operational_kpis() -> None:
    conn, _ = loaded_db()
    try:
        row = get_sql_kpis(conn)["operational_kpis"].iloc[0]
    finally:
        conn.close()

    assert float(row["delay_report_match_rate"]) == pytest.approx(80.0)
    assert float(row["transfer_match_rate"]) == pytest.approx(60.0)
    assert float(row["records_per_shipment"]) == pytest.approx(1.25)


def test_route_warehouse_rates_match_hand_computed() -> None:
    conn, _ = loaded_db()
    try:
        kpis = get_sql_kpis(conn)
        routes = kpis["route_delay_rates"].set_index("route")
        warehouses = kpis["warehouse_delay_rates"].set_index("warehouse")
    finally:
        conn.close()

    assert float(routes.loc["R1", "delay_rate"]) == pytest.approx(50.0)
    assert float(routes.loc["R2", "delay_rate"]) == pytest.approx(100.0)
    assert float(routes.loc["R1", "avg_delay"]) == pytest.approx(30.0)
    assert float(warehouses.loc["W1", "delay_rate"]) == pytest.approx(200.0 / 3)
    assert float(warehouses.loc["W2", "delay_rate"]) == pytest.approx(100.0)
    assert int(warehouses.loc["W1", "shipments"]) == 3


def test_views_agree_with_metrics_queries() -> None:
    conn, _ = loaded_db()
    try:
        kpis = get_sql_kpis(conn)
        for view, section in (
            ("route_delay_metrics", "route_delay_rates"),
            ("warehouse_delay_metrics", "warehouse_delay_rates"),
        ):
            from_view = execute_query(conn, f'SELECT * FROM "{view}"')
            pd.testing.assert_frame_equal(
                from_view.sort_values(by=from_view.columns[0], kind="mergesort").reset_index(drop=True),
                kpis[section].sort_values(by=kpis[section].columns[0], kind="mergesort").reset_index(drop=True),
                check_dtype=False,
            )
        summary = execute_query(conn, 'SELECT * FROM "shipment_delay_summary"')
        assert len(summary) == 4  # one row per shipment: dedup grain
        assert int(summary.set_index("shipment_id").loc["S1", "records"]) == 2
        assert float(summary.set_index("shipment_id").loc["S1", "shipment_delay"]) == pytest.approx(30.0)
    finally:
        conn.close()


def test_analysis_queries_grouping_and_ranking() -> None:
    conn, _ = loaded_db()
    try:
        results = execute_sql_file(conn, SQL_DIR / "analysis.sql")
        top = results["top_delayed_routes"].iloc[0]
        assert top["route"] == "R2"  # highest delay rate first

        busiest = results["busiest_warehouses"].iloc[0]
        assert busiest["warehouse"] == "W1"

        reasons = results["delay_reasons_ranked"].set_index("delay_reason")
        assert int(reasons.loc["traffic", "records"]) == 2
        assert reasons["records"].sum() == 4  # NULL reason excluded

        ranking = results["route_ranking"].set_index("route")
        assert int(ranking.loc["R2", "delay_rate_rank"]) == 1
        assert int(ranking.loc["R1", "delay_rate_rank"]) == 2

        trend = results["rolling_7d_avg_delay_rate"]
        assert len(trend) == 4  # four distinct days
        # Fewer than 7 days: full-window rule yields NULL, not partial means.
        assert trend["rolling_7d_avg_delay_rate"].isna().all()
    finally:
        conn.close()


def test_window_event_order_and_lag_gap() -> None:
    conn, _ = loaded_db()
    try:
        results = execute_sql_file(conn, SQL_DIR / "analysis.sql")
        order = results["shipment_event_order"]
        s1 = order[order["shipment_id"] == "S1"].sort_values("event_sequence")
        assert s1["event_sequence"].tolist() == [1, 2]

        gaps = results["previous_event_gap"]
        s1_gap = gaps[(gaps["shipment_id"] == "S1") & gaps["previous_event_time"].notna()]
        assert len(s1_gap) == 1
        assert float(s1_gap.iloc[0]["gap_minutes"]) == pytest.approx(240.0)
        # First events have no predecessor.
        assert int(gaps["previous_event_time"].isna().sum()) == 4
    finally:
        conn.close()


def test_shipment_grain_join_validates_duplication() -> None:
    # Joining the deduped shipment grain back to base rows quantifies the
    # one-to-many multiplication instead of hiding it.
    conn, _ = loaded_db()
    try:
        frame = execute_query(
            conn,
            """
            SELECT s.shipment_id, s.records AS base_rows, d.records AS summary_rows
            FROM (
                SELECT shipment_id, COUNT(*) AS records
                FROM "integrated_logistics" GROUP BY shipment_id
            ) AS s
            JOIN shipment_delay_summary AS d USING (shipment_id)
            """,
        )
        assert len(frame) == 4
        assert int(frame["base_rows"].sum()) == 5
        assert int(frame["summary_rows"].sum()) == 5
        assert int(frame.set_index("shipment_id").loc["S1", "base_rows"]) == 2
    finally:
        conn.close()


def test_zero_denominator_yields_null_not_error() -> None:
    empty = integrated_fixture().iloc[0:0]
    conn, _ = loaded_db(empty)
    try:
        kpis = get_sql_kpis(conn)
        ship = kpis["shipment_kpis"].iloc[0]
        assert int(ship["total_shipments"]) == 0
        assert ship["delay_rate"] is None or pd.isna(ship["delay_rate"])
        record = kpis["delay_kpis_record"].iloc[0]
        assert int(record["delayed_records"]) == 0
        assert record["average_delay"] is None or pd.isna(record["average_delay"])
        oper = kpis["operational_kpis"].iloc[0]
        assert oper["transfer_match_rate"] is None or pd.isna(oper["transfer_match_rate"])
    finally:
        conn.close()


def test_sql_pandas_consistency() -> None:
    conn, df = loaded_db()
    try:
        kpis = get_sql_kpis(conn)
        ship_sql = kpis["shipment_kpis"].iloc[0]
        rec_sql = kpis["delay_kpis_record"].iloc[0]
        oper_sql = kpis["operational_kpis"].iloc[0]
        routes_sql = kpis["route_delay_rates"].set_index("route")
        wh_sql = kpis["warehouse_delay_rates"].set_index("warehouse")

        ship_pd = compute_shipment_kpis(df)
        delay_pd = compute_delay_kpis(df)
        routes_pd = route_metrics(df).set_index("route")
        wh_pd = warehouse_metrics(df).set_index("warehouse")

        report = validate_sql_vs_pandas(
            [
                {"name": "total_shipments", "sql": ship_sql["total_shipments"],
                 "pandas": ship_pd["total_shipments"]},
                {"name": "delayed_shipments", "sql": ship_sql["delayed_shipments"],
                 "pandas": ship_pd["delayed_shipments"]},
                {"name": "delay_rate", "sql": ship_sql["delay_rate"],
                 "pandas": ship_pd["delay_rate"]},
                {"name": "average_delay_record", "sql": rec_sql["average_delay"],
                 "pandas": delay_pd["average_delay"]},
                {"name": "total_delay_record", "sql": rec_sql["total_delay_record_level"],
                 "pandas": delay_pd["total_delay"]},
                {"name": "route_R1_delay_rate", "sql": routes_sql.loc["R1", "delay_rate"],
                 "pandas": routes_pd.loc["R1", "delay_rate"]},
                {"name": "warehouse_W2_shipments", "sql": wh_sql.loc["W2", "shipments"],
                 "pandas": wh_pd.loc["W2", "shipments"]},
                {"name": "transfer_match_rate", "sql": oper_sql["transfer_match_rate"],
                 "pandas": 60.0},
            ]
        )
    finally:
        conn.close()

    assert report["all_match"], report["comparisons"]


def test_sql_section_helpers_reject_bad_input() -> None:
    with pytest.raises(ValueError, match="Duplicate SQL section"):
        split_sql_sections("-- query: a\nSELECT 1;\n-- query: a\nSELECT 2;")
    conn = get_connection()
    try:
        with pytest.raises(FileNotFoundError, match="Metrics SQL file"):
            get_sql_kpis(conn, metrics_path=SQL_DIR / "no_such_file.sql")
        with pytest.raises(FileNotFoundError, match="Views SQL file"):
            apply_views(conn, views_path=SQL_DIR / "no_such_file.sql")
    finally:
        conn.close()


def test_validate_sql_vs_pandas_reports_mismatch() -> None:
    report = validate_sql_vs_pandas(
        [
            {"name": "ok", "sql": 75.0, "pandas": 75.0},
            {"name": "bad", "sql": 75.0, "pandas": 50.0},
            {"name": "both_missing", "sql": None, "pandas": None},
            {"name": "one_missing", "sql": 1.0, "pandas": None},
        ]
    )
    assert report["all_match"] is False
    by_name = {d["name"]: d for d in report["comparisons"]}
    assert by_name["ok"]["match"] is True
    assert by_name["bad"]["match"] is False
    assert by_name["both_missing"]["match"] is True
    assert by_name["one_missing"]["match"] is False
