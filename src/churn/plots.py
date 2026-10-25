"""Matplotlib figures for EDA, model comparison and explainability.

All functions are pure (input data -> file on disk) so they can be reused from
notebooks or the training CLI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss

from . import config
from .explain import ShapResult, pretty_feature_name

logger = logging.getLogger(__name__)

PALETTE = {
    "LogisticRegression": "#1f77b4",
    "DecisionTree": "#ff7f0e",
    "RandomForest": "#2ca02c",
    "XGBoost": "#d62728",
    "KNN": "#9467bd",
    "SVM": "#8c564b",
}

plt.rcParams.update(
    {
        "figure.dpi": 130,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
    }
)


def _save(fig: plt.Figure, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    logger.info("Saved figure %s", path)
    return path


def _display(name: str) -> str:
    return config.MODEL_DISPLAY_NAMES.get(name, name)


# --------------------------------------------------------------------------- #
# Model comparison
# --------------------------------------------------------------------------- #
def plot_model_comparison(
    results: dict[str, dict[str, dict[str, float]]], path: str | Path
) -> Path:
    """Grouped horizontal bars: 5-fold CV mean with standard-deviation error bars."""
    rows = []
    for name, metrics in results.items():
        rows.append(
            {
                "model": _display(name),
                "roc_auc": metrics["roc_auc"]["mean"],
                "roc_auc_std": metrics["roc_auc"]["std"],
                "pr_auc": metrics["pr_auc"]["mean"],
                "pr_auc_std": metrics["pr_auc"]["std"],
                "f1": metrics["f1"]["mean"],
                "f1_std": metrics["f1"]["std"],
            }
        )
    frame = pd.DataFrame(rows).sort_values("roc_auc")
    y = np.arange(len(frame))
    height = 0.26

    fig, ax = plt.subplots(figsize=(9, 0.65 * len(frame) + 2.2))
    ax.barh(
        y + height,
        frame["roc_auc"],
        height,
        xerr=frame["roc_auc_std"],
        label="ROC-AUC",
        color="#1f4e79",
        capsize=3,
    )
    ax.barh(
        y,
        frame["pr_auc"],
        height,
        xerr=frame["pr_auc_std"],
        label="PR-AUC",
        color="#2e8b8b",
        capsize=3,
    )
    ax.barh(
        y - height,
        frame["f1"],
        height,
        xerr=frame["f1_std"],
        label="F1",
        color="#e0a458",
        capsize=3,
    )
    ax.set_yticks(y)
    ax.set_yticklabels(frame["model"])
    ax.set_xlabel("5-fold cross-validated score (mean +/- std)")
    ax.set_xlim(0, 1)
    ax.set_title("Model comparison on the training set")
    ax.legend(loc="lower right", ncol=3)
    for i, value in enumerate(frame["roc_auc"]):
        ax.text(value + 0.01, i + height, f"{value:.3f}", va="center", fontsize=7)
    return _save(fig, path)


def plot_roc_curves(curves: dict[str, dict[str, Any]], path: str | Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    for name, curve in curves.items():
        ax.plot(
            curve["fpr"],
            curve["tpr"],
            label=f"{_display(name)} (AUC {curve['auc']:.3f})",
            color=PALETTE.get(name),
            linewidth=1.8,
        )
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, alpha=0.5)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("ROC curves on the held-out test set")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.01)
    return _save(fig, path)


def plot_pr_curves(curves: dict[str, dict[str, Any]], path: str | Path, baseline: float) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    for name, curve in curves.items():
        ax.plot(
            curve["recall"],
            curve["precision"],
            label=f"{_display(name)} (AP {curve['ap']:.3f})",
            color=PALETTE.get(name),
            linewidth=1.8,
        )
    ax.axhline(
        baseline,
        color="k",
        linestyle="--",
        linewidth=1,
        alpha=0.5,
        label=f"Baseline ({baseline:.2f})",
    )
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-recall curves on the held-out test set")
    ax.legend(loc="lower left", fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.01)
    return _save(fig, path)


def plot_threshold_analysis(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    selected_threshold: float,
    path: str | Path,
) -> Path:
    from sklearn.metrics import f1_score, precision_score, recall_score

    thresholds = np.linspace(0.05, 0.95, 91)
    precision = [precision_score(y_true, probabilities >= t, zero_division=0) for t in thresholds]
    recall = [recall_score(y_true, probabilities >= t, zero_division=0) for t in thresholds]
    f1 = [f1_score(y_true, probabilities >= t, zero_division=0) for t in thresholds]

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.plot(thresholds, precision, label="Precision", color="#1f4e79")
    ax.plot(thresholds, recall, label="Recall", color="#c62828")
    ax.plot(thresholds, f1, label="F1", color="#2e7d32", linewidth=2)
    ax.axvline(
        selected_threshold,
        color="#6a1b9a",
        linestyle="--",
        linewidth=1.4,
        label=f"Selected threshold ({selected_threshold:.2f})",
    )
    ax.set_xlabel("Decision threshold")
    ax.set_ylabel("Score")
    ax.set_title("Threshold selection on out-of-fold predictions")
    ax.legend(loc="center right", fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    return _save(fig, path)


def plot_confusion_matrix(confusion: dict[str, int], path: str | Path, title: str) -> Path:
    matrix = np.array(
        [
            [confusion["true_negative"], confusion["false_positive"]],
            [confusion["false_negative"], confusion["true_positive"]],
        ]
    )
    fig, ax = plt.subplots(figsize=(4.6, 4.0))
    image = ax.imshow(matrix, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(
                j,
                i,
                f"{matrix[i, j]:,}",
                ha="center",
                va="center",
                color="white" if matrix[i, j] > matrix.max() / 2 else "#1f2933",
                fontsize=14,
                fontweight="bold",
            )
    ax.set_xticks([0, 1], ["Predicted stay", "Predicted churn"])
    ax.set_yticks([0, 1], ["Actual stay", "Actual churn"])
    ax.set_title(title)
    ax.grid(False)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    return _save(fig, path)


def plot_calibration(data: dict[str, tuple[np.ndarray, np.ndarray]], path: str | Path) -> Path:
    """Reliability diagram comparing predicted vs observed churn rates."""
    fig, ax = plt.subplots(figsize=(6.2, 5.0))
    for name, (y_true, probabilities) in data.items():
        if len(np.unique(y_true)) < 2:
            continue
        fraction_positive, mean_predicted = calibration_curve(
            y_true, probabilities, n_bins=10, strategy="quantile"
        )
        brier = brier_score_loss(y_true, probabilities)
        ax.plot(
            mean_predicted,
            fraction_positive,
            marker="o",
            markersize=3.5,
            linewidth=1.5,
            label=f"{_display(name)} (Brier {brier:.3f})",
            color=PALETTE.get(name),
        )
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, alpha=0.5, label="Perfect calibration")
    ax.set_xlabel("Mean predicted churn probability")
    ax.set_ylabel("Observed churn rate")
    ax.set_title("Calibration on the held-out test set")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    return _save(fig, path)


# --------------------------------------------------------------------------- #
# Explainability
# --------------------------------------------------------------------------- #
def plot_native_importance(
    rows: list[dict[str, Any]], path: str | Path, title: str, *, top_n: int = 15
) -> Path:
    rows = rows[:top_n]
    if not rows:
        return Path(path)
    labels = [row["label"] for row in rows][::-1]
    values = [float(row.get("value", row.get("importance", 0.0))) for row in rows][::-1]
    colors = ["#c62828" if v >= 0 else "#1565c0" for v in values]

    fig, ax = plt.subplots(figsize=(8.0, max(3.2, 0.36 * len(rows) + 1.4)))
    ax.barh(labels, values, color=colors)
    ax.axvline(0, color="#37474f", linewidth=0.8)
    ax.set_xlabel(
        "Signed contribution (log-odds)" if "coefficient" in title.lower() else "Importance"
    )
    ax.set_title(title)
    return _save(fig, path)


def plot_shap_beeswarm(result: ShapResult, path: str | Path, *, max_display: int = 15) -> Path:
    import shap

    if len(result.values) < 2:
        return Path(path)
    labels = [pretty_feature_name(name)[0] for name in result.feature_names]
    fig = plt.figure(figsize=(9.0, 6.4))
    shap.summary_plot(
        result.values,
        result.transformed,
        feature_names=labels,
        show=False,
        max_display=max_display,
        plot_size=None,
    )
    plt.title("SHAP summary: impact of each feature on churn probability")
    return _save(fig, path)


def plot_shap_bar(rows: list[dict[str, Any]], path: str | Path, *, top_n: int = 15) -> Path:
    rows = rows[:top_n][::-1]
    if not rows:
        return Path(path)
    labels = [row["label"] for row in rows]
    values = [row["importance"] for row in rows]
    fig, ax = plt.subplots(figsize=(8.0, max(3.2, 0.36 * len(rows) + 1.4)))
    ax.barh(labels, values, color="#2e8b8b")
    ax.set_xlabel("Mean |SHAP value| (average impact on model output)")
    ax.set_title("Key churn drivers (SHAP, aggregated by source feature)")
    return _save(fig, path)


def plot_local_explanation(
    drivers: list[dict[str, Any]], path: str | Path, title: str = "Why this customer is at risk"
) -> Path:
    rows = sorted(drivers, key=lambda d: abs(d["contribution"]))[-10:]
    if not rows:
        return Path(path)
    labels = [
        f"{d['label']} = {d['value']}" if d.get("value") is not None else d["label"] for d in rows
    ]
    values = [d["contribution"] for d in rows]
    colors = ["#c62828" if v > 0 else "#1565c0" for v in values]

    fig, ax = plt.subplots(figsize=(8.4, max(3.0, 0.42 * len(rows) + 1.5)))
    ax.barh(labels, values, color=colors)
    ax.axvline(0, color="#37474f", linewidth=0.8)
    ax.set_xlabel("SHAP contribution (positive = increases churn risk)")
    ax.set_title(title)
    return _save(fig, path)


# --------------------------------------------------------------------------- #
# EDA and risk
# --------------------------------------------------------------------------- #
def plot_churn_segments(df: pd.DataFrame, path: str | Path) -> Path:
    frame = df.copy()
    frame["TenureBucket"] = pd.cut(
        frame["tenure"],
        bins=[-0.1, 6, 12, 24, 48, np.inf],
        labels=["0-6", "7-12", "13-24", "25-48", "49+"],
    )
    panels = [
        ("Contract", "By contract type"),
        ("InternetService", "By internet service"),
        ("PaymentMethod", "By payment method"),
        ("TenureBucket", "By tenure (months)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2))
    for ax, (column, title) in zip(axes.ravel(), panels, strict=True):
        rates = frame.groupby(column, observed=True)[config.TARGET].mean().sort_values()
        counts = frame.groupby(column, observed=True)[config.TARGET].size()
        bars = ax.bar(range(len(rates)), rates.values, color="#2e8b8b")
        ax.set_xticks(range(len(rates)))
        ax.set_xticklabels([str(v) for v in rates.index], rotation=18, ha="right")
        ax.set_ylim(0, max(0.55, rates.max() * 1.25))
        ax.set_ylabel("Churn rate")
        ax.set_title(title)
        for bar, (rate, count) in zip(
            bars, zip(rates.values, counts.reindex(rates.index), strict=True), strict=True
        ):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.008,
                f"{rate:.0%}\n(n={count:,})",
                ha="center",
                va="bottom",
                fontsize=7,
            )
    fig.suptitle("Churn rate by customer segment", fontsize=13, fontweight="bold", y=1.01)
    return _save(fig, path)


def plot_risk_distribution(
    probabilities: np.ndarray,
    path: str | Path,
    *,
    bands: tuple[tuple[str, float, float], ...] | None = None,
) -> Path:
    bands = bands or config.RISK_BANDS
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    ax.hist(probabilities, bins=35, color="#546e7a", edgecolor="white", linewidth=0.4)
    for name, lower, upper in bands:
        ax.axvspan(lower, min(upper, 1.0), color=config.RISK_COLORS[name], alpha=0.10)
        ax.axvline(lower, color=config.RISK_COLORS[name], linestyle="--", linewidth=1)
    handles = [
        Patch(facecolor=config.RISK_COLORS[name], alpha=0.25, label=f"{name.title()} risk")
        for name, _, _ in bands
    ]
    ax.legend(handles=handles, loc="upper right")
    ax.set_xlabel("Predicted churn probability")
    ax.set_ylabel("Number of customers")
    ax.set_title("Distribution of churn risk scores")
    ax.set_xlim(0, 1)
    return _save(fig, path)


def plot_global_importance_comparison(
    native_rows: list[dict[str, Any]],
    shap_rows: list[dict[str, Any]],
    path: str | Path,
) -> Path:
    """Side-by-side native importance vs SHAP to show method agreement."""
    if not native_rows or not shap_rows:
        return Path(path)
    native = {row["source"]: row["abs_value"] for row in native_rows}
    shap_map = {row["feature"]: row["importance"] for row in shap_rows}
    common = sorted(set(native) & set(shap_map), key=lambda k: -shap_map[k])[:12]
    if not common:
        return Path(path)
    labels = [config.FEATURE_LABELS.get(k, k) for k in common][::-1]
    native_values = np.array([native[k] for k in common][::-1], dtype=float)
    shap_values = np.array([shap_map[k] for k in common][::-1], dtype=float)
    native_values /= native_values.max() or 1.0
    shap_values /= shap_values.max() or 1.0
    y = np.arange(len(common))
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    ax.barh(y + 0.2, native_values, 0.38, label="Native importance (normalised)", color="#ff8f00")
    ax.barh(y - 0.2, shap_values, 0.38, label="Mean |SHAP| (normalised)", color="#2e8b8b")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Normalised importance")
    ax.set_title("Native feature importance vs SHAP agreement")
    ax.legend(loc="lower right")
    return _save(fig, path)
