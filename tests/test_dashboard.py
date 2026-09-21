"""Tests for dashboard helpers (pure logic only; no Streamlit runtime)."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from analysis.cascade_analysis import reconstruct_shipment_journey
from app.components.charts import (
    bar_chart,
    delay_status_donut,
    depth_chart,
    journey_timeline,
    trend_line,
)
from app.components.data_loader import (
    build_demo_dataset,
    discover_processed_datasets,
    load_processed_csv,
)
from app.components.filters import apply_filters, available_filter_options
from app.components.metrics import (
    format_duration,
    format_number,
    format_percent,
    prepare_kpi_cards,
)


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "shipment_id": ["S1", "S1", "S2", "S3"],
            "timestamp": [
                "2024-01-01 08:00", "2024-01-02 09:00",
                "2024-01-03 10:00", "2024-01-04 11:00",
            ],
            "route_id": ["R1", "R1", "R2", "R1"],
            "warehouse_id": ["W1", "W2", "W1", "W1"],
            "delay_reason": ["traffic", "traffic", "weather", "none"],
            "delay_duration": [30.0, 20.0, 60.0, 0.0],
        }
    )


def test_apply_filters_each_dimension_and_no_mutation() -> None:
    df = sample_frame()
    before = df.copy(deep=True)

    assert len(apply_filters(df, routes=["R1"])) == 3
    assert len(apply_filters(df, warehouses=["W2"])) == 1
    assert len(apply_filters(df, reasons=["weather"])) == 1
    assert len(apply_filters(df, start_date="2024-01-03")) == 2
    assert len(apply_filters(df, end_date="2024-01-02")) == 2
    assert len(apply_filters(df, delay_status="Delayed")) == 3
    assert len(apply_filters(df, delay_status="On-time")) == 1
    combined = apply_filters(df, routes=["R1"], delay_status="Delayed",
                             start_date="2024-01-02")
    assert len(combined) == 1
    pd.testing.assert_frame_equal(df, before)


def test_apply_filters_empty_result_and_bad_status() -> None:
    df = sample_frame()
    assert apply_filters(df, routes=["NOPE"]).empty
    with pytest.raises(ValueError, match="delay_status"):
        apply_filters(df, delay_status="Maybe")


def test_apply_filters_ignores_missing_columns() -> None:
    df = pd.DataFrame({"shipment_id": ["S1", "S2"]})
    # No route/duration/timestamp columns: selections are no-ops, not errors.
    assert len(apply_filters(df, routes=["R1"], delay_status="Delayed")) == 2
    assert apply_filters(pd.DataFrame({"a": []})).empty


def test_available_filter_options_reflects_schema() -> None:
    options = available_filter_options(sample_frame())
    assert options["routes"] == ["R1", "R2"]
    assert options["warehouses"] == ["W1", "W2"]
    assert options["delay_status_available"] is True
    assert options["min_date"] == "2024-01-01"

    sparse = available_filter_options(pd.DataFrame({"shipment_id": ["S1"]}))
    assert sparse["routes"] == []
    assert sparse["timestamp_column"] is None
    assert sparse["delay_status_available"] is False


def test_charts_return_figures_and_survive_empty() -> None:
    df = sample_frame()
    trend = pd.DataFrame({"period": ["2024-01-01", "2024-01-02"], "delay_rate": [50.0, 25.0]})
    for figure in (
        trend_line(trend),
        bar_chart(df, "route_id", "delay_duration", "t"),
        delay_status_donut(3, 1),
        depth_chart(pd.DataFrame({"cascade_depth": [1, 2, 2]})),
    ):
        assert isinstance(figure, go.Figure)
        assert len(figure.data) > 0
    for figure in (
        trend_line(pd.DataFrame()),
        bar_chart(pd.DataFrame(), "a", "b", "t"),
        delay_status_donut(0, 0),
        depth_chart(pd.DataFrame()),
        journey_timeline(pd.DataFrame()),
    ):
        assert isinstance(figure, go.Figure)


def test_journey_timeline_uses_event_structure() -> None:
    events, _ = reconstruct_shipment_journey(sample_frame())
    figure = journey_timeline(events)
    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 2  # delayed + on-time traces


def test_kpi_prep_formats_and_handles_none() -> None:
    cards = prepare_kpi_cards(
        {"total_shipments": 100, "delayed_shipments": 20,
         "delay_rate": 20.0, "on_time_rate": 80.0},
        {"average_delay": 35.5},
        {"candidate_count": 3},
    )
    by_label = {c["label"]: c["value"] for c in cards}
    assert by_label["Delay rate"] == "20.0%"
    assert by_label["Average delay"] == "35.5"
    assert by_label["Cascade candidates"] == "3"

    missing = prepare_kpi_cards({}, {}, {})
    assert all(c["value"] == "n/a" for c in missing)
    assert format_percent(None) == "n/a"
    assert format_number(float("nan")) == "n/a"
    assert format_duration(10) == "10.0"


def test_demo_dataset_deterministic_and_valid() -> None:
    first, second = build_demo_dataset(), build_demo_dataset()
    pd.testing.assert_frame_equal(first, second)
    assert len(first) > 60  # extra downstream events included
    assert set(first["shipment_id"].nunique() for _ in [0]) == {60}
    assert (first["delay_duration"] >= 0).all()
    assert first["_demo_source"].all()


def test_data_loader_discovers_orders_and_reads(tmp_path: Path) -> None:
    (tmp_path / "b.csv").write_text("a\n1\n", encoding="utf-8")
    (tmp_path / "integrated_logistics_data.csv").write_text("a\n2\n", encoding="utf-8")
    found = discover_processed_datasets(tmp_path)
    assert [p.name for p in found] == ["integrated_logistics_data.csv", "b.csv"]
    assert len(load_processed_csv(tmp_path / "b.csv")) == 1
    assert discover_processed_datasets(tmp_path / "missing") == []
    with pytest.raises(FileNotFoundError, match="not found"):
        load_processed_csv(tmp_path / "missing.csv")


def test_app_renders_pages_without_exception() -> None:
    """Smoke test: boot the Streamlit app on demo data, visit key pages."""
    streamlit = pytest.importorskip("streamlit")
    app_test = pytest.importorskip("streamlit.testing.v1")
    entrypoint = Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py"
    at = app_test.AppTest.from_file(entrypoint, default_timeout=60)
    at.run()
    assert not at.exception
    assert len(at.metric) == 6  # overview KPI cards on demo data
    at.sidebar.radio[0].set_value("Cascades").run()
    assert not at.exception
    assert len(at.metric) >= 4  # cascade summary cards
    at.sidebar.radio[0].set_value("Alerts").run()
    assert not at.exception
    assert len(at.metric) >= 4  # alert summary cards
    _ = streamlit  # Widgets render through the AppTest harness above.
