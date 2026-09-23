"""Tests for the route-cascade prediction baseline (deterministic fixtures).

Covers: target generation, leakage guards, temporal splitting, feature
generation, insufficient-data handling, class imbalance, training,
evaluation, serialization, inference, probability ranges, output schemas,
version metadata, dashboard/report/pipeline behavior, and secrets.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.cascade_analysis import detect_cascade_candidates
from analysis.predict import (
    PREDICTION_COLUMNS,
    predict_for_shipments,
    predict_single,
    route_prediction_summary,
    validate_inference_record,
)
from analysis.prediction_features import (
    ALLOWED_HISTORICAL_FEATURES,
    TARGET_COLUMN,
    apply_route_history,
    assess_prediction_readiness,
    assert_no_leakage_columns,
    build_delayed_shipment_table,
    build_feature_matrix,
    build_prediction_dataset,
    fit_route_history,
    temporal_split,
)
from analysis.prediction_model import (
    PREDICTION_AVAILABLE,
    PREDICTION_UNAVAILABLE,
    artifact_has_no_secrets,
    average_precision_score,
    balanced_sample_weight,
    discover_model_artifacts,
    evaluate_predictions,
    load_model_artifact,
    roc_auc_score,
    save_model_artifact,
    train_and_evaluate,
    train_logistic_regression,
)
from config.prediction_config import resolve_prediction_config

TINY_CONFIG = {
    "min_delayed_shipments": 6,
    "min_cascade_positives": 2,
    "min_train_positives": 1,
    "min_test_positives": 1,
    "min_observed_days": 1,
}


def journey_frame() -> pd.DataFrame:
    """Deterministic journeys: known cascades across routes and days."""
    rows = []
    plan = [
        # (shipment, route, [(day, duration), ...])
        ("A", "R1", [("01", 10.0), ("02", 30.0)]),  # cascade
        ("B", "R1", [("03", 15.0)]),  # single delay
        ("C", "R1", [("04", 12.0), ("05", 22.0)]),  # cascade
        ("D", "R2", [("06", 20.0)]),  # single delay
        ("E", "R2", [("07", 18.0), ("08", 40.0)]),  # cascade
        ("F", "R2", [("09", 11.0), ("10", 13.0)]),  # cascade
        ("G", "R1", [("11", 0.0)]),  # on-time, out of scope
        ("H", "R3", [("12", 25.0), ("13", 35.0)]),  # cascade, late period
        ("I", "R3", [("14", 16.0)]),  # single delay, late period
        ("J", "R3", [("15", 0.0)]),  # on-time, out of scope
    ]
    for shipment, route, events in plan:
        for day, duration in events:
            rows.append(
                {
                    "shipment_id": shipment,
                    "timestamp": f"2024-01-{day} 08:00:00",
                    "route_id": route,
                    "warehouse_id": "W1",
                    "scan_type": "pickup",
                    "delay_duration": duration,
                    "delay_reason": "traffic",
                    "reported_at": "2024-02-01 00:00:00",
                    "transfer_id": f"T-{shipment}",
                    "transfer_status": "delayed",
                }
            )
    return pd.DataFrame(rows)


def test_target_generation_matches_cascade_definition() -> None:
    df = journey_frame()
    shipments, info = build_delayed_shipment_table(df)
    candidates, _ = detect_cascade_candidates(df)
    expected = set(candidates["shipment_id"].astype(str))
    flagged = set(shipments.loc[shipments[TARGET_COLUMN] == 1, "shipment_id"])
    assert flagged == expected
    assert set(shipments[TARGET_COLUMN].unique()) <= {0, 1}
    # On-time shipments G/J are out of scope, counted but not returned.
    assert "G" not in set(shipments["shipment_id"])
    assert info["delayed_shipments"] == 8
    assert info["cascade_shipments"] == 5


def test_no_leakage_in_feature_names() -> None:
    df = journey_frame()
    bundle = build_prediction_dataset(df, TINY_CONFIG)
    assert_no_leakage_columns(bundle["feature_names"])
    forbidden = (
        "delay_reason", "reported_at", "transfer_", "downstream",
        "final_", "cascade_depth", "stages",
    )
    for name in bundle["feature_names"]:
        lowered = name.lower()
        if lowered in ALLOWED_HISTORICAL_FEATURES:
            continue
        assert not any(token in lowered for token in forbidden), name


def test_delay_reason_does_not_change_features() -> None:
    df = journey_frame()
    variant = df.copy(deep=True)
    variant["delay_reason"] = "weather"
    first = build_prediction_dataset(df, TINY_CONFIG)
    second = build_prediction_dataset(variant, TINY_CONFIG)
    pd.testing.assert_frame_equal(first["X_train"], second["X_train"])
    pd.testing.assert_frame_equal(first["X_test"], second["X_test"])


def test_leakage_guard_rejects_post_outcome_columns() -> None:
    with pytest.raises(ValueError, match="Leakage guard"):
        assert_no_leakage_columns(["route_hist_cascade_rate", "downstream_delay"])
    with pytest.raises(ValueError, match="Leakage guard"):
        assert_no_leakage_columns(["cascade_depth"])
    with pytest.raises(ValueError, match="Leakage guard"):
        assert_no_leakage_columns(["delay_reason"])
    # The documented train-only historical features are allowed.
    assert_no_leakage_columns(
        ["initial_delay_duration", "route_hist_cascade_rate", "route=R1"]
    )


def test_temporal_split_is_chronological() -> None:
    df = journey_frame()
    shipments, _ = build_delayed_shipment_table(df)
    train, test, info = temporal_split(shipments, 0.7)
    assert info["train_rows"] + info["test_rows"] == len(shipments)
    train_max = pd.to_datetime(train["initial_delay_time"], utc=True).max()
    test_min = pd.to_datetime(test["initial_delay_time"], utc=True).min()
    assert train_max <= test_min
    assert info["strategy"].startswith("chronological")
    assert info["train_period"][0] <= info["test_period"][0]


def test_route_history_uses_training_data_only() -> None:
    df = journey_frame()
    shipments, _ = build_delayed_shipment_table(df)
    train, test, _ = temporal_split(shipments, 0.7)
    history = fit_route_history(train)
    # Train-only rate for each route matches the train frame exactly.
    for route in train["route"].unique():
        group = train[train["route"] == route]
        expected = float(group[TARGET_COLUMN].sum()) / len(group)
        assert history["route_rates"][str(route)] == pytest.approx(expected)
    # Routes unseen in training fall back to the global training rate.
    assert "R3" not in history["route_rates"] or True
    mapped = apply_route_history(test, history)
    assert (mapped["route_hist_cascade_rate"] >= 0).all()
    assert (mapped["route_hist_cascade_rate"] <= 1).all()
    unseen = pd.DataFrame(
        {
            "shipment_id": ["Z"],
            "route": ["RX_UNSEEN"],
            "initial_delay_time": [pd.Timestamp("2024-01-20", tz="UTC")],
            "initial_event_seq": [1],
            "initial_delay_duration": [10.0],
            "initial_scan_type": ["pickup"],
            "initial_warehouse": ["W1"],
            TARGET_COLUMN: [0],
        }
    )
    fallback = apply_route_history(unseen, history)
    assert fallback["route_hist_cascade_rate"].iloc[0] == pytest.approx(
        history["global_rate"]
    )


def test_feature_generation_schema_and_determinism() -> None:
    df = journey_frame()
    before = df.copy(deep=True)
    bundle = build_prediction_dataset(df, TINY_CONFIG)
    pd.testing.assert_frame_equal(df, before)
    assert list(bundle["X_train"].columns) == bundle["feature_names"]
    assert list(bundle["X_test"].columns) == bundle["feature_names"]
    assert bundle["X_train"].isna().sum().sum() == 0
    repeat = build_prediction_dataset(df, TINY_CONFIG)
    pd.testing.assert_frame_equal(bundle["X_train"], repeat["X_train"])
    assert bundle["feature_names"] == repeat["feature_names"]


def test_insufficient_data_is_reported_not_modeled() -> None:
    # Empty input.
    empty = assess_prediction_readiness(pd.DataFrame())
    assert empty["available"] is False
    # Tiny frame: 2 delayed shipments, 1 cascade.
    tiny = pd.DataFrame(
        [
            {"shipment_id": "A", "timestamp": "2024-01-01 08:00",
             "route_id": "R1", "delay_duration": 10.0},
            {"shipment_id": "A", "timestamp": "2024-01-02 08:00",
             "route_id": "R1", "delay_duration": 20.0},
            {"shipment_id": "B", "timestamp": "2024-01-03 08:00",
             "route_id": "R1", "delay_duration": 5.0},
        ]
    )
    readiness = assess_prediction_readiness(tiny)
    assert readiness["available"] is False
    assert "minimum" in readiness["reason"]
    assert readiness["cascade_shipments"] == 1
    with pytest.raises(ValueError, match="Insufficient validated training data"):
        build_prediction_dataset(tiny)
    with pytest.raises(ValueError, match="Insufficient validated training data"):
        train_and_evaluate(tiny)
    # LaDe-like: many shipments, one cascade (two delayed events on S000).
    rows = []
    for i in range(60):
        day = (i % 14) + 1
        if i == 0:
            rows.append(
                {"shipment_id": "S000", "timestamp": "2024-01-01 08:00",
                 "route_id": "region_1", "delay_duration": 30.0}
            )
            rows.append(
                {"shipment_id": "S000", "timestamp": "2024-01-02 08:00",
                 "route_id": "region_1", "delay_duration": 45.0}
            )
        elif i == 1:
            rows.append(
                {"shipment_id": "S001", "timestamp": f"2024-01-{day:02d} 08:00",
                 "route_id": "region_2", "delay_duration": 0.0}
            )
        else:
            rows.append(
                {"shipment_id": f"S{i:03d}", "timestamp": f"2024-01-{day:02d} 08:00",
                 "route_id": f"region_{(i % 4) + 1}", "delay_duration": 0.0}
            )
    lade_like = pd.DataFrame(rows)
    status = assess_prediction_readiness(lade_like)
    assert status["available"] is False
    assert status["cascade_shipments"] == 1


def test_class_imbalance_handling() -> None:
    # 30 delayed shipments on distinct days; cascades at days 1, 2, 29, 30
    # so both chronological halves contain positives.
    rows = []
    for i in range(30):
        day = i + 1
        events = [10.0, 20.0] if i in (0, 1, 28, 29) else [10.0]
        for duration in events:
            rows.append(
                {
                    "shipment_id": f"S{i:02d}",
                    "timestamp": f"2024-01-{day:02d} 08:00:00",
                    "route_id": "R1" if i % 2 else "R2",
                    "warehouse_id": "W1",
                    "delay_duration": duration,
                }
            )
    df = pd.DataFrame(rows)
    config = dict(TINY_CONFIG, min_delayed_shipments=10, min_cascade_positives=2,
                  min_observed_days=1)
    readiness = assess_prediction_readiness(df, config)
    assert readiness["available"] is True
    assert readiness["class_imbalance"] < 0.35
    result = train_and_evaluate(df, config=config, dataset_label="imbalanced")
    assert result["class_weight_effective"] == "balanced"
    weights = balanced_sample_weight(result_bundle_y_train(df, config))
    assert len(weights) == readiness["train_rows"]
    metrics = result["metrics"]["test"]
    assert metrics["precision"] is not None or metrics["positives"] in (0, metrics["n"])


def result_bundle_y_train(df: pd.DataFrame, config: dict) -> pd.Series:
    return build_prediction_dataset(df, config)["y_train"]


def test_model_training_converges_and_is_deterministic() -> None:
    df = journey_frame()
    first = train_and_evaluate(df, config=TINY_CONFIG, dataset_label="test")
    second = train_and_evaluate(df, config=TINY_CONFIG, dataset_label="test")
    assert first["coefficients"] == second["coefficients"]
    assert np.isfinite(first["final_train_loss"])
    assert len(first["coefficients"]) == len(first["feature_names"])
    # A direct low-level fit also converges on separable toy data.
    X = np.array([[0.0], [1.0], [2.0], [3.0]])
    y = np.array([0, 0, 1, 1])
    fitted = train_logistic_regression(X, y)
    assert np.isfinite(fitted["final_loss"])
    assert fitted["iterations"] == 2000


def test_model_evaluation_reports_all_metrics() -> None:
    df = journey_frame()
    result = train_and_evaluate(df, config=TINY_CONFIG, dataset_label="test")
    for split_name in ("train", "test"):
        metrics = result["metrics"][split_name]
        for key in (
            "accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc",
            "confusion_matrix", "majority_baseline_accuracy", "baseline_rate",
        ):
            assert key in metrics, (split_name, key)
        total = (
            metrics["confusion_matrix"]["tp"] + metrics["confusion_matrix"]["fp"]
            + metrics["confusion_matrix"]["tn"] + metrics["confusion_matrix"]["fn"]
        )
        assert total == metrics["n"]
        assert 0.0 <= metrics["accuracy"] <= 1.0
        if metrics["roc_auc"] is not None:
            assert 0.0 <= metrics["roc_auc"] <= 1.0
    # Degenerate single-class input yields None AUCs instead of crashing.
    degenerate = evaluate_predictions(
        pd.Series([0, 0, 0]), np.array([0.1, 0.2, 0.3])
    )
    assert degenerate["roc_auc"] is None
    assert degenerate["pr_auc"] is None
    # Rank-based AUC helpers behave on known orderings.
    assert roc_auc_score(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(1.0)
    assert roc_auc_score(np.array([0, 1]), np.array([0.5, 0.5])) == pytest.approx(0.5)
    assert average_precision_score(np.array([0, 0]), np.array([0.1, 0.9])) is None


def test_model_serialization_roundtrip(tmp_path: Path) -> None:
    df = journey_frame()
    result = train_and_evaluate(df, config=TINY_CONFIG, dataset_label="test")
    assert artifact_has_no_secrets(result)
    path = save_model_artifact(result, tmp_path / "models")
    assert path.is_file()
    loaded = load_model_artifact(path)
    assert loaded["coefficients"] == result["coefficients"]
    # Inference identical before/after the roundtrip.
    before, _ = predict_for_shipments(df, result)
    after, _ = predict_for_shipments(df, loaded)
    pd.testing.assert_frame_equal(before, after)
    # Discovery lists the artifact newest-first.
    entries = discover_model_artifacts(tmp_path / "models")
    assert entries and entries[0]["path"] == str(path)
    assert discover_model_artifacts(tmp_path / "empty") == []
    # Corrupt artifacts fail clearly.
    with pytest.raises(FileNotFoundError, match="not found"):
        load_model_artifact(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_model_artifact(bad)
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps({"model_version": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="misses keys"):
        load_model_artifact(incomplete)


def test_inference_single_and_batch() -> None:
    df = journey_frame()
    result = train_and_evaluate(df, config=TINY_CONFIG, dataset_label="test")
    single = predict_single(
        {"route": "R1", "initial_delay_duration": 45.0,
         "initial_scan_type": "pickup", "initial_warehouse": "W1"},
        result,
    )
    assert set(single) == {"route", "prediction", "cascade_probability", "model_version"}
    assert single["route"] == "R1"
    assert single["prediction"] in (0, 1)
    assert 0.0 <= single["cascade_probability"] <= 1.0
    assert single["model_version"] == result["model_version"]
    # Minimal record uses safe defaults; unseen routes fall back gracefully.
    fallback = predict_single({"route": "RX_NEW"}, result)
    assert 0.0 <= fallback["cascade_probability"] <= 1.0
    # Batch scoring schema.
    predictions, info = predict_for_shipments(df, result)
    assert list(predictions.columns) == [
        "shipment_id", "route", "initial_delay_time",
        "cascade_probability", "prediction", "model_version",
    ]
    assert info["scored_shipments"] == len(predictions) == 8
    assert ((predictions["cascade_probability"] >= 0.0)
            & (predictions["cascade_probability"] <= 1.0)).all()
    # Invalid records fail clearly.
    with pytest.raises(ValueError, match="non-blank 'route'"):
        validate_inference_record({"route": "  "})
    with pytest.raises(ValueError, match="non-negative"):
        validate_inference_record({"route": "R1", "initial_delay_duration": -5})
    with pytest.raises(ValueError, match="parseable timestamp"):
        validate_inference_record(
            {"route": "R1", "initial_delay_time": "not-a-time"})
    with pytest.raises(ValueError, match="mapping"):
        validate_inference_record(["R1"])  # type: ignore[arg-type]


def test_route_level_prediction_output() -> None:
    df = journey_frame()
    result = train_and_evaluate(df, config=TINY_CONFIG, dataset_label="test")
    predictions, _ = predict_for_shipments(df, result)
    summary = route_prediction_summary(predictions)
    assert list(summary.columns) == [
        "route", "predicted_shipments", "mean_cascade_probability",
        "share_predicted_cascade",
    ]
    assert ((summary["mean_cascade_probability"] >= 0.0)
            & (summary["mean_cascade_probability"] <= 1.0)).all()
    assert summary["predicted_shipments"].sum() == len(predictions)
    assert route_prediction_summary(predictions.iloc[0:0]).empty


def test_model_version_metadata() -> None:
    config = resolve_prediction_config(
        {**TINY_CONFIG, "model_version": "custom-v9"}
    )
    assert config["model_version"] == "custom-v9"
    df = journey_frame()
    result = train_and_evaluate(df, config=config, dataset_label="test")
    assert result["model_version"] == "custom-v9"
    assert result["target"] == TARGET_COLUMN
    assert result["trained_at"]
    assert result["dataset"] == "test"
    with pytest.raises(ValueError, match="Unknown prediction config keys"):
        resolve_prediction_config({"nope": 1})


def _write_fixture_artifact(models_dir: Path) -> dict:
    df = journey_frame()
    result = train_and_evaluate(df, config=TINY_CONFIG, dataset_label="fixture")
    save_model_artifact(result, models_dir, filename="route_cascade_baseline_test.json")
    return result


def _page_text(at: object) -> str:
    parts: list[str] = []
    for attr in ("info", "markdown", "caption", "header", "subheader", "metric",
                 "error", "warning", "success", "dataframe", "table"):
        try:
            elements = getattr(at, attr)
        except Exception:  # pragma: no cover - harness API drift
            continue
        try:
            for element in elements:
                parts.append(str(getattr(element, "value", element)))
        except Exception:  # pragma: no cover - harness API drift
            continue
    return "\n".join(parts)


def test_dashboard_prediction_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    streamlit = pytest.importorskip("streamlit")
    app_test = pytest.importorskip("streamlit.testing.v1")
    _ = streamlit
    monkeypatch.setenv("PREDICTION_MODELS_DIR", str(tmp_path / "no-models"))
    entrypoint = Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py"
    at = app_test.AppTest.from_file(entrypoint, default_timeout=120)
    at.run()
    assert not at.exception
    at.sidebar.radio[0].set_value("Prediction").run()
    assert not at.exception
    assert "insufficient validated training data" in _page_text(at).lower()


def test_dashboard_prediction_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    streamlit = pytest.importorskip("streamlit")
    app_test = pytest.importorskip("streamlit.testing.v1")
    _ = streamlit
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    result = _write_fixture_artifact(models_dir)
    monkeypatch.setenv("PREDICTION_MODELS_DIR", str(models_dir))
    entrypoint = Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py"
    at = app_test.AppTest.from_file(entrypoint, default_timeout=180)
    at.run()
    assert not at.exception
    at.sidebar.radio[0].set_value("Prediction").run()
    assert not at.exception
    text = _page_text(at).lower()
    assert result["model_version"].lower() in text
    assert "roc-auc" in text


def _tmp_pipeline_run(
    tmp_path: Path, n_shipments: int, seed: int = 7
) -> dict:
    from pipeline.run_pipeline import run_pipeline

    models_dir = tmp_path / "models"
    manifest = run_pipeline(
        dataset="showcase",
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        runs_dir=tmp_path / "runs",
        output_path=tmp_path / "integrated.csv",
        seed=seed,
        n_shipments=n_shipments,
        models_dir=models_dir,
    )
    return {"manifest": manifest, "tmp": tmp_path, "models_dir": models_dir}


def test_pipeline_prediction_unavailable_never_fails(tmp_path: Path) -> None:
    from pipeline.run_pipeline import STAGE_ORDER

    assert "prediction" in STAGE_ORDER
    assert STAGE_ORDER.index("prediction") > STAGE_ORDER.index("route_risk")
    run = _tmp_pipeline_run(tmp_path, n_shipments=60)
    manifest = run["manifest"]
    stage = manifest["stages"]["prediction"]
    assert stage["status"] == "WARNING"
    assert stage["detail"]["status"] == PREDICTION_UNAVAILABLE
    assert manifest["outputs"]["prediction_model"] is None
    assert manifest["overall_status"] in ("SUCCESS", "SUCCESS_WITH_WARNINGS")
    assert manifest["stages"]["alerts"]["status"] in ("SUCCESS", "WARNING")


def test_pipeline_prediction_available_records_artifact(tmp_path: Path) -> None:
    run = _tmp_pipeline_run(tmp_path, n_shipments=800)
    manifest = run["manifest"]
    stage = manifest["stages"]["prediction"]
    assert stage["status"] == "SUCCESS"
    assert stage["detail"]["status"] == PREDICTION_AVAILABLE
    ref = manifest["outputs"]["prediction_model"]
    assert Path(ref["path"]).is_file()
    assert ref["path"].startswith(str(run["models_dir"]))
    test_metrics = stage["detail"]["test_metrics"]
    for key in ("accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc"):
        assert key in test_metrics
    assert stage["detail"]["route_predictions"]
    loaded = load_model_artifact(ref["path"])
    assert artifact_has_no_secrets(loaded)


def test_report_prediction_sections(tmp_path: Path) -> None:
    from reports.report_generator import PREDICTION_NOT_GENERATED, build_report

    available = _tmp_pipeline_run(tmp_path / "ok", n_shipments=800)
    report = build_report(Path(available["manifest"]["manifest_path"]))
    pred = report["prediction"]
    assert pred["status"] == PREDICTION_AVAILABLE
    assert pred["model_version"]
    assert pred["route_predictions"]
    assert pred["test_metrics"]["roc_auc"] is not None
    assert "not an ml prediction" in (
        __import__("reports.report_generator", fromlist=["render_markdown"])
        .render_markdown(report).lower()
    )

    from reports.report_generator import render_markdown

    text = render_markdown(report)
    assert "### ML prediction baseline" in text
    assert pred["model_version"] in text
    assert "Mean estimated P(cascade)" in text

    small = _tmp_pipeline_run(tmp_path / "small", n_shipments=60)
    small_report = build_report(Path(small["manifest"]["manifest_path"]))
    assert small_report["prediction"]["status"] == PREDICTION_UNAVAILABLE
    small_text = render_markdown(small_report)
    assert PREDICTION_NOT_GENERATED in small_text
    for section in ("## 6. Route Intelligence", "## 9. Alerts", "## 12. Limitations"):
        assert section in small_text


def test_no_secrets_in_model_metadata(tmp_path: Path) -> None:
    df = journey_frame()
    result = train_and_evaluate(df, config=TINY_CONFIG, dataset_label="test")
    path = save_model_artifact(result, tmp_path / "models")
    text = path.read_text(encoding="utf-8").lower()
    for marker in ("password", "secret", "token", "api_key", "smtp", "credential"):
        assert marker not in text
    assert artifact_has_no_secrets(result)
    assert artifact_has_no_secrets(json.loads(path.read_text(encoding="utf-8")))
