"""Unified pipeline runner for Cascading Delay Intelligence (orchestration only).

Executes the existing pipeline stages in one controlled path::

    source build -> ingestion -> validation -> [GATE] -> cleaning
        -> integration -> analytics -> sql -> cascade -> route_risk
        -> alerts -> run manifest

Every calculation below delegates to the established modules; this file
contains no business logic of its own (no cleaning rules, no KPIs, no
cascade definition, no thresholds). Stage functions only coordinate,
time, record metadata, and enforce the validation gate:

* validation ERROR  -> stop before cleaning; downstream stages SKIPPED;
  overall FAILED; manifest still written; CLI exits non-zero.
* validation WARNING -> continue; warnings recorded; overall
  SUCCESS_WITH_WARNINGS.
* PASS -> SUCCESS.

Programmatic use::

    from pipeline.run_pipeline import run_pipeline
    manifest = run_pipeline(dataset="showcase")

CLI::

    python -m pipeline.run_pipeline --dataset showcase
    python -m pipeline.run_pipeline --dataset lade --input path/to/pickup.csv
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.alerts import generate_alerts, summarize_alerts
from analysis.cascade_analysis import detect_cascade_candidates
from analysis.delay_analysis import (
    delay_over_time,
    delay_reason_breakdown,
)
from analysis.kpis import (
    compute_delay_kpis,
    compute_kpis,
    compute_shipment_kpis,
)
from analysis.route_analysis import route_metrics
from analysis.route_risk import route_cascade_risk
from analysis.warehouse_analysis import warehouse_metrics
from pipeline.cleaning import clean_file
from pipeline.ingestion import get_dataset_metadata, load_dataset
from pipeline.integration import (
    build_integrated_dataset,
    save_integrated_dataset,
)
from pipeline.sql_database import (
    DEFAULT_TABLE,
    apply_views,
    execute_query,
    get_connection,
    load_integrated_dataset,
    split_sql_sections,
    validate_sql_vs_pandas,
)
from pipeline.validation import validate_dataset

PathLike = Union[str, Path]

STAGE_ORDER = [
    "ingestion",
    "validation",
    "cleaning",
    "integration",
    "analytics",
    "sql",
    "cascade",
    "route_risk",
    "alerts",
]

# Overall pipeline statuses.
SUCCESS = "SUCCESS"
SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
FAILED = "FAILED"

DEFAULT_RUNS_DIR = Path("data/processed/runs")
SHOWCASE_INTEGRATED_FILENAME = "integrated_logistics_showcase.csv"
LADE_INTEGRATED_FILENAME = "integrated_logistics_lade.csv"

# Validation declarations per source role (interpreted by
# pipeline.validation; the runner only passes them through).
VALIDATION_CONFIGS: dict[str, dict[str, Any]] = {
    "scans": {
        "required_columns": ["shipment_id", "timestamp"],
        "identifier_columns": ["shipment_id"],
        "timestamp_columns": ["timestamp"],
        "numeric_columns": ["delay_duration"],
    },
    "delays": {
        "required_columns": ["shipment_id"],
        "identifier_columns": ["shipment_id"],
        "timestamp_columns": ["reported_at"],
        "numeric_columns": ["delay_duration"],
    },
    "transfers": {
        "required_columns": ["shipment_id", "transfer_id"],
        "identifier_columns": ["shipment_id", "transfer_id"],
        "timestamp_columns": ["transfer_time"],
        "numeric_columns": [],
    },
}

# Cleaning declarations for the LaDe schema (caller-declared per the
# cleaning layer's contract; showcase configs live with its generator).
LADE_CLEANING_CONFIGS: dict[str, dict[str, Any]] = {
    "scans": {
        "identifier_columns": ["shipment_id"],
        "numeric_columns": ["delay_duration", "lng", "lat"],
        "categorical_columns": ["route_id", "status", "event_type", "city"],
        "datetime_columns": ["timestamp", "scheduled_time"],
        "non_negative_columns": ["delay_duration"],
    },
    "delays": {
        "identifier_columns": ["shipment_id", "delay_id"],
        "numeric_columns": ["delay_duration", "initial_delay_duration"],
        "categorical_columns": ["route_id", "delay_stage", "city"],
        "datetime_columns": ["reported_at"],
        "non_negative_columns": ["delay_duration", "initial_delay_duration"],
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StageRecord:
    """Structured execution status for one pipeline stage."""

    stage: str
    status: str = "PENDING"  # PENDING/RUNNING/SUCCESS/WARNING/FAILED/SKIPPED
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    detail: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "detail": self.detail,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class _Timer:
    """Context manager stamping a StageRecord's timing fields."""

    def __init__(self, record: StageRecord) -> None:
        self.record = record

    def __enter__(self) -> StageRecord:
        self.record.status = "RUNNING"
        self.record.started_at = _now_iso()
        self._start = time.perf_counter()
        return self.record

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self.record.finished_at = _now_iso()
        self.record.duration_seconds = round(time.perf_counter() - self._start, 3)
        return False


