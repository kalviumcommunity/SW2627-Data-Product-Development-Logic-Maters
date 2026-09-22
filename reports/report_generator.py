"""Stakeholder reporting layer (presentation/consumption only).

Converts the outputs of an actual ``pipeline/run_pipeline.py`` run into a
readable Markdown or HTML operational report. This module contains no
analytics of its own: every number comes from the run manifest (run
context, timings, validation, row counts) or from reusing the existing
analysis functions over the run's integrated CSV
(``compute_kpis``, ``route_metrics``, ``detect_cascade_candidates``,
``route_cascade_risk``, ``generate_alerts``, …). Recomputation is
deterministic for an unchanged integrated file (alert timestamps are
pinned to the run's start time), so identical inputs always yield
identical reports.

Conventions:

* unavailable dimensions render as "Not available for this dataset" —
  never fabricated, never crashing;
* synthetic results are always badged synthetic, never presented as
  observed operations;
* empirical probabilities are described as historical observations, never
  as ML predictions; language stays associational ("observed",
  "recorded", "associated"), never causal.

CLI::

    python -m reports.report_generator --run data/processed/runs/run_<id>.json --format markdown
    python -m reports.report_generator --run data/processed/runs/run_<id>.json --format html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.alerts import generate_alerts, summarize_alerts
from analysis.cascade_analysis import (
    cascade_by_route,
    cascade_by_warehouse,
    cascade_summary_metrics,
    detect_cascade_candidates,
    root_cause_signals,
)
from analysis.delay_analysis import delay_over_time, delay_reason_breakdown
from analysis.eda import get_delay_distribution
from analysis.kpis import compute_kpis
from analysis.route_analysis import route_metrics
from analysis.route_risk import route_cascade_risk
from analysis.warehouse_analysis import transfer_activity, warehouse_metrics

PathLike = Union[str, Path]

DEFAULT_RUNS_DIR = Path("data/processed/runs")
NOT_AVAILABLE = "Not available for this dataset"

DISCLAIMER_ML = (
    "Risk figures in this report are historical empirical indicators "
    "(observed frequencies). They are not an ML prediction and carry no "
    "validated future accuracy."
)
DISCLAIMER_CAUSAL = (
    "All patterns below describe observed associations in recorded data. "
    "Observational data does not establish causation."
)


def _fmt(value: Any, digits: int = 1) -> str:
    """Human number or 'N/A' (None/NaN-safe)."""
    if value is None:
        return "N/A"
    try:
        if pd.isna(value):
            return "N/A"
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _pct(value: Any) -> str:
    return "N/A" if value is None else f"{_fmt(value)}%"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return "\n".join(lines)


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    cells = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table>"


def load_manifest(path: PathLike) -> dict[str, Any]:
    """Read a run manifest (clear error when it is missing or corrupt)."""
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Run manifest not found: {resolved}. Run "
            "`python -m pipeline.run_pipeline --dataset showcase` first."
        )
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Run manifest is not valid JSON: {resolved} ({exc}).") from exc


def resolve_integrated_frame(manifest: dict[str, Any]) -> pd.DataFrame:
    """Load exactly the integrated CSV the manifest points at (no substitutes)."""
    raw_path = ((manifest.get("outputs") or {}).get("integrated") or {}).get("path")
    if not raw_path:
        raise ValueError(
            "Manifest has no integrated output recorded; the pipeline run "
            "did not reach integration. Re-run the pipeline."
        )
    resolved = Path(raw_path)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Integrated dataset from run '{manifest.get('run_id')}' is missing: "
            f"{resolved}. Re-run the pipeline instead of substituting another file."
        )
    return pd.read_csv(resolved)


def source_label(dataset: Any) -> tuple[str, str]:
    """(short label, stakeholder description) for a manifest dataset name."""
    name = str(dataset or "unknown")
    if name == "showcase":
        return (
            "Synthetic showcase (deterministic, seed-recorded)",
            "This data is SYNTHETIC: generated to exercise the full product "
            "surface. Shapes are realistic; behaviour was not observed in "
            "production and must not be presented as real operations.",
        )
    if name == "lade":
        return (
            "LaDe real-world pickup data (Jilin showcase window)",
            "Real industry pickup records (LaDe). Coverage is partial by "
            "source design: no warehouses, transfers, or delay reasons exist, "
            "so those sections are honestly unavailable below.",
        )
    return (f"Dataset '{name}'", "Custom dataset supplied to the pipeline runner.")


def _stage_rows(manifest: dict[str, Any]) -> list[list[str]]:
    rows = []
    for name, stage in (manifest.get("stages") or {}).items():
        rows.append([
            str(name),
            str(stage.get("status", "UNKNOWN")),
            _fmt(stage.get("duration_seconds", None), digits=2).replace(",", "") + "s"
            if stage.get("duration_seconds") is not None else "N/A",
            "; ".join(str(w) for w in stage.get("warnings", [])) or "—",
        ])
    return rows


def build_report(manifest_path: PathLike) -> dict[str, Any]:
    """Assemble every report section from manifest + integrated data.

    Returns a JSON-friendly dict; rendering (Markdown/HTML/Streamlit) is
    separate. Deterministic: alert timestamps reuse the run start time.
    """
    manifest = load_manifest(manifest_path)
    frame = resolve_integrated_frame(manifest)
    dataset = manifest.get("dataset", "unknown")
    label, description = source_label(dataset)
    detected_at = manifest.get("started_at")

    bundle = compute_kpis(frame)
    ship = bundle["shipment"]
    delay = bundle["delay"] if isinstance(bundle.get("delay"), dict) else {}

    try:
        routes = route_metrics(frame)
    except ValueError:
        routes = pd.DataFrame()
    try:
        risk, _ = route_cascade_risk(frame)
    except ValueError:
        risk = pd.DataFrame()
    try:
        candidates, _ = detect_cascade_candidates(frame)
        total_shipments = ship.get("total_shipments")
        cascade_summary = cascade_summary_metrics(candidates, total_shipments=total_shipments)
        by_route = cascade_by_route(candidates)
        by_warehouse = cascade_by_warehouse(candidates)
        signals = root_cause_signals(candidates)
    except ValueError:
        candidates, cascade_summary = pd.DataFrame(), {"candidate_count": 0}
        by_route = by_warehouse = signals = pd.DataFrame()
    try:
        warehouses = warehouse_metrics(frame)
        transfers = transfer_activity(frame)
    except ValueError:
        warehouses, transfers = pd.DataFrame(), {}
    try:
        reasons = delay_reason_breakdown(frame)
        reasons = reasons[reasons["delay_reason"].astype(str).str.lower() != "unknown"]
    except ValueError:
        reasons = pd.DataFrame()
    try:
        distribution = get_delay_distribution(frame)
    except ValueError:
        distribution = {"available": False}
    try:
        trend = delay_over_time(frame, freq="D")
    except ValueError:
        trend = pd.DataFrame()
    alerts, alert_report = generate_alerts(frame, detected_at=detected_at)
    alert_summary = summarize_alerts(alerts)

    stages = manifest.get("stages") or {}
    total_duration = sum(
        float(s.get("duration_seconds") or 0.0) for s in stages.values()
    )

    report: dict[str, Any] = {
        "run_id": manifest.get("run_id"),
        "dataset": dataset,
        "source_label": label,
        "source_description": description,
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
        "overall_status": manifest.get("overall_status"),
        "total_duration_seconds": round(total_duration, 2),
        "integrated_path": ((manifest.get("outputs") or {}).get("integrated") or {}).get("path"),
        "integrated_rows": ((manifest.get("outputs") or {}).get("integrated") or {}).get("rows"),
        "params": manifest.get("params", {}),
        "stage_rows": _stage_rows(manifest),
        "warnings": list(manifest.get("warnings", [])),
        "errors": list(manifest.get("errors", [])),
        "validation_summary": manifest.get("validation_summary", {}),
        "kpis": {
            "total_shipments": ship.get("total_shipments"),
            "delayed_shipments": ship.get("delayed_shipments"),
            "delay_rate": ship.get("delay_rate"),
            "on_time_rate": ship.get("on_time_rate"),
            "average_delay": delay.get("average_delay"),
            "median_delay": delay.get("median_delay"),
            "max_delay": delay.get("max_delay"),
            "total_delay": delay.get("total_delay"),
            "delayed_records": delay.get("delayed_records"),
        },
        "routes_table": routes.to_dict(orient="records") if not routes.empty else [],
        "risk_table": risk.to_dict(orient="records") if not risk.empty else [],
        "cascade": {
            "candidate_count": int(cascade_summary.get("candidate_count", 0) or 0),
            "candidate_rate": cascade_summary.get("candidate_rate"),
            "avg_depth": cascade_summary.get("avg_cascade_depth"),
            "max_depth": cascade_summary.get("max_cascade_depth"),
            "depth_distribution": cascade_summary.get("depth_distribution", {}),
            "by_route": by_route.to_dict(orient="records") if not by_route.empty else [],
            "by_warehouse": by_warehouse.to_dict(orient="records") if not by_warehouse.empty else [],
            "signals": signals.to_dict(orient="records") if not signals.empty else [],
            "examples": (
                candidates.head(5).to_dict(orient="records") if not candidates.empty else []
            ),
        },
        "warehouses_table": warehouses.to_dict(orient="records") if not warehouses.empty else [],
        "transfers": {
            endpoint: {
                "available": bool(info.get("available")),
                "top": [
                    {"warehouse": str(r["warehouse"]), "transfers": int(r["transfers"])}
                    for _, r in info.get("activity", pd.DataFrame()).head(6).iterrows()
                ],
            }
            for endpoint, info in (transfers or {}).items()
            if isinstance(info, dict)
        },
        "reasons_table": reasons.to_dict(orient="records") if not reasons.empty else [],
        "distribution": {
            "available": bool(distribution.get("available")),
            "delayed_records": distribution.get("delayed_records"),
            "stats": distribution.get("stats", {}),
        },
        "trend": {
            "periods": int(len(trend)),
            "first_period": str(trend["period"].iloc[0]) if len(trend) else None,
            "last_period": str(trend["period"].iloc[-1]) if len(trend) else None,
        },
        "alerts": {
            "total": int(alert_summary.get("total_alerts", 0)),
            "by_severity": alert_summary.get("by_severity", {}),
            "by_type": alert_summary.get("by_type", {}),
            "affected_routes": alert_summary.get("affected_routes", []),
            "affected_warehouses": alert_summary.get("affected_warehouses", []),
            "rows": alerts.to_dict(orient="records") if not alerts.empty else [],
            "thresholds": {
                k: v for k, v in (alert_report.get("config") or {}).items()
                if k in (
                    "delay_rate_threshold", "critical_delay_rate",
                    "delay_duration_threshold", "critical_delay_duration",
                    "critical_cascade_depth",
                )
            },
        },
    }
    report["interpretation"] = _interpretation(report)
    report["investigations"] = _investigations(report)
    return report


def _interpretation(report: dict[str, Any]) -> list[str]:
    """Factual reading of the risk table (no scores, no best/worst labels)."""
    notes: list[str] = []
    rows = report["risk_table"]
    if not rows:
        return ["No routes with observed delays; no route-risk interpretation is possible."]
    recurring = [r for r in rows if (r.get("cascade_recurrence") or 0) == 1.0 and (r.get("observed_periods") or 0) > 1]
    if recurring:
        names = ", ".join(str(r["route"]) for r in recurring)
        notes.append(
            f"Routes with cascades in every observed delay period (recurring "
            f"historical behaviour): {names}."
        )
    rated = [r for r in rows if r.get("cascade_probability") is not None]
    if rated:
        top = max(rated, key=lambda r: float(r["cascade_probability"]))
        notes.append(
            f"Highest observed historical conditional probability: route "
            f"{top['route']} at {_fmt(top['cascade_probability'], digits=3)} "
            f"({_fmt(top['cascade_shipments'])} cascades of "
            f"{_fmt(top['delayed_shipments'])} initial delays)."
        )
    volatile = [r for r in rows if (r.get("cascade_rate_cv") or 0) > 1.0]
    if volatile:
        notes.append(
            "High period-to-period volatility (CV above 1.0): "
            + ", ".join(str(r["route"]) for r in volatile)
            + " — cascade behaviour there is bursty rather than steady."
        )
    thin = [r for r in rows if r.get("risk_class") == "INSUFFICIENT_DATA"]
    if thin:
        notes.append(
            f"{len(thin)} route(s) have too few delayed shipments for a stable "
            f"rate; treat their figures as indicative only: "
            + ", ".join(str(r["route"]) for r in thin[:8])
            + (", …" if len(thin) > 8 else ".")
        )
    if not notes:
        notes.append("No route shows repeated historical cascade behaviour in this run.")
    return notes


def _investigations(report: dict[str, Any]) -> list[str]:
    """Evidence-based follow-ups; 'investigate', never 'fix'."""
    items: list[str] = []
    for row in report["risk_table"]:
        if (row.get("cascade_recurrence") or 0) == 1.0 and (row.get("observed_periods") or 0) > 1:
            items.append(
                f"Investigate route {row['route']}: cascades were observed in "
                f"every delay period ({_fmt(row['cascade_shipments'])} cascade "
                f"shipments, historical rate {_pct(row['cascade_rate'])})."
            )
    for row in (report["cascade"]["by_warehouse"] or [])[:3]:
        items.append(
            f"Inspect warehouse {row.get('warehouse')}: "
            f"{_fmt(row.get('candidates'))} cascade candidate(s) recorded "
            f"alongside it (association for investigation, not proof of cause)."
        )
    if report["warnings"]:
        items.append(
            "Review the data-quality warnings in §3 before relying on "
            "metrics from the affected sources."
        )
    if not report["cascade"]["candidate_count"]:
        items.append(
            "No cascade candidates were observed; delay handling can focus on "
            "isolated delays rather than propagation."
        )
    if not items:
        items.append("No specific investigation areas stand out in this run.")
    return items


def _limitations(report: dict[str, Any]) -> list[str]:
    items = [
        "Observational data does not establish causation; cascade sequences "
        "are associated delays in time order, not proven cause and effect.",
        DISCLAIMER_ML,
    ]
    if report["dataset"] == "showcase":
        items.append(
            "Synthetic showcase data: realistic shapes for exercising the "
            "product, not observed operations. Do not present these figures "
            "as real business performance."
        )
    if report["dataset"] == "lade":
        items.append(
            "LaDe source limitation: no warehouse, transfer, or delay-reason "
            "fields exist, so those sections are unavailable rather than zero."
        )
    if not report["warehouses_table"]:
        items.append("Warehouse-level analysis is unavailable for this dataset.")
    if not report["reasons_table"]:
        items.append("Delay reasons are not available in this dataset.")
    small = [r for r in report["risk_table"] if r.get("risk_class") == "INSUFFICIENT_DATA"]
    if small:
        items.append(
            f"Small-sample caution: {len(small)} route(s) fall below the "
            "minimum-observation guard; their rates are unstable."
        )
    return items


def render_markdown(report: dict[str, Any]) -> str:
    """Render the full stakeholder report as Markdown (deterministic)."""
    k = report["kpis"]
    c = report["cascade"]
    a = report["alerts"]
    lines = [
        "# Cascading Delay Intelligence Report",
        "",
        f"Run `{report['run_id']}` · dataset `{report['dataset']}` · status `{report['overall_status']}`",
        f"> Source: **{report['source_label']}** — {report['source_description']}",
        "",
        "## 1. Executive Summary",
        "",
        f"- Shipments processed: **{_fmt(k['total_shipments'])}**; delayed: **{_fmt(k['delayed_shipments'])}** (delay rate **{_pct(k['delay_rate'])}**).",
        f"- Cascade candidates: **{_fmt(c['candidate_count'])}**" + (
            f" (candidate rate {_pct(c['candidate_rate'])}, average depth {_fmt(c['avg_depth'])}, max depth {_fmt(c['max_depth'])})."
            if c["candidate_count"] else " — none observed in this run."),
        f"- Alerts triggered: **{_fmt(a['total'])}** " + (
            "(" + ", ".join(f"{n} {s.lower()}" for s, n in sorted(a["by_severity"].items())) + ")."
            if a["by_severity"] else "(none)."),
        f"- Validation: {report['validation_summary'] and ', '.join(f'{s}: {v.get('status')}' for s, v in sorted(report['validation_summary'].items())) or 'not recorded'}; pipeline warnings: {len(report['warnings'])}.",
    ]
    top_risk = [r for r in report["risk_table"] if r.get("cascade_probability") is not None]
    if top_risk:
        top = max(top_risk, key=lambda r: float(r["cascade_probability"]))
        lines.append(
            f"- Strongest route-risk signal: route {top['route']} recorded a higher "
            f"historical cascade rate ({_pct(top['cascade_rate'])}) than other observed routes."
        )
    lines += [
        "",
        "## 2. Run & Dataset Information",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Dataset: `{report['dataset']}` ({report['source_label']})",
        f"- Executed: {report['started_at']} → {report['finished_at']}",
        f"- Overall status: `{report['overall_status']}`; processing time: {_fmt(report['total_duration_seconds'], digits=2)}s",
        f"- Integrated output: `{report['integrated_path']}` ({_fmt(report['integrated_rows'])} rows)",
        f"- Parameters: {json.dumps(report['params'], default=str)}",
        "",
        _md_table(
            ["Stage", "Status", "Duration", "Warnings"],
            report["stage_rows"],
        ),
    ]
    if report["errors"]:
        lines += ["", "Run errors:", ""]
        lines += [f"- {e}" for e in report["errors"]]
    lines += [
        "",
        "## 3. Data Quality",
        "",
    ]
    if report["validation_summary"]:
        lines.append(_md_table(
            ["Source", "Status", "Issues"],
            [[s, str(v.get("status")), _fmt(v.get("issue_count"))] for s, v in sorted(report["validation_summary"].items())],
        ))
        lines.append("")
    if report["warnings"]:
        lines.append("Warnings (shown, not hidden):")
        lines.append("")
        lines += [f"- {w}" for w in report["warnings"]]
    else:
        lines.append("No quality problems were recorded for this run.")
    lines += [
        "",
        "## 4. Operational KPIs",
        "",
        _md_table(
            ["Metric", "Value"],
            [
                ["Total shipments", _fmt(k["total_shipments"])],
                ["Delayed shipments", _fmt(k["delayed_shipments"])],
                ["Delay rate", _pct(k["delay_rate"])],
                ["On-time rate", _pct(k["on_time_rate"])],
                ["Delayed records", _fmt(k["delayed_records"])],
                ["Average delay (min)", _fmt(k["average_delay"])],
                ["Median delay (min)", _fmt(k["median_delay"])],
                ["Max delay (min)", _fmt(k["max_delay"])],
                ["Total delay (min)", _fmt(k["total_delay"])],
            ],
        ),
        "",
        "## 5. Delay Analysis",
        "",
    ]
    dist = report["distribution"]
    if dist.get("available"):
        stats = dist.get("stats", {})
        lines.append(
            f"Delayed records: {_fmt(dist.get('delayed_records'))}; mean {_fmt(stats.get('mean'))} min, "
            f"median {_fmt(stats.get('median'))} min, max {_fmt(stats.get('max'))} min."
        )
        lines.append("")
    else:
        lines += ["Delay distribution is not available for this dataset.", ""]
    if report["reasons_table"]:
        lines.append(_md_table(
            ["Delay reason", "Records", "Share", "Avg delay (min)"],
            [[str(r.get("delay_reason")), _fmt(r.get("records")),
              _pct(r.get("pct_of_records")), _fmt(r.get("avg_delay"))]
             for r in report["reasons_table"]],
        ))
        lines.append("")
    else:
        lines += ["Delay reasons are not available in this dataset.", ""]
    if report["trend"]["periods"]:
        lines.append(
            f"Delay trend spans {report['trend']['periods']} daily periods "
            f"({report['trend']['first_period']} → {report['trend']['last_period']})."
        )
        lines.append("")
    lines += ["## 6. Route Intelligence", ""]
    if report["risk_table"]:
        lines.append(_md_table(
            ["Route", "Class", "Cascade rate", "P(downstream|initial)", "Recurrence",
             "Avg depth", "Max depth", "Delayed", "Cascades", "Periods"],
            [[str(r.get("route")), str(r.get("risk_class")), _pct(r.get("cascade_rate")),
              _fmt(r.get("cascade_probability"), digits=3), _fmt(r.get("cascade_recurrence"), digits=2),
              _fmt(r.get("average_cascade_depth")), _fmt(r.get("max_cascade_depth")),
              _fmt(r.get("delayed_shipments")), _fmt(r.get("cascade_shipments")),
              _fmt(r.get("observed_periods"))]
             for r in report["risk_table"]],
        ))
        lines += ["", "Historical conditional probability = cascades ÷ initial delays (observed frequency, not a prediction).", ""]
    else:
        lines += ["No routes with observed delays in this run.", ""]
    lines += ["## 7. Cascade Intelligence", ""]
    if c["candidate_count"]:
        lines.append(
            f"A cascade is an observed sequence: an initial delay followed by later "
            f"downstream delay(s) in one shipment's journey. Observed: "
            f"{_fmt(c['candidate_count'])} candidates "
            f"(rate {_pct(c['candidate_rate'])}), average depth {_fmt(c['avg_depth'])}, "
            f"max depth {_fmt(c['max_depth'])}; depth mix "
            + ", ".join(f"depth {d}: {n}" for d, n in sorted(c["depth_distribution"].items()))
            + "."
        )
        lines.append("")
        if c["by_route"]:
            lines.append(_md_table(
                ["Route", "Candidates", "Avg depth", "Avg downstream delay"],
                [[str(r.get("route")), _fmt(r.get("candidates")),
                  _fmt(r.get("avg_cascade_depth")), _fmt(r.get("avg_downstream_delay"))]
                 for r in c["by_route"]],
            ))
            lines.append("")
        if c["signals"]:
            lines.append("Commonly observed stage signals: " + ", ".join(
                f"{s.get('signal')} ({_fmt(s.get('share_pct'))}%)" for s in c["signals"]) + ".")
            lines.append("")
        if c["examples"]:
            ex = c["examples"][0]
            lines.append(
                f"Representative example: shipment {ex.get('shipment_id')} — stages "
                f"{' → '.join(str(s) for s in (ex.get('stages') or []))}, initial "
                f"{_fmt(ex.get('initial_delay_duration'))} min, downstream "
                f"{_fmt(ex.get('downstream_delay_duration'))} min."
            )
            lines.append("")
    else:
        lines += ["No cascade candidates were observed in this run.", ""]
    lines += ["## 8. Warehouse / Operational Point Analysis", ""]
    if report["warehouses_table"]:
        lines.append(_md_table(
            ["Warehouse", "Shipments", "Delayed", "Delay rate", "Avg delay"],
            [[str(r.get("warehouse")), _fmt(r.get("shipments")), _fmt(r.get("delayed_shipments")),
              _pct(r.get("delay_rate")), _fmt(r.get("avg_delay"))]
             for r in report["warehouses_table"]],
        ))
        lines.append("")
        for endpoint, info in sorted(report["transfers"].items()):
            if info.get("available") and info.get("top"):
                lines.append("Transfer " + str(endpoint).replace("_", " ") + ": " + ", ".join(
                    f"{t['warehouse']} ({_fmt(t['transfers'])} legs)" for t in info["top"]) + ".")
        lines.append("")
    else:
        lines += ["Warehouse-level analysis is unavailable for this dataset.", ""]
    lines += ["## 9. Alerts", ""]
    if a["total"]:
        lines.append(
            f"Total alerts: **{_fmt(a['total'])}** — " + ", ".join(
                f"{n} {s.lower()}" for s, n in sorted(a["by_severity"].items())) + ". "
            f"Affected routes: {', '.join(str(r) for r in a['affected_routes']) or 'none'}; "
            f"affected warehouses: {', '.join(str(w) for w in a['affected_warehouses']) or 'none'}."
        )
        lines.append("")
        lines.append(_md_table(
            ["Alert", "Type", "Severity", "Entity", "Metric", "Observed", "Threshold"],
            [[str(r.get("alert_id")), str(r.get("alert_type")), str(r.get("severity")),
              f"{r.get('entity_type')}:{r.get('entity_id')}", str(r.get("metric")),
              _fmt(r.get("metric_value")), _fmt(r.get("threshold"))]
             for r in a["rows"][:50]],
        ))
        if len(a["rows"]) > 50:
            lines.append("")
            lines.append(f"Showing 50 of {_fmt(len(a['rows']))} alerts; the remainder follow the same evidence pattern.")
        lines.append("")
        lines.append("Configured thresholds: " + ", ".join(
            f"{k}={v}" for k, v in sorted(a["thresholds"].items())) + ".")
        lines.append("")
    else:
        lines += ["No alerts were triggered in this run.", ""]
    lines += ["## 10. Route Risk Interpretation", ""]
    lines += [f"- {n}" for n in report["interpretation"]]
    lines += ["", "## 11. Recommended Investigation Areas", ""]
    lines += [f"- {n}" for n in report["investigations"]]
    lines += ["", "## 12. Limitations", ""]
    lines += [f"- {n}" for n in _limitations(report)]
    lines.append("")
    return "\n".join(lines) + "\n"


_CSS = (
    "body{font-family:sans-serif;max-width:960px;margin:2em auto;padding:0 1em;color:#222}"
    "table{border-collapse:collapse;margin:1em 0;min-width:60%}"
    "th,td{border:1px solid #999;padding:4px 10px;text-align:left;font-size:14px}"
    "th{background:#eee}blockquote{border-left:4px solid #999;padding-left:1em;color:#444}"
    "code{background:#f4f4f4;padding:1px 4px}"
)


def render_html(report: dict[str, Any]) -> str:
    """Render the report as standalone HTML (stdlib only, deterministic)."""
    md = render_markdown(report)
    out: list[str] = []
    in_table = False
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("| "):
            cells = [html.escape(c.strip()) for c in stripped.strip("|").split("|")]
            if set(cells) == {""} or all(set(c) <= {"-", " "} for c in cells):
                if not in_table:
                    out.append("<table>")
                    in_table = True
                continue
            if not in_table:
                out.append("<table><thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        else:
            if in_table:
                out.append("</tbody></table>")
                in_table = False
            if stripped.startswith("# "):
                out.append(f"<h1>{html.escape(stripped[2:])}</h1>")
            elif stripped.startswith("## "):
                out.append(f"<h2>{html.escape(stripped[3:])}</h2>")
            elif stripped.startswith("> "):
                out.append(f"<blockquote>{html.escape(stripped[2:])}</blockquote>")
            elif stripped.startswith("- "):
                out.append(f"<ul><li>{html.escape(stripped[2:])}</li></ul>")
            elif stripped == "":
                out.append("")
            else:
                out.append(f"<p>{html.escape(stripped)}</p>")
    if in_table:
        out.append("</tbody></table>")
    body = "\n".join(out)
    title = html.escape(f"Cascading Delay Intelligence Report — {report['run_id']}")
    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">\n"
        f"<title>{title}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        f"{body}\n</body></html>\n"
    )


def discover_runs(runs_dir: PathLike = DEFAULT_RUNS_DIR) -> list[dict[str, Any]]:
    """List available run manifests, newest first (read-only)."""
    directory = Path(runs_dir)
    if not directory.is_dir():
        return []
    runs = []
    for path in sorted(directory.glob("run_*.json"), key=lambda p: p.name, reverse=True):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        runs.append({
            "run_id": manifest.get("run_id", path.stem),
            "dataset": manifest.get("dataset", "unknown"),
            "overall_status": manifest.get("overall_status", "UNKNOWN"),
            "finished_at": manifest.get("finished_at"),
            "path": str(path),
        })
    return runs


def generate_report(
    manifest_path: PathLike,
    format: str = "markdown",
    output_path: Optional[PathLike] = None,
) -> Path:
    """Build a report file from a run manifest (deterministic).

    Default destination: ``<manifest_dir>/report_<run_id>.md|.html`` —
    flat beside the manifest, matching the existing runs layout.
    """
    if format not in ("markdown", "html"):
        raise ValueError(f"Unsupported format: {format!r} (expected 'markdown' or 'html').")
    manifest = load_manifest(manifest_path)
    report = build_report(manifest_path)
    text = render_markdown(report) if format == "markdown" else render_html(report)
    suffix = ".md" if format == "markdown" else ".html"
    destination = (
        Path(output_path)
        if output_path is not None
        else Path(manifest_path).parent / f"report_{manifest.get('run_id')}{suffix}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


def build_parser() -> argparse.ArgumentParser:
    """CLI definition (help text doubles as usage documentation)."""
    parser = argparse.ArgumentParser(
        prog="reports.report_generator",
        description=(
            "Generate a stakeholder Markdown/HTML report from a pipeline run "
            "manifest. All figures reuse existing analytics over the run's "
            "own integrated output; nothing is fabricated."
        ),
    )
    parser.add_argument(
        "--run", required=True,
        help="Path to the run manifest JSON (data/processed/runs/run_<id>.json).",
    )
    parser.add_argument(
        "--format", choices=["markdown", "html"], default="markdown",
        help="Report format (default: markdown).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Destination file (default: report_<run_id>.md|.html beside the manifest).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point: 0 on success, 1 with a clear message on failure."""
    args = build_parser().parse_args(argv)
    try:
        destination = generate_report(args.run, format=args.format, output_path=args.output)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Report generation failed: {exc}")
        return 1
    print(f"Report written: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
