"""Validated predictive baseline for route cascades (NumPy-only).

Model: L2-regularized logistic regression fitted with deterministic
full-batch gradient descent (zero initialization, fixed learning rate and
iteration budget — no randomness, no new dependencies). This is an
analytical baseline, not a production-grade predictor: probabilities are
reported as *estimated* probabilities with explicit limitations, never
as certainties or causal claims.

Artifacts are plain JSON (coefficients, scaler, vocabularies, metrics,
metadata) — a safe serialization with no pickle and no secrets. Loading
an artifact only needs NumPy, so inference works anywhere the feature
builder runs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

from analysis.prediction_features import (
    TARGET_COLUMN,
    TARGET_DEFINITION,
    build_prediction_dataset,
)
from config.prediction_config import (
    resolve_prediction_config,
)

PathLike = Union[str, Path]

PREDICTION_AVAILABLE = "PREDICTION_AVAILABLE"
PREDICTION_UNAVAILABLE = "PREDICTION_UNAVAILABLE"

DEFAULT_MODELS_DIR = Path("data/processed/models")

REQUIRED_ARTIFACT_KEYS = (
    "model_version",
    "target",
    "target_definition",
    "feature_names",
    "coefficients",
    "intercept",
    "scaler",
    "fitted",
    "history",
    "config",
    "metrics",
    "split",
    "trained_at",
)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid."""
    out = np.empty_like(values, dtype=float)
    positive = values >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_values = np.exp(values[~positive])
    out[~positive] = exp_values / (1.0 + exp_values)
    return out


def fit_scaler(matrix: pd.DataFrame) -> dict[str, list[float]]:
    """Column means/stds from the training matrix (std 0 guarded to 1)."""
    values = matrix.to_numpy(dtype=float)
    means = np.nanmean(values, axis=0)
    stds = np.nanstd(values, axis=0)
    stds = np.where(np.isnan(stds) | (stds == 0.0), 1.0, stds)
    means = np.where(np.isnan(means), 0.0, means)
    return {"means": [float(m) for m in means], "stds": [float(s) for s in stds]}


def apply_scaler(matrix: pd.DataFrame, scaler: dict[str, list[float]]) -> np.ndarray:
    """Standardize columns with a fitted scaler (read-only)."""
    values = matrix.to_numpy(dtype=float)
    means = np.asarray(scaler["means"], dtype=float)
    stds = np.asarray(scaler["stds"], dtype=float)
    return (np.nan_to_num(values, nan=0.0) - means) / stds


def train_logistic_regression(
    features: np.ndarray,
    target: np.ndarray,
    learning_rate: float = 0.5,
    max_iterations: int = 2000,
    l2_penalty: float = 1.0,
    sample_weight: Optional[np.ndarray] = None,
) -> dict[str, Any]:
    """Fit binary logistic regression (deterministic gradient descent).

    Zero-initialized weights, full-batch updates, L2 penalty on the
    coefficients (intercept unpenalized). Returns weights, intercept, and
    the final average log-loss.
    """
    X = np.asarray(features, dtype=float)
    y = np.asarray(target, dtype=float).reshape(-1)
    n, p = X.shape
    weights = np.zeros(p, dtype=float)
    intercept = 0.0
    if sample_weight is None:
        sample_weight = np.ones(n, dtype=float)
    else:
        sample_weight = np.asarray(sample_weight, dtype=float).reshape(-1)
    total_weight = float(sample_weight.sum()) or 1.0
    for _ in range(int(max_iterations)):
        logits = X @ weights + intercept
        probs = _sigmoid(logits)
        errors = (probs - y) * sample_weight / total_weight
        gradient = X.T @ errors + float(l2_penalty) * weights / max(n, 1)
        intercept_gradient = float(errors.sum())
        weights = weights - float(learning_rate) * gradient
        intercept = intercept - float(learning_rate) * intercept_gradient
    logits = X @ weights + intercept
    probs = np.clip(_sigmoid(logits), 1e-12, 1.0 - 1e-12)
    loss = float(
        -(sample_weight * (y * np.log(probs) + (1.0 - y) * np.log(1.0 - probs))).sum()
        / total_weight
    )
    return {
        "coefficients": [float(w) for w in weights],
        "intercept": float(intercept),
        "final_loss": loss,
        "iterations": int(max_iterations),
    }


