"""Tests for metric computation and threshold selection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from churn.evaluate import (
    cross_validate_pipeline,
    curve_points,
    evaluate_predictions,
    flatten_cv_results,
    tune_threshold,
)
from churn.features import build_pipeline


def test_evaluate_predictions_known_values():
    y_true = [0, 0, 1, 1]
    probabilities = [0.1, 0.7, 0.4, 0.9]
    result = evaluate_predictions(y_true, probabilities, threshold=0.5)
    assert result["confusion"] == {
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 1,
        "true_positive": 1,
    }
    assert result["accuracy"] == 0.5
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5


def test_evaluate_predictions_perfect():
    result = evaluate_predictions([0, 1, 1, 0], [0.01, 0.99, 0.8, 0.2], threshold=0.5)
    assert result["roc_auc"] == 1.0
    assert result["pr_auc"] == 1.0
    assert result["brier"] == pytest.approx(0.02, abs=0.001)


def test_tune_threshold_finds_perfect_cutoff():
    y_true = np.array([0, 0, 0, 1, 1, 1])
    probabilities = np.array([0.10, 0.20, 0.30, 0.60, 0.70, 0.80])
    result = tune_threshold(y_true, probabilities)
    assert 0.2 < result["threshold"] <= 0.6
    assert result["f1"] == 1.0


def test_tune_threshold_handles_single_class_scores():
    y_true = np.array([0, 0, 1, 1])
    probabilities = np.array([0.9, 0.8, 0.2, 0.1])  # perfectly inverted
    result = tune_threshold(y_true, probabilities)
    assert set(result) == {"threshold", "f1", "precision", "recall"}
    assert 0 < result["threshold"] < 1


def test_curve_points_are_downsampled_and_bounded():
    rng = np.random.default_rng(0)
    y_true = rng.integers(0, 2, 500)
    probabilities = rng.random(500)
    points = curve_points(y_true, probabilities, max_points=40)
    assert 2 <= len(points["fpr"]) <= 40
    assert len(points["fpr"]) == len(points["tpr"])
    assert len(points["recall"]) == len(points["precision"])
    assert all(0 <= value <= 1 for value in points["fpr"] + points["tpr"])


def test_cross_validate_pipeline_reports_every_metric(synthetic_csv):
    from churn.data import prepare_dataset, split_dataset

    df = prepare_dataset(synthetic_csv)
    X_train, _, y_train, _, _, _ = split_dataset(df)
    pipeline = build_pipeline("LogisticRegression")
    results = cross_validate_pipeline(pipeline, X_train, y_train, cv_folds=2)
    assert {"roc_auc", "pr_auc", "accuracy", "precision", "recall", "f1"} <= set(results)
    for metric in ["roc_auc", "pr_auc", "f1"]:
        assert len(results[metric]["folds"]) == 2
        assert 0 <= results[metric]["mean"] <= 1
        assert results[metric]["std"] >= 0
    table = flatten_cv_results({"LR": results})
    assert table.loc["LR", "roc_auc_mean"] == results["roc_auc"]["mean"]


def test_tune_threshold_requires_labels():
    with pytest.raises(ValueError):
        tune_threshold(pd.Series(dtype=int), np.array([]))