class PipelineFailed(RuntimeError):
    """Raised when the pipeline stops (gate or stage failure)."""


def _apply_validation_gate(
    validation_results: dict[str, dict[str, Any]],
) -> tuple[bool, list[str], list[str]]:
    """Interpret validation outcomes without reimplementing checks.

    Returns ``(proceed, errors, warnings)``: any ERROR-level issue in any
    source stops the pipeline; WARNING-only continues with warnings
    recorded; clean results proceed silently.
    """
    errors: list[str] = []
    warnings: list[str] = []
    for name, result in validation_results.items():
        for issue in result.get("issues", []):
            severity = str(issue.get("severity", "INFO"))
            message = f"{name}: [{issue.get('check')}] {issue.get('message')}"
            if severity == "ERROR":
                errors.append(message)
            elif severity == "WARNING":
                warnings.append(message)
    return (not errors, errors, warnings)


def _role_of(filename: str) -> Optional[str]:
    """Map a source filename to its integration role (scan/delay/transfer)."""
    lowered = filename.lower()
    if "scan" in lowered:
        return "scans"
    if "delay" in lowered:
        return "delays"
    if "transfer" in lowered:
        return "transfers"
    return None


def _discover_source_files(raw_dir: Path) -> dict[str, Path]:
    """Find role-bearing raw CSVs in a directory (read-only)."""
    sources: dict[str, Path] = {}
    if not raw_dir.is_dir():
        return sources
    for path in sorted(raw_dir.glob("*.csv"), key=lambda p: p.name):
        role = _role_of(path.name)
        if role and role not in sources:
            sources[role] = path
    return sources


def _cleaning_configs(dataset: str) -> dict[str, dict[str, Any]]:
    if dataset == "showcase":
        from pipeline.synthetic_showcase import CLEANING_CONFIGS

        return {
            "scans": CLEANING_CONFIGS["showcase_shipment_scans"],
            "delays": CLEANING_CONFIGS["showcase_delay_reports"],
            "transfers": CLEANING_CONFIGS["showcase_warehouse_transfers"],
        }
    return LADE_CLEANING_CONFIGS


