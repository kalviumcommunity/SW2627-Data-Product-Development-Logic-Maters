"""Tests for reports/report_generator.py (tmp fixtures only)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.run_pipeline import run_pipeline
from reports.report_generator import (
    build_report,
    discover_runs,
    generate_report,
    load_manifest,
    render_html,
    render_markdown,
    resolve_integrated_frame,
)


@pytest.fixture(scope="module")
def showcase_run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """One small deterministic pipeline run shared by report tests."""
    tmp_path = tmp_path_factory.mktemp("showcase_run")
    manifest = run_pipeline(
        dataset="showcase",
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        runs_dir=tmp_path / "runs",
        output_path=tmp_path / "integrated.csv",
        seed=7,
        n_shipments=100,
    )
    manifest_path = Path(manifest["manifest_path"])
    return {"manifest": manifest, "manifest_path": manifest_path, "tmp": tmp_path}


def lade_like_run(tmp_path: Path) -> Path:
    """Partial LaDe-style fixture: routes + durations, no warehouse/reason/transfer."""
    rows = [
        {"shipment_id": "L1", "timestamp": "2024-01-01 08:00",
         "route_id": "region_1", "delay_duration": 30.0},
        {"shipment_id": "L1", "timestamp": "2024-01-02 08:00",
         "route_id": "region_1", "delay_duration": 45.0},
        {"shipment_id": "L2", "timestamp": "2024-01-03 08:00",
         "route_id": "region_2", "delay_duration": 0.0},
    ]
    integrated = tmp_path / "lade_integrated.csv"
    pd.DataFrame(rows).to_csv(integrated, index=False)
    manifest = {
        "run_id": "lade-fixture-1",
        "dataset": "lade",
        "started_at": "2024-02-01T00:00:00+00:00",
        "finished_at": "2024-02-01T00:01:00+00:00",
        "overall_status": "SUCCESS_WITH_WARNINGS",
        "params": {"input": None},
        "stages": {
            "validation": {
                "stage": "validation", "status": "WARNING",
                "started_at": "2024-02-01T00:00:00+00:00",
                "finished_at": "2024-02-01T00:01:00+00:00",
                "duration_seconds": 1.0, "detail": {},
                "warnings": ["scans: [missing_values] demo warning"],
                "errors": [],
            }
        },
        "inputs": {"scans": {"row_count": 3}},
        "outputs": {"integrated": {"path": str(integrated), "rows": 3, "columns": 4}},
        "validation_summary": {"scans": {"status": "WARNING", "issue_count": 1}},
        "warnings": ["scans: [missing_values] demo warning"],
        "errors": [],
    }
    manifest_path = tmp_path / "run_lade-fixture-1.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_report_from_successful_showcase_run(showcase_run: dict) -> None:
    report = build_report(showcase_run["manifest_path"])
    assert report["run_id"] == showcase_run["manifest"]["run_id"]
    assert report["kpis"]["total_shipments"] == 100
    assert report["kpis"]["delayed_shipments"] > 0
    assert report["cascade"]["candidate_count"] > 0
    assert report["alerts"]["total"] > 0


def test_markdown_generation(showcase_run: dict, tmp_path: Path) -> None:
    destination = generate_report(
        showcase_run["manifest_path"], format="markdown",
        output_path=tmp_path / "report.md",
    )
    text = destination.read_text(encoding="utf-8")
    assert text.startswith("# Cascading Delay Intelligence Report")
    for section in (
        "## 1. Executive Summary", "## 3. Data Quality", "## 4. Operational KPIs",
        "## 6. Route Intelligence", "## 7. Cascade Intelligence",
        "## 9. Alerts", "## 12. Limitations",
    ):
        assert section in text


def test_html_generation(showcase_run: dict, tmp_path: Path) -> None:
    destination = generate_report(
        showcase_run["manifest_path"], format="html",
        output_path=tmp_path / "report.html",
    )
    text = destination.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert "<table>" in text
    assert "Cascading Delay Intelligence Report" in text
    with pytest.raises(ValueError, match="Unsupported format"):
        generate_report(showcase_run["manifest_path"], format="pdf")


def test_executive_summary_has_real_kpis(showcase_run: dict) -> None:
    text = render_markdown(build_report(showcase_run["manifest_path"]))
    kpis = showcase_run["manifest"]["stages"]["analytics"]["detail"]["kpis"]
    assert f"{kpis['total_shipments']:,}" in text
    assert f"{kpis['delayed_shipments']:,}" in text


def test_route_risk_section_has_real_metrics(showcase_run: dict) -> None:
    report = build_report(showcase_run["manifest_path"])
    assert report["risk_table"]
    text = render_markdown(report)
    first_route = report["risk_table"][0]["route"]
    assert first_route in text
    assert "Historical conditional probability" in text


def test_cascade_section_has_real_metrics(showcase_run: dict) -> None:
    report = build_report(showcase_run["manifest_path"])
    count = report["cascade"]["candidate_count"]
    assert count > 0
    text = render_markdown(report)
    assert f"{count:,}" in text
    assert "depth" in text.lower()


def test_alerts_section_has_real_alerts(showcase_run: dict) -> None:
    report = build_report(showcase_run["manifest_path"])
    assert report["alerts"]["total"] > 0
    text = render_markdown(report)
    first_id = report["alerts"]["rows"][0]["alert_id"]
    assert first_id in text
    assert "Configured thresholds" in text


def test_validation_warnings_appear(showcase_run: dict) -> None:
    report = build_report(showcase_run["manifest_path"])
    assert report["warnings"]
    text = render_markdown(report)
    assert "Warnings (shown, not hidden)" in text
    for warning in report["warnings"][:3]:
        assert warning[:40] in text


def test_partial_data_honest_empty_states(tmp_path: Path) -> None:
    manifest_path = lade_like_run(tmp_path)
    report = build_report(manifest_path)
    assert report["warehouses_table"] == []
    assert report["reasons_table"] == []
    text = render_markdown(report)
    assert "Warehouse-level analysis is unavailable for this dataset." in text
    assert "Delay reasons are not available in this dataset." in text
    # Still generates: KPIs + the one cascade come through.
    assert report["kpis"]["total_shipments"] == 2
    assert report["cascade"]["candidate_count"] == 1


def test_synthetic_label_and_lade_distinction(
    showcase_run: dict, tmp_path: Path
) -> None:
    showcase = build_report(showcase_run["manifest_path"])
    assert "SYNTHETIC" in showcase["source_description"]
    assert "synthetic" in render_markdown(showcase).lower()
    lade = build_report(lade_like_run(tmp_path))
    assert "SYNTHETIC" not in lade["source_description"]
    assert "LaDe" in lade["source_label"]
    lade_text = render_markdown(lade).lower()
    # Tmp-dir names may leak fixture words into file paths; the badge and
    # limitation prose must stay clean.
    assert "SYNTHETIC" not in render_markdown(lade)
    assert "synthetic showcase" not in lade_text
    assert "synthetic data" not in lade_text


def test_empirical_risk_not_labeled_ml(showcase_run: dict) -> None:
    text = render_markdown(build_report(showcase_run["manifest_path"])).lower()
    assert "not an ml prediction" in text
    for forbidden in ("forecast", "machine-learning model", "trained model", "predicts that"):
        assert forbidden not in text


def test_deterministic_generation(showcase_run: dict) -> None:
    first = render_markdown(build_report(showcase_run["manifest_path"]))
    second = render_markdown(build_report(showcase_run["manifest_path"]))
    assert first == second
    report = build_report(showcase_run["manifest_path"])
    assert render_html(report) == render_html(build_report(showcase_run["manifest_path"]))


def test_no_secrets_in_reports(showcase_run: dict, tmp_path: Path) -> None:
    manifest_path = lade_like_run(tmp_path)
    cases = [
        ("markdown", manifest_path),
        ("html", showcase_run["manifest_path"]),
    ]
    for format_name, path in cases:
        report = build_report(path)
        text = (render_markdown if format_name == "markdown" else render_html)(report)
        # Tmp-dir names leak fixture words into echoed file paths; scan the
        # prose, not local paths.
        prose = "\n".join(
            line for line in text.splitlines()
            if "lade_integrated.csv" not in line and "integrated.csv" not in line
        ).lower()
        for secret in ("password", "api_key", "secret", "bearer ", "smtp"):
            assert secret not in prose


def test_missing_optional_artifact_does_not_crash(tmp_path: Path) -> None:
    manifest_path = lade_like_run(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["stages"] = {}  # stage detail unavailable
    manifest["validation_summary"] = {}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = build_report(manifest_path)
    assert report["kpis"]["total_shipments"] == 2
    render_markdown(report)


def test_missing_manifest_fails_clearly(tmp_path: Path) -> None:
    missing = tmp_path / "run_nope.json"
    with pytest.raises(FileNotFoundError, match="Run manifest not found"):
        load_manifest(missing)
    with pytest.raises(FileNotFoundError, match="Run manifest not found"):
        build_report(missing)


def test_missing_integrated_output_fails_clearly(tmp_path: Path) -> None:
    manifest_path = lade_like_run(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"]["integrated"]["path"] = str(tmp_path / "gone.csv")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="missing"):
        resolve_integrated_frame(load_manifest(manifest_path))


def test_discover_runs_lists_manifests(showcase_run: dict) -> None:
    from reports.report_generator import discover_runs

    runs = discover_runs(showcase_run["tmp"] / "runs")
    assert len(runs) == 1
    assert runs[0]["run_id"] == showcase_run["manifest"]["run_id"]
    assert discover_runs(showcase_run["tmp"] / "nope") == []


def test_streamlit_reports_page_smoke() -> None:
    streamlit = pytest.importorskip("streamlit")
    app_test = pytest.importorskip("streamlit.testing.v1")
    _ = streamlit
    from pathlib import Path as _Path

    entrypoint = _Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py"
    at = app_test.AppTest.from_file(str(entrypoint), default_timeout=180)
    at.run()
    assert not at.exception
    at.sidebar.radio[0].set_value("Reports").run()
    assert not at.exception
    options = [str(o) for o in at.selectbox[0].options]
    showcase = next((o for o in options if "showcase" in o and "SUCCESS" in o), None)
    assert showcase is not None, f"no successful showcase run in {options}"
    at.selectbox[0].set_value(showcase).run()
    assert not at.exception
    assert any("route cascade risk" in str(s.value).lower() for s in at.subheader)
    assert len(at.download_button) == 2