def balanced_sample_weight(target: pd.Series) -> np.ndarray:
    """Inverse-frequency weights (n / (2 * n_class)) for each row."""
    y = np.asarray(target.to_numpy(dtype=int)).reshape(-1)
    n = len(y)
    positives = int((y == 1).sum())
    negatives = n - positives
    weight_pos = n / (2.0 * positives) if positives else 1.0
    weight_neg = n / (2.0 * negatives) if negatives else 1.0
    return np.where(y == 1, weight_pos, weight_neg).astype(float)


def predict_proba_from_params(
    matrix: pd.DataFrame,
    coefficients: list[float],
    intercept: float,
    scaler: dict[str, list[float]],
    feature_names: list[str],
) -> np.ndarray:
    """Estimated P(cascade) for each row (column order validated)."""
    if list(matrix.columns) != list(feature_names):
        raise ValueError(
            "Feature columns do not match the trained model: "
            f"expected {feature_names}, got {list(matrix.columns)}."
        )
    standardized = apply_scaler(matrix, scaler)
    logits = standardized @ np.asarray(coefficients, dtype=float) + float(intercept)
    return _sigmoid(logits)


def roc_auc_score(y_true: np.ndarray, y_score: np.ndarray) -> Optional[float]:
    """Rank-based ROC-AUC with tie-averaged ranks (None on single class)."""
    y_true = np.asarray(y_true, dtype=int).reshape(-1)
    y_score = np.asarray(y_score, dtype=float).reshape(-1)
    positives = int((y_true == 1).sum())
    negatives = int((y_true == 0).sum())
    if positives == 0 or negatives == 0:
        return None
    order = np.argsort(y_score, kind="mergesort")
    sorted_scores = y_score[order]
    ranks = np.empty(len(y_score), dtype=float)
    start = 0
    while start < len(y_score):
        end = start + 1
        while end < len(y_score) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        average_rank = (start + 1 + end) / 2.0  # 1-based mean rank of the tie
        ranks[order[start:end]] = average_rank
        start = end
    rank_sum = float(ranks[y_true == 1].sum())
    auc = (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)
    return float(min(max(auc, 0.0), 1.0))


def average_precision_score(
    y_true: np.ndarray, y_score: np.ndarray
) -> Optional[float]:
    """Average precision (PR-AUC summary; None when no positives)."""
    y_true = np.asarray(y_true, dtype=int).reshape(-1)
    y_score = np.asarray(y_score, dtype=float).reshape(-1)
    positives = int((y_true == 1).sum())
    if positives == 0:
        return None
    order = np.argsort(-y_score, kind="mergesort")
    ranked = y_true[order]
    cumulative = np.cumsum(ranked)
    precision = cumulative / np.arange(1, len(ranked) + 1)
    return float((precision[ranked == 1].sum()) / positives)


