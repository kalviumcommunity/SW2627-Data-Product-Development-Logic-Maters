"""Route-cascade prediction page: validated baseline estimates (no guarantees).

Shows the trained baseline's status, training/test periods, evaluation
metrics, and per-route predicted cascade probabilities beside the
historical empirical rates (labeled separately — never mixed). When no
validated model exists, explains why instead of showing fake predictions.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from analysis.predict import (
    predict_for_shipments,
    predict_single,
    resolve_artifact_or_none,
    route_prediction_summary,
)
from analysis.prediction_model import discover_model_artifacts
from analysis.route_risk import route_cascade_risk
from app.components.charts import bar_chart

UNAVAILABLE_MESSAGE = (
    "Prediction model unavailable: insufficient validated training data."
)


def get_models_dir() -> Path:
    """Artifact directory (``PREDICTION_MODELS_DIR`` override for tests)."""
    override = os.environ.get("PREDICTION_MODELS_DIR")
    if override:
        return Path(override)
    from analysis.prediction_model import DEFAULT_MODELS_DIR

    return DEFAULT_MODELS_DIR


@st.cache_data(show_spinner=False)
def _cached_artifact(models_dir_str: str) -> dict | None:
    """Newest validated model artifact, if any (cached per directory)."""
    return resolve_artifact_or_none(Path(models_dir_str))


@st.cache_data(show_spinner=False)
def _cached_route_predictions(
    filtered: pd.DataFrame, artifact_path: str
) -> tuple[pd.DataFrame, dict]:
    """Per-route predicted probabilities for the selection (cached)."""
    from analysis.predict import load_model

    artifact = load_model(artifact_path)
    predictions, info = predict_for_shipments(filtered, artifact)
    return route_prediction_summary(predictions), info


def _render_unavailable(models_dir: Path) -> None:
    st.info(UNAVAILABLE_MESSAGE)
    st.markdown(
        "ML prediction was not generated because the available dataset did "
        "not meet the minimum validation requirements. The empirical "
        "route-risk analysis on the Routes page remains available — it "
        "describes observed history and is preferable to an invalid model."
    )
    artifacts = discover_model_artifacts(models_dir)
    if artifacts:
        st.caption(
            "Existing artifacts found, but none matched this run's data "
            "context; retrain via the pipeline on a larger dataset."
        )
    else:
        st.caption(
            f"No validated model artifact found in `{models_dir}`. Run "
            "`python -m pipeline.run_pipeline --dataset showcase` on a "
            "dataset with at least 200 delayed shipments and 50 observed "
            "cascades to train the baseline."
        )


def _render_model_status(artifact: dict) -> None:
    st.subheader("Model status")
    test_metrics = artifact["metrics"]["test"]
    cols = st.columns(4)
    cols[0].metric("Model version", str(artifact["model_version"]))
    cols[1].metric("Dataset", str(artifact.get("dataset") or "unknown"))
    cols[2].metric(
        "Test accuracy", f"{test_metrics['accuracy']:.3f}"
        if test_metrics["accuracy"] is not None else "n/a"
    )
    cols[3].metric(
        "Test ROC-AUC", f"{test_metrics['roc_auc']:.3f}"
        if test_metrics["roc_auc"] is not None else "n/a"
    )
    split = artifact["split"]
    st.caption(
        f"Trained {artifact['trained_at']} · train {split['train_period'][0]} → "
        f"{split['train_period'][1]} ({split['train_rows']} delayed shipments, "
        f"{split['train_positives']} cascades) · test {split['test_period'][0]} → "
        f"{split['test_period'][1]} ({split['test_rows']} delayed shipments, "
        f"{split['test_positives']} cascades). Baseline (majority-class) test "
        f"accuracy: {test_metrics['majority_baseline_accuracy']:.3f}."
    )


def _render_metrics(artifact: dict) -> None:
    st.subheader("Evaluation metrics (held-out test period)")
    st.caption(
        "Accuracy alone hides failures on skewed data, so precision, recall, "
        "F1, ROC-AUC, and PR-AUC are reported alongside it."
    )
    rows = []
    for split_name in ("train", "test"):
        metrics = artifact["metrics"][split_name]
        rows.append(
            {
                "Split": split_name,
                "n": metrics["n"],
                "Positives": metrics["positives"],
                "Accuracy": _fmt3(metrics["accuracy"]),
                "Precision": _fmt3(metrics["precision"]),
                "Recall": _fmt3(metrics["recall"]),
                "F1": _fmt3(metrics["f1"]),
                "ROC-AUC": _fmt3(metrics["roc_auc"]),
                "PR-AUC": _fmt3(metrics["pr_auc"]),
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch")
    confusion = artifact["metrics"]["test"]["confusion_matrix"]
    st.caption(
        f"Test confusion matrix — TP {confusion['tp']}, FP {confusion['fp']}, "
        f"TN {confusion['tn']}, FN {confusion['fn']} "
        f"(threshold {artifact['config']['decision_threshold']})."
    )


def _fmt3(value: object) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else "n/a"


def _render_route_predictions(
    filtered: pd.DataFrame, artifact: dict, models_dir: Path
) -> None:
    st.subheader("Predicted route cascade probabilities")
    st.caption(
        "Average predicted probability of cascade across scored delayed "
        "shipments per route (model estimates, not guaranteed outcomes)."
    )
    artifacts = discover_model_artifacts(models_dir)
    artifact_path = artifacts[0]["path"] if artifacts else None
    if artifact_path is None:
        st.info(UNAVAILABLE_MESSAGE)
        return
    try:
        summary, info = _cached_route_predictions(filtered, artifact_path)
    except ValueError as exc:
        st.info(f"Route predictions unavailable for this selection: {exc}")
        return
    if summary.empty:
        st.info("No delayed shipments in the current selection to score.")
        return
    try:
        risk, _ = route_cascade_risk(filtered)
        historical = risk[["route", "cascade_rate"]].rename(
            columns={"cascade_rate": "historical_cascade_rate_pct"}
        )
        combined = summary.merge(historical, on="route", how="left")
    except ValueError:
        combined = summary.assign(historical_cascade_rate_pct=None)
    st.dataframe(combined, width="stretch")
    st.plotly_chart(
        bar_chart(
            summary,
            "route",
            "mean_cascade_probability",
            "Predicted cascade probability by route (model estimate)",
            y_label="Mean predicted probability",
        ),
        width="stretch",
    )
    st.caption(
        "Historical cascade rate = observed cascades ÷ initial delays "
        "(what already happened). Model prediction = estimated probability "
        "for new delayed shipments (validated on the held-out test period)."
    )


def _render_estimator(artifact: dict) -> None:
    st.subheader("Single-shipment estimator")
    st.caption(
        "Estimate the cascade probability for a newly observed initial "
        "delay. Uses only information available at the prediction point."
    )
    routes = list(artifact["fitted"]["vocabularies"].get("route", [])) or ["R1"]
    scans = list(artifact["fitted"]["vocabularies"].get("initial_scan_type", [])) or [
        "unknown"
    ]
    warehouses = list(
        artifact["fitted"]["vocabularies"].get("initial_warehouse", [])
    ) or ["unknown"]
    col_a, col_b = st.columns(2)
    with col_a:
        route = st.selectbox("Route", routes)
        scan = st.selectbox("Initial event stage", scans)
    with col_b:
        warehouse = st.selectbox("Initial warehouse", warehouses)
        duration = st.number_input(
            "Initial delay (minutes)", min_value=0.0, value=30.0, step=5.0
        )
    try:
        result = predict_single(
            {
                "route": route,
                "initial_delay_duration": float(duration),
                "initial_scan_type": scan,
                "initial_warehouse": warehouse,
            },
            artifact,
        )
    except ValueError as exc:
        st.error(f"Invalid input: {exc}")
        return
    st.metric(
        "Predicted probability of cascade",
        f"{result['cascade_probability']:.2f}",
        help="Model estimate, not a certainty.",
    )
    st.caption(
        f"Predicted class: {'cascade' if result['prediction'] else 'no cascade'} "
        f"(threshold {artifact['config']['decision_threshold']}) · "
        f"model {result['model_version']}."
    )


def _render_limitations(artifact: dict) -> None:
    st.subheader("Data limitations")
    for item in artifact.get("limitations", []):
        st.markdown(f"- {item}")


def render(filtered: pd.DataFrame, full: pd.DataFrame) -> None:
    st.header("Route cascade prediction")
    st.caption(
        "Lightweight, explainable baseline: given an observed initial delay, "
        "what is the estimated probability of a downstream (cascading) delay?"
    )
    models_dir = get_models_dir()
    artifact = _cached_artifact(str(models_dir))
    if artifact is None:
        _render_unavailable(models_dir)
        return
    _render_model_status(artifact)
    _render_metrics(artifact)
    _render_route_predictions(filtered, artifact, models_dir)
    _render_estimator(artifact)
    _render_limitations(artifact)


if __name__ == "__main__":
    from app.components.standalone import bootstrap_standalone_page

    bootstrap_standalone_page("Prediction", render)
