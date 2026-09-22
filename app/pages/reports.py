"""Reports page: stakeholder reports from pipeline runs (no analytics here).

Lists available run manifests, shows run metadata plus the key report
sections, and offers the generated Markdown/HTML as downloads. All
figures come from :mod:`reports.report_generator`, which reuses the
existing analytics over each run's own integrated output.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from reports.report_generator import (
    build_report,
    discover_runs,
    load_manifest,
    prefer_reportable_run,
    render_html,
    render_markdown,
)


@st.cache_data(show_spinner=False)
def _cached_report(manifest_path: str) -> dict:
    """Assembled report sections for one run (cached per manifest path)."""
    return build_report(manifest_path)


def render(filtered: pd.DataFrame, full: pd.DataFrame) -> None:
    st.header("Operational reports")
    st.caption(
        "Stakeholder reports generated from recorded pipeline runs. "
        "Figures reuse the existing analytics over each run's own output."
    )
    runs = discover_runs()
    if not runs:
        st.info(
            "No pipeline runs recorded yet. Run "
            "`python -m pipeline.run_pipeline --dataset showcase` first."
        )
        return
    labels = [
        f"{r['run_id']} · {r['dataset']} · {r['overall_status']}"
        + ("" if r.get("has_integrated") else " (no reportable output)")
        for r in runs
    ]
    choice = st.selectbox(
        "Pipeline run", labels, index=prefer_reportable_run(runs)
    )
    manifest_path = next(r["path"] for r, label in zip(runs, labels) if label == choice)
    selected = next(r for r in runs if r["path"] == manifest_path)
    if not selected.get("has_integrated"):
        st.info(
            "This run did not reach integration, so there is no output to "
            "report on. Pick a run without the “no reportable output” tag — "
            "or re-run the pipeline successfully first."
        )
        _render_run_failure(manifest_path)
        return
    try:
        report = _cached_report(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Report unavailable: {exc}")
        return

    st.markdown(
        f"> Source: **{report['source_label']}** — {report['source_description']}"
    )
    cols = st.columns(4)
    cols[0].metric("Shipments", f"{report['kpis']['total_shipments']:,}" if report["kpis"]["total_shipments"] is not None else "n/a")
    rate = report["kpis"]["delay_rate"]
    cols[1].metric("Delay rate", f"{rate:.1f}%" if rate is not None else "n/a")
    cols[2].metric("Cascade candidates", f"{report['cascade']['candidate_count']:,}")
    cols[3].metric("Alerts", f"{report['alerts']['total']:,}")

    st.subheader("Run & data quality")
    st.dataframe(
        pd.DataFrame(report["stage_rows"], columns=["Stage", "Status", "Duration", "Warnings"]),
        width="stretch",
    )
    if report["warnings"]:
        st.warning("Warnings recorded for this run:")
        for warning in report["warnings"]:
            st.markdown(f"- {warning}")
    if report["errors"]:
        st.error("Errors recorded for this run:")
        for error in report["errors"]:
            st.markdown(f"- {error}")

    st.subheader("Route cascade risk")
    if report["risk_table"]:
        st.dataframe(
            pd.DataFrame(report["risk_table"])[
                ["route", "risk_class", "cascade_rate", "cascade_probability",
                 "cascade_recurrence", "average_cascade_depth",
                 "delayed_shipments", "cascade_shipments"]
            ],
            width="stretch",
        )
    else:
        st.info("No routes with observed delays in this run.")

    st.subheader("Alerts")
    by_sev = report["alerts"]["by_severity"]
    if report["alerts"]["total"]:
        st.caption(" · ".join(f"{n} {s.lower()}" for s, n in sorted(by_sev.items())))
        st.dataframe(
            pd.DataFrame(report["alerts"]["rows"])[
                ["alert_id", "alert_type", "severity", "entity_type", "entity_id",
                 "metric", "metric_value", "threshold"]
            ].head(100),
            width="stretch",
        )
    else:
        st.info("No alerts were triggered in this run.")

    st.subheader("Investigations & limitations")
    for item in report["investigations"]:
        st.markdown(f"- {item}")

    st.subheader("Download")
    col_md, col_html = st.columns(2)
    with col_md:
        st.download_button(
            label="Download Markdown report",
            data=render_markdown(report),
            file_name=f"report_{report['run_id']}.md",
            mime="text/markdown",
        )
    with col_html:
        st.download_button(
            label="Download HTML report",
            data=render_html(report),
            file_name=f"report_{report['run_id']}.html",
            mime="text/html",
        )


def _render_run_failure(manifest_path: str) -> None:
    """Show what a non-reportable run did record (stages + errors)."""
    try:
        manifest = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Run manifest unreadable: {exc}")
        return
    st.subheader("What this run recorded")
    stages = manifest.get("stages") or {}
    if stages:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Stage": name,
                        "Status": s.get("status", "UNKNOWN"),
                        "Errors": "; ".join(str(e) for e in s.get("errors", [])) or "—",
                    }
                    for name, s in stages.items()
                ]
            ),
            width="stretch",
        )
    for error in manifest.get("errors", []):
        st.markdown(f"- {error}")


if __name__ == "__main__":
    from app.components.standalone import bootstrap_standalone_page

    bootstrap_standalone_page("Reports", render)