def evaluate_predictions(
    y_true: pd.Series,
    y_prob: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Classification metrics at a fixed decision threshold (read-only).

    Accuracy is reported alongside precision/recall/F1 — never alone —
    because accuracy hides failures on imbalanced data. ROC-AUC is None
    with a single test class; PR-AUC is None with no test positives.
    """
    y = np.asarray(y_true.to_numpy(dtype=int)).reshape(-1)
    prob = np.asarray(y_prob, dtype=float).reshape(-1)
    predicted = (prob >= float(threshold)).astype(int)
    tp = int(((predicted == 1) & (y == 1)).sum())
    fp = int(((predicted == 1) & (y == 0)).sum())
    tn = int(((predicted == 0) & (y == 0)).sum())
    fn = int(((predicted == 0) & (y == 1)).sum())
    total = len(y)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall)
        else None
    )
    majority = max(int((y == 1).sum()), int((y == 0).sum()))
    return {
        "n": total,
        "positives": int((y == 1).sum()),
        "negatives": int((y == 0).sum()),
        "baseline_rate": float((y == 1).mean()) if total else 0.0,
        "majority_baseline_accuracy": (majority / total) if total else None,
        "accuracy": float((predicted == y).mean()) if total else None,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "roc_auc": roc_auc_score(y, prob),
        "pr_auc": average_precision_score(y, prob),
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "threshold": float(threshold),
    }


def train_and_evaluate(
    dataset: pd.DataFrame,
    config: Optional[dict[str, Any]] = None,
    dataset_label: str = "unknown",
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    """Train the baseline on the chronological train split, evaluate on test.

    Raises:
        ValueError: When the dataset fails the readiness assessment (the
            reason explains the unmet requirement — never a silent skip).
    """
    cfg = resolve_prediction_config(config)
    bundle = build_prediction_dataset(dataset, cfg)
    X_train = bundle["X_train"]
    X_test = bundle["X_test"]
    y_train = bundle["y_train"]
    y_test = bundle["y_test"]

    minority_share = float(
        min(int(y_train.sum()), int(len(y_train) - y_train.sum())) / max(len(y_train), 1)
    )
    if cfg["class_weight"] == "balanced":
        effective_weight: Optional[str] = "balanced"
    elif minority_share < float(cfg["auto_balance_minority_share"]):
        effective_weight = "balanced"
    else:
        effective_weight = None
    sample_weight = balanced_sample_weight(y_train) if effective_weight else None

    scaler = fit_scaler(X_train)
    fitted = train_logistic_regression(
        apply_scaler(X_train, scaler),
        y_train.to_numpy(dtype=int),
        learning_rate=float(cfg["learning_rate"]),
        max_iterations=int(cfg["max_iterations"]),
        l2_penalty=float(cfg["l2_penalty"]),
        sample_weight=sample_weight,
    )
    train_prob = predict_proba_from_params(
        X_train, fitted["coefficients"], fitted["intercept"], scaler,
        bundle["feature_names"],
    )
    test_prob = predict_proba_from_params(
        X_test, fitted["coefficients"], fitted["intercept"], scaler,
        bundle["feature_names"],
    )
    threshold = float(cfg["decision_threshold"])
    result = {
        "model_version": str(cfg["model_version"]),
        "target": TARGET_COLUMN,
        "target_definition": TARGET_DEFINITION,
        "dataset": str(dataset_label),
        "run_id": run_id,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_names": bundle["feature_names"],
        "coefficients": fitted["coefficients"],
        "intercept": fitted["intercept"],
        "final_train_loss": fitted["final_loss"],
        "scaler": scaler,
        "fitted": bundle["fitted"],
        "history": bundle["history"],
        "config": cfg,
        "split": bundle["split"],
        "readiness": bundle["readiness"],
        "class_weight_effective": effective_weight,
        "train_minority_share": minority_share,
        "metrics": {
            "train": evaluate_predictions(y_train, train_prob, threshold),
            "test": evaluate_predictions(y_test, test_prob, threshold),
        },
        "limitations": [
            "Analytical baseline: estimated probabilities from historical "
            "patterns, not guaranteed outcomes and not proof of causation.",
            "Applies only to shipments with an observed initial delay; "
            "shipments without any delay are out of scope.",
            "Route history uses training-period observations only; routes "
            "unseen in training fall back to the global training rate.",
        ],
    }
    return result


def save_model_artifact(
    result: dict[str, Any],
    models_dir: PathLike = DEFAULT_MODELS_DIR,
    filename: Optional[str] = None,
) -> Path:
    """Write a training result as JSON (creates parents; no secrets)."""
    directory = Path(models_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if filename is None:
        stamp = str(result.get("trained_at", "")).replace(":", "").replace("+", "p")
        run = str(result.get("run_id") or "norun")
        filename = f"route_cascade_baseline_{stamp}_{run}.json"
    destination = directory / filename
    destination.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return destination


def load_model_artifact(path: PathLike) -> dict[str, Any]:
    """Load and validate a model artifact (clear error when unusable)."""
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Model artifact not found: {resolved}.")
    try:
        artifact = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model artifact is not valid JSON: {resolved} ({exc}).") from exc
    missing = [k for k in REQUIRED_ARTIFACT_KEYS if k not in artifact]
    if missing:
        raise ValueError(f"Model artifact {resolved} misses keys: {missing}.")
    if len(artifact["feature_names"]) != len(artifact["coefficients"]):
        raise ValueError(
            f"Model artifact {resolved} has "
            f"{len(artifact['feature_names'])} features but "
            f"{len(artifact['coefficients'])} coefficients."
        )
    return artifact


def discover_model_artifacts(
    models_dir: PathLike = DEFAULT_MODELS_DIR,
) -> list[dict[str, Any]]:
    """List available model artifacts, newest first (read-only)."""
    directory = Path(models_dir)
    if not directory.is_dir():
        return []
    entries = []
    for path in sorted(directory.glob("route_cascade_baseline_*.json"), reverse=True):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries.append(
            {
                "model_version": artifact.get("model_version"),
                "dataset": artifact.get("dataset"),
                "run_id": artifact.get("run_id"),
                "trained_at": artifact.get("trained_at"),
                "path": str(path),
            }
        )
    return entries


def artifact_has_no_secrets(artifact: dict[str, Any]) -> bool:
    """True when no key/value in the artifact suggests embedded secrets."""
    text = json.dumps(artifact, default=str).lower()
    markers = ("password", "secret", "token", "api_key", "apikey", "credential")
    return not any(marker in text for marker in markers)