def run_pipeline(
    dataset: str = "showcase",
    input: Optional[PathLike] = None,
    raw_dir: Optional[PathLike] = None,
    processed_dir: Optional[PathLike] = None,
    runs_dir: PathLike = DEFAULT_RUNS_DIR,
    output_path: Optional[PathLike] = None,
    seed: int = 42,
    n_shipments: int = 3000,
    ds_min: int = 605,
    ds_max: int = 618,
    skip_source_build: bool = False,
    alert_config: Optional[dict[str, Any]] = None,
    risk_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run the full pipeline and return the run manifest (also written to disk).

    Args:
        dataset: ``"showcase"`` (deterministic synthetic sources) or
            ``"lade"`` (real LaDe pickup file via the existing adapter).
        input: LaDe source CSV path (required for ``dataset="lade"``).
        raw_dir/processed_dir: working directories (defaults isolate each
            dataset under ``data/raw/<dataset>/`` and
            ``data/processed/<dataset>/``).
        runs_dir: manifest directory (default ``data/processed/runs/``).
        output_path: integrated CSV destination (defaults per dataset).
        seed/n_shipments: showcase generation parameters (documented in the
            manifest; the generator itself is untouched).
        ds_min/ds_max: LaDe showcase window passed to the adapter.
        skip_source_build: reuse existing raw CSVs in ``raw_dir`` instead
            of (re)building sources (role detection by filename).
        alert_config/risk_config: passthrough overrides for alerts and
            route-risk classification.

    Raises:
        ValueError: On an unknown dataset or a missing LaDe input.
        PipelineFailed: When the validation gate stops the run or a stage
            raises. The manifest is still written first.
    """
    if dataset not in ("showcase", "lade"):
        raise ValueError(f"Unknown dataset: {dataset!r} (expected 'showcase' or 'lade').")

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    started_at = _now_iso()
    stages: dict[str, StageRecord] = {name: StageRecord(name) for name in STAGE_ORDER}
    global_warnings: list[str] = []
    global_errors: list[str] = []

    resolved_raw = Path(raw_dir) if raw_dir is not None else Path("data/raw") / dataset
    resolved_processed = (
        Path(processed_dir) if processed_dir is not None else Path("data/processed") / dataset
    )
    resolved_runs = Path(runs_dir)
    resolved_runs.mkdir(parents=True, exist_ok=True)
    default_output = (
        SHOWCASE_INTEGRATED_FILENAME if dataset == "showcase" else LADE_INTEGRATED_FILENAME
    )
    resolved_output = Path(output_path) if output_path is not None else Path("data/processed") / default_output

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "dataset": dataset,
        "started_at": started_at,
        "finished_at": None,
        "overall_status": "PENDING",
        "params": {
            "seed": seed if dataset == "showcase" else None,
            "n_shipments": n_shipments if dataset == "showcase" else None,
            "ds_min": ds_min if dataset == "lade" else None,
            "ds_max": ds_max if dataset == "lade" else None,
            "skip_source_build": skip_source_build,
            "input": str(input) if input is not None else None,
            "raw_dir": str(resolved_raw),
            "processed_dir": str(resolved_processed),
            "output_path": str(resolved_output),
        },
        "stages": {},
        "inputs": {},
        "outputs": {},
        "validation_summary": {},
        "warnings": global_warnings,
        "errors": global_errors,
        "pipeline": {"runner": "pipeline/run_pipeline.py"},
    }

    def write_manifest(status: str) -> dict[str, Any]:
        manifest["finished_at"] = _now_iso()
        manifest["overall_status"] = status
        manifest["stages"] = {name: rec.to_dict() for name, rec in stages.items()}
        manifest["warnings"] = list(global_warnings)
        manifest["errors"] = list(global_errors)
        manifest_path = resolved_runs / f"run_{run_id}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest

    def fail(message: str, stage: StageRecord, exc: Optional[BaseException] = None) -> dict[str, Any]:
        label = f"{type(exc).__name__}: {exc}" if exc is not None else message
        stage.status = "FAILED"
        stage.errors.append(label)
        global_errors.append(f"{stage.stage}: {label}")
        manifest_out = write_manifest(FAILED)
        raise PipelineFailed(f"Pipeline FAILED at stage '{stage.stage}': {label}") from exc

    def skip_remaining(failed_stage: str) -> None:
        for name in STAGE_ORDER[STAGE_ORDER.index(failed_stage) + 1:]:
            rec = stages[name]
            rec.status = "SKIPPED"
            rec.started_at = _now_iso()
            rec.finished_at = rec.started_at
            rec.duration_seconds = 0.0

    print(f"Run {run_id} (dataset={dataset})")
    sources: dict[str, Path] = {}
    frames: dict[str, pd.DataFrame] = {}
    cleaned: dict[str, pd.DataFrame] = {}
    integrated: Optional[pd.DataFrame] = None

    # -- Ingestion (source build + load) -------------------------------------
    rec = stages["ingestion"]
    try:
        with _Timer(rec):
            if skip_source_build:
                sources = _discover_source_files(resolved_raw)
                if "scans" not in sources:
                    raise FileNotFoundError(
                        f"No scan source found in {resolved_raw} "
                        "(expected a *scan*.csv when skip_source_build is set)."
                    )
            elif dataset == "showcase":
                from pipeline.synthetic_showcase import build_showcase_sources

                gen = build_showcase_sources(seed=seed, n_shipments=n_shipments, raw_dir=resolved_raw)
                sources = {role: Path(gen["paths"][name]) for role, name in (
                    ("scans", "showcase_shipment_scans"),
                    ("delays", "showcase_delay_reports"),
                    ("transfers", "showcase_warehouse_transfers"),
                )}
                rec.detail["generation"] = {
                    k: gen[k] for k in ("seed", "n_shipments", "scan_rows", "delay_rows", "transfer_rows")
                }
            else:
                if input is None:
                    raise ValueError(
                        "LaDe input missing: download pickup/pickup_jl.csv from "
                        "Hugging Face 'Cainiao-AI/LaDe' and pass "
                        "--input path/to/pickup_jl.csv (nothing is fetched automatically)."
                    )
                from pipeline.lade_adapter import build_lade_sources

                summary = build_lade_sources(input, raw_dir=resolved_raw, ds_min=ds_min, ds_max=ds_max)
                sources = {
                    "scans": Path(summary["scans_path"]),
                    "delays": Path(summary["delays_path"]),
                }
                rec.detail["adapter"] = {
                    k: summary[k] for k in ("source_file", "subset_rows", "scans_rows", "delays_rows")
                    if k in summary
                }
                rec.detail["adapter"]["warehouse_transfers"] = summary.get("warehouse_transfers")
            for role, path in sources.items():
                frames[role] = load_dataset(path)
                meta = get_dataset_metadata(frames[role], path)
                manifest["inputs"][role] = {**meta, "path": str(path)}
            rec.detail["sources"] = {role: str(p) for role, p in sources.items()}
            rec.status = "SUCCESS"
    except Exception as exc:
        fail("ingestion failed", rec, exc)
    print("[1/9] Ingestion ........ SUCCESS")

    # -- Validation + gate ----------------------------------------------------
    rec = stages["validation"]
    validation_results: dict[str, dict[str, Any]] = {}
    try:
        with _Timer(rec):
            for role, frame in frames.items():
                result = validate_dataset(
                    frame, dataset_name=f"{dataset}_{role}", **VALIDATION_CONFIGS[role]
                )
                validation_results[role] = result
            proceed, errors, warnings = _apply_validation_gate(validation_results)
            rec.detail["per_source"] = {
                role: {
                    "status": r["status"],
                    "issues": [f"[{i['severity']}] {i['check']}: {i['message']}" for i in r["issues"]],
                }
                for role, r in validation_results.items()
            }
            rec.warnings.extend(warnings)
            global_warnings.extend(warnings)
            manifest["validation_summary"] = {
                role: {"status": r["status"], "issue_count": len(r["issues"])}
                for role, r in validation_results.items()
            }
            if not proceed:
                rec.status = "FAILED"
                rec.errors.extend(errors)
                global_errors.extend(errors)
                skip_remaining("validation")
                manifest_out = write_manifest(FAILED)
                print("[2/9] Validation ...... FAILED (gate stopped the pipeline)")
                print(f"Manifest: {manifest_out['manifest_path']}")
                raise PipelineFailed(
                    f"Validation gate stopped the run with {len(errors)} ERROR(s)."
                )
            rec.status = "WARNING" if warnings else "SUCCESS"
    except PipelineFailed:
        raise
    except Exception as exc:
        fail("validation failed", rec, exc)
    print(f"[2/9] Validation ...... {rec.status}")

    # -- Cleaning --------------------------------------------------------------
    rec = stages["cleaning"]
    try:
        with _Timer(rec):
            resolved_processed.mkdir(parents=True, exist_ok=True)
            configs = _cleaning_configs(dataset)
            for role, path in sources.items():
                frame, summary, saved = clean_file(
                    path,
                    output_path=resolved_processed / f"{path.stem}_cleaned.csv",
                    dataset_name=path.stem,
                    **configs[role],
                )
                cleaned[f"{path.stem}_cleaned"] = frame
                rec.detail[role] = {
                    "input_rows": summary["input_rows"],
                    "output_rows": summary["output_rows"],
                    "duplicates_removed": summary.get("duplicates_removed"),
                    "output_path": str(saved),
                }
            rec.status = "SUCCESS"
    except Exception as exc:
        fail("cleaning failed", rec, exc)
    print("[3/9] Cleaning ........ SUCCESS")

    # -- Integration ------------------------------------------------------------
    rec = stages["integration"]
    try:
        with _Timer(rec):
            integrated, report = build_integrated_dataset(
                cleaned, timestamp_pairs=[("timestamp", "reported_at")]
            )
            saved = save_integrated_dataset(integrated, resolved_output)
            manifest["outputs"]["integrated"] = {
                "path": str(saved),
                "rows": int(len(integrated)),
                "columns": int(len(integrated.columns)),
            }
            rec.detail = {
                "base": report["base_dataset"],
                "sources_used": report["sources_used"],
                "output_rows": report["row_count"],
                "output_columns": report["column_count"],
                "joins": [
                    {
                        "right": j["right"],
                        "relationship": j["relationship"],
                        "matched": j["matched"],
                        "output_rows": j["output_rows"],
                    }
                    for j in report["joins"]
                ],
                "skipped": report["skipped"],
                "temporal_violations": {
                    label: d.get("violations", 0)
                    for label, d in report["temporal_consistency"].get("pairs", {}).items()
                    if d.get("checked")
                },
                "output_path": str(saved),
            }
            for warning in report.get("unresolved", []):
                # Skip the standing scope note; only genuine run findings
                # (many-to-many output, zero-match joins) become warnings.
                if "out of scope" in str(warning):
                    continue
                rec.warnings.append(str(warning))
                global_warnings.append(f"integration: {warning}")
            rec.status = "WARNING" if rec.warnings else "SUCCESS"
    except Exception as exc:
        fail("integration failed", rec, exc)
    print(f"[4/9] Integration ..... {rec.status}")
    assert integrated is not None

    # -- Analytics ---------------------------------------------------------------
    rec = stages["analytics"]
    try:
        with _Timer(rec):
            bundle = compute_kpis(integrated)
            ship = bundle["shipment"]
            rec.detail["kpis"] = {
                "total_shipments": ship["total_shipments"],
                "delayed_shipments": ship["delayed_shipments"],
                "delay_rate": ship["delay_rate"],
                "average_delay": bundle["delay"].get("average_delay"),
            }
            try:
                routes = route_metrics(integrated)
                rec.detail["routes"] = {
                    "count": int(len(routes)),
                    "top_route": str(routes.iloc[0]["route"]) if not routes.empty else None,
                    "top_delay_rate": float(routes.iloc[0]["delay_rate"])
                    if not routes.empty and routes.iloc[0]["delay_rate"] is not None
                    else None,
                }
            except ValueError as exc:
                rec.warnings.append(f"routes unavailable: {exc}")
            try:
                warehouses = warehouse_metrics(integrated)
                rec.detail["warehouses"] = {"count": int(len(warehouses))}
            except ValueError as exc:
                rec.warnings.append(f"warehouses unavailable: {exc}")
            try:
                reasons = delay_reason_breakdown(integrated)
                rec.detail["delay_reasons"] = {"count": int(len(reasons))}
            except ValueError as exc:
                rec.warnings.append(f"delay reasons unavailable: {exc}")
            try:
                trend = delay_over_time(integrated, freq="D")
                rec.detail["trend_periods"] = int(len(trend))
            except ValueError as exc:
                rec.warnings.append(f"trend unavailable: {exc}")
            global_warnings.extend(f"analytics: {w}" for w in rec.warnings)
            rec.status = "WARNING" if rec.warnings else "SUCCESS"
    except Exception as exc:
        fail("analytics failed", rec, exc)
    print(f"[5/9] Analytics ....... {rec.status}")

    # -- SQL ----------------------------------------------------------------------
    rec = stages["sql"]
    try:
        with _Timer(rec):
            conn = get_connection()
            try:
                load_integrated_dataset(integrated, connection=conn)
                try:
                    rec.detail["views"] = apply_views(conn)
                except Exception as exc:
                    rec.warnings.append(f"views unavailable: {exc}")
                sql_text = Path("sql/metrics.sql").read_text(encoding="utf-8")
                sections = split_sql_sections(sql_text)
                sql_results: dict[str, pd.DataFrame] = {}
                for name, sql in sections.items():
                    try:
                        sql_results[name] = execute_query(
                            conn, sql.replace("{table}", f'"{DEFAULT_TABLE}"')
                        )
                    except Exception as exc:
                        rec.warnings.append(f"sql section '{name}' unrunnable: {exc}")
                comparisons: list[dict[str, Any]] = []
                if "shipment_kpis" in sql_results:
                    ship_sql = sql_results["shipment_kpis"].iloc[0]
                    ship_pd = compute_shipment_kpis(integrated)
                    for key in ("total_shipments", "delayed_shipments", "delay_rate"):
                        comparisons.append(
                            {"name": key, "sql": ship_sql[key], "pandas": ship_pd[key]}
                        )
                if "delay_kpis_record" in sql_results:
                    comparisons.append(
                        {
                            "name": "average_delay_record",
                            "sql": sql_results["delay_kpis_record"].iloc[0]["average_delay"],
                            "pandas": compute_delay_kpis(integrated)["average_delay"],
                        }
                    )
                # Stage-local availability checks keep SQL independent of the
                # analytics stage record while reusing the same functions.
                try:
                    routes_pd = route_metrics(integrated).set_index("route")
                except ValueError as exc:
                    routes_pd = None
                    rec.warnings.append(f"route SQL comparison skipped: {exc}")
                if routes_pd is not None and "route_delay_rates" in sql_results:
                    routes_sql = sql_results["route_delay_rates"].set_index("route")
                    for route in routes_pd.index:
                        if route in routes_sql.index:
                            comparisons.append(
                                {
                                    "name": f"route_{route}_delay_rate",
                                    "sql": routes_sql.loc[route, "delay_rate"],
                                    "pandas": routes_pd.loc[route, "delay_rate"],
                                }
                            )
                try:
                    wh_pd = warehouse_metrics(integrated).set_index("warehouse")
                except ValueError as exc:
                    wh_pd = None
                    rec.warnings.append(f"warehouse SQL comparison skipped: {exc}")
                if wh_pd is not None and "warehouse_delay_rates" in sql_results:
                    wh_sql = sql_results["warehouse_delay_rates"].set_index("warehouse")
                    for warehouse in wh_pd.index:
                        if warehouse in wh_sql.index:
                            comparisons.append(
                                {
                                    "name": f"warehouse_{warehouse}_delay_rate",
                                    "sql": wh_sql.loc[warehouse, "delay_rate"],
                                    "pandas": wh_pd.loc[warehouse, "delay_rate"],
                                }
                            )
                sql_report = validate_sql_vs_pandas(comparisons) if comparisons else None
                rec.detail["comparisons"] = len(comparisons)
                rec.detail["all_match"] = (
                    bool(sql_report["all_match"]) if sql_report else None
                )
                if sql_report and not sql_report["all_match"]:
                    mismatched = [c["name"] for c in sql_report["comparisons"] if not c["match"]]
                    rec.warnings.append(f"SQL/Pandas mismatches: {mismatched}")
                if not comparisons:
                    rec.warnings.append("no SQL/Pandas comparisons were runnable")
            finally:
                conn.close()
            global_warnings.extend(f"sql: {w}" for w in rec.warnings)
            rec.status = "WARNING" if rec.warnings else "SUCCESS"
    except Exception as exc:
        fail("sql failed", rec, exc)
    print(f"[6/9] SQL ............. {rec.status}")

    # -- Cascade --------------------------------------------------------------------
    rec = stages["cascade"]
    try:
        with _Timer(rec):
            candidates, info = detect_cascade_candidates(integrated)
            rec.detail = {
                "shipments_checked": info["shipments_checked"],
                "candidate_shipments": info["candidate_shipments"],
                "single_delay_not_candidates": info["single_delay_not_candidates"],
                "rule": info["rule"],
            }
            rec.status = "SUCCESS"
    except Exception as exc:
        fail("cascade failed", rec, exc)
    print(f"[7/9] Cascade ......... {rec.status}")

    # -- Route risk --------------------------------------------------------------------
    rec = stages["route_risk"]
    try:
        with _Timer(rec):
            risk, info = route_cascade_risk(integrated, risk_config=risk_config)
            top = risk.iloc[0] if not risk.empty else None
            rec.detail = {
                "routes": info["routes"],
                "top_route": str(top["route"]) if top is not None else None,
                "top_cascade_rate": float(top["cascade_rate"])
                if top is not None and top["cascade_rate"] is not None
                else None,
            }
            rec.status = "SUCCESS"
    except Exception as exc:
        fail("route_risk failed", rec, exc)
    print(f"[8/9] Route Risk ...... {rec.status}")

    # -- Alerts --------------------------------------------------------------------------
    rec = stages["alerts"]
    try:
        with _Timer(rec):
            alerts, report = generate_alerts(integrated, alert_config)
            summary = summarize_alerts(alerts)
            rec.detail = {
                "total_alerts": summary["total_alerts"],
                "by_severity": summary["by_severity"],
                "by_type": summary["by_type"],
                "unavailable": report["unavailable"],
            }
            for name in report["unavailable"]:
                rec.warnings.append(f"alert check unavailable: {name}")
            global_warnings.extend(f"alerts: {w}" for w in rec.warnings)
            rec.status = "WARNING" if rec.warnings else "SUCCESS"
    except Exception as exc:
        fail("alerts failed", rec, exc)
    print(f"[9/9] Alerts .......... {rec.status}")

    overall = SUCCESS_WITH_WARNINGS if global_warnings else SUCCESS
    manifest_out = write_manifest(overall)
    print(
        "Pipeline completed successfully with warnings."
        if overall == SUCCESS_WITH_WARNINGS
        else "Pipeline completed successfully."
    )
    print(f"Manifest: {manifest_out['manifest_path']}")
    return manifest_out


def build_parser() -> argparse.ArgumentParser:
    """CLI definition (help text doubles as usage documentation)."""
    parser = argparse.ArgumentParser(
        prog="pipeline.run_pipeline",
        description=(
            "Run the Cascading Delay Intelligence pipeline end to end: "
            "source build, ingestion, validation (gated), cleaning, "
            "integration, analytics, SQL cross-check, cascade analysis, "
            "route-risk analysis, alerts, and a machine-readable run manifest."
        ),
    )
    parser.add_argument(
        "--dataset",
        choices=["showcase", "lade"],
        default="showcase",
        help="Which dataset to run (default: showcase).",
    )
    parser.add_argument(
        "--input",
        default=None,
        help=(
            "LaDe source CSV (pickup file) for --dataset lade. Nothing is "
            "downloaded automatically; pass the local path explicitly."
        ),
    )
    parser.add_argument("--raw-dir", default=None, help="Raw working directory.")
    parser.add_argument("--processed-dir", default=None, help="Cleaned working directory.")
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR), help="Manifest directory.")
    parser.add_argument("--output", default=None, help="Integrated CSV destination.")
    parser.add_argument("--seed", type=int, default=42, help="Showcase generator seed.")
    parser.add_argument("--n-shipments", type=int, default=3000, help="Showcase shipment count.")
    parser.add_argument("--ds-min", type=int, default=605, help="LaDe window start (MMDD).")
    parser.add_argument("--ds-max", type=int, default=618, help="LaDe window end (MMDD).")
    parser.add_argument(
        "--skip-source-build",
        action="store_true",
        help="Reuse existing raw CSVs in --raw-dir instead of (re)building sources.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point: 0 on success (warnings included), 1 on failure."""
    args = build_parser().parse_args(argv)
    try:
        run_pipeline(
            dataset=args.dataset,
            input=args.input,
            raw_dir=args.raw_dir,
            processed_dir=args.processed_dir,
            runs_dir=args.runs_dir,
            output_path=args.output,
            seed=args.seed,
            n_shipments=args.n_shipments,
            ds_min=args.ds_min,
            ds_max=args.ds_max,
            skip_source_build=args.skip_source_build,
        )
    except PipelineFailed as exc:
        print(str(exc))
        return 1
    except (ValueError, FileNotFoundError) as exc:
        print(f"Pipeline setup error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
