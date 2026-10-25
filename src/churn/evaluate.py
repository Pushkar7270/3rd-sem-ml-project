"""Model evaluation, cross-validation and decision-threshold selection."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.pipeline import Pipeline

from . import config


def evaluate_predictions(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, float | int | dict[str, int]]:
    """Classification metrics for a probability vector at a fixed threshold."""
    y_true = np.asarray(y_true).astype(int)
    probabilities = np.asarray(probabilities, dtype=float)
    y_pred = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

    return {
        "threshold": round(float(threshold), 4),
        "roc_auc": round(float(roc_auc_score(y_true, probabilities)), 4),
        "pr_auc": round(float(average_precision_score(y_true, probabilities)), 4),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "brier": round(float(brier_score_loss(y_true, probabilities)), 4),
        "log_loss": round(float(log_loss(y_true, probabilities, labels=[0, 1])), 4),
        "confusion": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
        "support": {
            "total": int(len(y_true)),
            "actual_churn": int(y_true.sum()),
            "predicted_churn": int(y_pred.sum()),
        },
    }


def cross_validate_pipeline(
    pipeline: Pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    *,
    cv_folds: int = config.CV_FOLDS,
    random_state: int = config.RANDOM_STATE,
) -> dict[str, dict[str, float]]:
    """Stratified k-fold CV returning mean/std for every configured metric."""
    cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
    scores = cross_validate(
        clone(pipeline),
        X,
        y,
        cv=cv,
        scoring=config.SCORING_METRICS,
        n_jobs=1,
        return_train_score=False,
        error_score="raise",
    )
    results: dict[str, dict[str, float]] = {}
    for metric in config.SCORING_METRICS:
        values = np.asarray(scores[f"test_{metric}"], dtype=float)
        results[metric] = {
            "mean": round(float(values.mean()), 4),
            "std": round(float(values.std(ddof=0)), 4),
            "folds": [round(float(v), 4) for v in values],
        }
    results["fit_time_seconds"] = {
        "mean": round(float(np.mean(scores["fit_time"])), 3),
        "std": round(float(np.std(scores["fit_time"])), 3),
        "folds": [round(float(v), 3) for v in scores["fit_time"]],
    }
    return results


def tune_threshold(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    *,
    min_threshold: float = 0.10,
    max_threshold: float = 0.90,
) -> dict[str, float]:
    """Choose the probability cut-off that maximises F1 on out-of-fold scores.

    F1 balances missed churners against wasted retention offers.  The grid
    combines a uniform sweep with probability quantiles so that sparse regions
    are still considered.
    """
    y_true = np.asarray(y_true).astype(int)
    probabilities = np.asarray(probabilities, dtype=float)
    if len(y_true) != len(probabilities):
        raise ValueError("y_true and probabilities must have the same length")
    if len(y_true) == 0:
        raise ValueError("At least one observation is required")
    uniform = np.linspace(min_threshold, max_threshold, 81)
    quantiles = np.quantile(probabilities, np.linspace(0.05, 0.95, 19))
    grid = np.unique(np.clip(np.concatenate([uniform, quantiles]), 0.01, 0.99))

    best_threshold, best_f1, best_precision, best_recall = 0.5, -1.0, 0.0, 0.0
    for threshold in grid:
        predictions = (probabilities >= threshold).astype(int)
        f1 = f1_score(y_true, predictions, zero_division=0)
        if f1 > best_f1:
            best_threshold = float(threshold)
            best_f1 = float(f1)
            best_precision = float(precision_score(y_true, predictions, zero_division=0))
            best_recall = float(recall_score(y_true, predictions, zero_division=0))
    return {
        "threshold": round(best_threshold, 4),
        "f1": round(best_f1, 4),
        "precision": round(best_precision, 4),
        "recall": round(best_recall, 4),
    }


def curve_points(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    *,
    max_points: int = 60,
) -> dict[str, list[float]]:
    """Downsampled ROC and PR points for JSON/API driven charts."""
    y_true = np.asarray(y_true).astype(int)
    probabilities = np.asarray(probabilities, dtype=float)
    fpr, tpr, _ = roc_curve(y_true, probabilities)
    precision, recall, _ = precision_recall_curve(y_true, probabilities)

    def _sample(x: np.ndarray, y: np.ndarray) -> tuple[list[float], list[float]]:
        if len(x) > max_points:
            idx = np.unique(np.linspace(0, len(x) - 1, max_points).astype(int))
            x, y = x[idx], y[idx]
        return [round(float(v), 4) for v in x], [round(float(v), 4) for v in y]

    fpr_s, tpr_s = _sample(fpr, tpr)
    recall_s, precision_s = _sample(recall, precision)
    return {"fpr": fpr_s, "tpr": tpr_s, "recall": recall_s, "precision": precision_s}


def flatten_cv_results(results: dict[str, dict[str, dict[str, float]]]) -> pd.DataFrame:
    """One row per model, columns ``metric_mean`` / ``metric_std``."""
    rows = []
    for model_name, metrics in results.items():
        row: dict[str, float | str] = {"model": model_name}
        for metric, summary in metrics.items():
            row[f"{metric}_mean"] = summary["mean"]
            row[f"{metric}_std"] = summary["std"]
        rows.append(row)
    return pd.DataFrame(rows).set_index("model")


def cv_summary_table(results: dict[str, dict[str, dict[str, float]]]) -> pd.DataFrame:
    """Compact table for the model card and console output."""
    rows = []
    for model_name, metrics in results.items():
        rows.append(
            {
                "Model": config.MODEL_DISPLAY_NAMES.get(model_name, model_name),
                "ROC-AUC": f"{metrics['roc_auc']['mean']:.4f} +/- {metrics['roc_auc']['std']:.3f}",
                "PR-AUC": f"{metrics['pr_auc']['mean']:.4f} +/- {metrics['pr_auc']['std']:.3f}",
                "F1": f"{metrics['f1']['mean']:.4f} +/- {metrics['f1']['std']:.3f}",
                "Recall": f"{metrics['recall']['mean']:.4f} +/- {metrics['recall']['std']:.3f}",
                "Fit (s)": f"{metrics['fit_time_seconds']['mean']:.2f}",
            }
        )
    return pd.DataFrame(rows).sort_values("ROC-AUC", ascending=False)
