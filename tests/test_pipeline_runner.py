"""Tests for pipeline/run_pipeline.py (orchestration only; tmp dirs)."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import pipeline.run_pipeline as runner
from pipeline.run_pipeline import (
    PipelineFailed,
    STAGE_ORDER,
    _apply_validation_gate,
    main,
    run_pipeline,
)


def tmp_layout(tmp_path: Path) -> dict[str, Path]:
    return {
        "raw": tmp_path / "raw",
        "processed": tmp_path / "processed",
        "runs": tmp_path / "runs",
        "output": tmp_path / "integrated.csv",
    }


def test_successful_showcase_run_records_all_stages(tmp_path: Path) -> None:
    layout = tmp_layout(tmp_path)
    manifest = run_pipeline(
        dataset="showcase",
        raw_dir=layout["raw"],
        processed_dir=layout["processed"],
        runs_dir=layout["runs"],
        output_path=layout["output"],
        seed=7,
        n_shipments=120,
    )
    assert manifest["overall_status"] in ("SUCCESS", "SUCCESS_WITH_WARNINGS")
    assert list(manifest["stages"]) == STAGE_ORDER
    for name, stage in manifest["stages"].items():
        assert stage["status"] in ("SUCCESS", "WARNING"), name
        assert stage["started_at"] and stage["finished_at"]
        assert stage["duration_seconds"] is not None and stage["duration_seconds"] >= 0
    assert layout["output"].is_file()
    integrated = pd.read_csv(layout["output"])
    assert len(integrated) > 120  # event grain
    assert manifest["outputs"]["integrated"]["rows"] == len(integrated)
    # SQL cross-check covers routes/warehouses, not just headline KPIs.
    sql_detail = manifest["stages"]["sql"]["detail"]
    assert sql_detail["comparisons"] >= 10
    assert sql_detail["all_match"] is True
    # Manifest written to disk and re-readable.
    stored = json.loads(Path(manifest["manifest_path"]).read_text(encoding="utf-8"))
    assert stored["run_id"] == manifest["run_id"]
    assert stored["dataset"] == "showcase"


def test_validation_warning_continues_pipeline(tmp_path: Path) -> None:
    layout = tmp_layout(tmp_path)
    manifest = run_pipeline(
        dataset="showcase",
        raw_dir=layout["raw"],
        processed_dir=layout["processed"],
        runs_dir=layout["runs"],
        output_path=layout["output"],
        seed=7,
        n_shipments=120,
    )
    validation = manifest["stages"]["validation"]
    # Showcase delivery events carry no warehouse: an honest WARNING.
    assert validation["status"] == "WARNING"
    assert manifest["stages"]["alerts"]["status"] in ("SUCCESS", "WARNING")
    assert manifest["overall_status"] == "SUCCESS_WITH_WARNINGS"
    assert manifest["warnings"]


def test_gate_unit_policy() -> None:
    ok_result = {"issues": [{"severity": "INFO", "check": "c", "message": "m"}]}
    proceed, errors, warnings = _apply_validation_gate({"a": ok_result})
    assert proceed and not errors and not warnings

    warn_result = {"issues": [{"severity": "WARNING", "check": "c", "message": "m"}]}
    proceed, errors, warnings = _apply_validation_gate({"a": warn_result})
    assert proceed and not errors and len(warnings) == 1

    err_result = {
        "issues": [
            {"severity": "WARNING", "check": "c", "message": "m"},
            {"severity": "ERROR", "check": "c", "message": "boom"},
        ]
    }
    proceed, errors, warnings = _apply_validation_gate({"a": err_result})
    assert not proceed and len(errors) == 1 and len(warnings) == 1


def test_validation_error_stops_pipeline_before_cleaning(tmp_path: Path) -> None:
    layout = tmp_layout(tmp_path)
    layout["raw"].mkdir(parents=True)
    # Scans without the required shipment_id column -> validation ERROR.
    pd.DataFrame({"timestamp": ["2024-01-01 08:00"], "delay_duration": [5.0]}).to_csv(
        layout["raw"] / "showcase_shipment_scans.csv", index=False
    )
    with pytest.raises(PipelineFailed, match="Validation gate"):
        run_pipeline(
            dataset="showcase",
            raw_dir=layout["raw"],
            processed_dir=layout["processed"],
            runs_dir=layout["runs"],
            output_path=layout["output"],
            skip_source_build=True,
        )
    manifests = list(layout["runs"].glob("run_*.json"))
    assert len(manifests) == 1
    stored = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert stored["overall_status"] == "FAILED"
    assert stored["stages"]["validation"]["status"] == "FAILED"
    assert stored["stages"]["validation"]["errors"]
    for name in STAGE_ORDER[STAGE_ORDER.index("validation") + 1:]:
        assert stored["stages"][name]["status"] == "SKIPPED", name
    # Nothing downstream was produced.
    assert not layout["output"].exists()
    assert list(layout["processed"].glob("*_cleaned.csv")) == []


def test_stage_failure_marks_failed_and_writes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("integration exploded")

    monkeypatch.setattr(runner, "build_integrated_dataset", boom)
    layout = tmp_layout(tmp_path)
    with pytest.raises(PipelineFailed, match="integration"):
        run_pipeline(
            dataset="showcase",
            raw_dir=layout["raw"],
            processed_dir=layout["processed"],
            runs_dir=layout["runs"],
            output_path=layout["output"],
            seed=7,
            n_shipments=60,
        )
    manifests = list(layout["runs"].glob("run_*.json"))
    assert len(manifests) == 1
    stored = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert stored["overall_status"] == "FAILED"
    stage = stored["stages"]["integration"]
    assert stage["status"] == "FAILED"
    assert any("RuntimeError" in e for e in stage["errors"])
    assert stored["errors"]


def test_manifest_has_no_secrets_or_datasets(tmp_path: Path) -> None:
    layout = tmp_layout(tmp_path)
    manifest = run_pipeline(
        dataset="showcase",
        raw_dir=layout["raw"],
        processed_dir=layout["processed"],
        runs_dir=layout["runs"],
        output_path=layout["output"],
        seed=7,
        n_shipments=60,
    )
    text = json.dumps(manifest).lower()
    assert "password" not in text and "api_key" not in text

    def all_keys(node: object) -> list[str]:
        if isinstance(node, dict):
            return list(node) + [k for v in node.values() for k in all_keys(v)]
        if isinstance(node, list):
            return [k for item in node for k in all_keys(item)]
        return []

    forbidden_keys = {"password", "secret", "token", "api_key", "credentials"}
    assert not (forbidden_keys & {k.lower() for k in all_keys(manifest)})
    for key in (
        "run_id", "dataset", "started_at", "finished_at", "overall_status",
        "stages", "inputs", "outputs", "validation_summary", "warnings", "errors",
    ):
        assert key in manifest, key
    # Inputs are metadata only (row counts, not embedded frames).
    assert manifest["inputs"]["scans"]["row_count"] > 0
    assert "delay_duration" not in manifest["inputs"]["scans"]


def test_runner_does_not_mutate_raw_sources(tmp_path: Path) -> None:
    layout = tmp_layout(tmp_path)
    manifest = run_pipeline(
        dataset="showcase",
        raw_dir=layout["raw"],
        processed_dir=layout["processed"],
        runs_dir=layout["runs"],
        output_path=layout["output"],
        seed=7,
        n_shipments=60,
    )
    before = {
        p.name: p.read_bytes()
        for p in sorted(layout["raw"].glob("*.csv"))
    }
    run_pipeline(
        dataset="showcase",
        raw_dir=layout["raw"],
        processed_dir=layout["processed"],
        runs_dir=layout["runs"],
        output_path=tmp_path / "integrated2.csv",
        seed=7,
        n_shipments=60,
        skip_source_build=True,
    )
    after = {p.name: p.read_bytes() for p in sorted(layout["raw"].glob("*.csv"))}
    assert before == after
    assert manifest["overall_status"] in ("SUCCESS", "SUCCESS_WITH_WARNINGS")


def test_unknown_dataset_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown dataset"):
        run_pipeline(dataset="nope")


def test_cli_help_and_lade_without_input() -> None:
    repo = Path(__file__).resolve().parent.parent
    help_proc = subprocess.run(
        [sys.executable, "-m", "pipeline.run_pipeline", "--help"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert help_proc.returncode == 0
    assert "--dataset" in help_proc.stdout

    missing = subprocess.run(
        [sys.executable, "-m", "pipeline.run_pipeline", "--dataset", "lade"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert missing.returncode != 0
    assert "LaDe input missing" in missing.stdout + missing.stderr


def test_cli_showcase_run_end_to_end(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parent.parent
    raw = tmp_path / "raw"
    proc = subprocess.run(
        [
            sys.executable, "-m", "pipeline.run_pipeline",
            "--dataset", "showcase",
            "--n-shipments", "60",
            "--raw-dir", str(raw),
            "--processed-dir", str(tmp_path / "processed"),
            "--runs-dir", str(tmp_path / "runs"),
            "--output", str(tmp_path / "integrated.csv"),
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert "Manifest:" in proc.stdout
    assert (tmp_path / "integrated.csv").is_file()
    assert len(list((tmp_path / "runs").glob("run_*.json"))) == 1
