"""Tests for the model registry and estimator configuration."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from churn import config
from churn.data import prepare_dataset, split_dataset
from churn.features import build_estimator, build_pipeline, feature_names


def _supports_probability(estimator) -> bool:
    return hasattr(estimator, "predict_proba")


def test_registry_is_complete():
    assert config.MODEL_NAMES == [
        "LogisticRegression",
        "DecisionTree",
        "RandomForest",
        "XGBoost",
        "KNN",
        "SVM",
    ]
    assert set(config.MODEL_DISPLAY_NAMES) == set(config.MODEL_NAMES)


def test_build_estimator_returns_probability_estimators():
    for name in config.MODEL_NAMES:
        estimator = build_estimator(name)
        assert _supports_probability(estimator), name


def test_every_estimator_is_deterministic():
    X = pd.DataFrame(
        {
            "a": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0] * 10,
            "b": [1, 0, 1, 0, 1, 0] * 10,
        }
    )
    y = pd.Series([0, 1, 0, 1, 0, 1] * 10)
    for name in config.MODEL_NAMES:
        first = build_estimator(name).fit(X, y)
        second = build_estimator(name).fit(X, y)
        np.testing.assert_allclose(
            first.predict_proba(X), second.predict_proba(X), rtol=1e-8, atol=1e-8
        )


def test_model_metadata_matches_registry():
    for name in config.MODEL_NAMES:
        estimator = build_estimator(name)
        assert config.MODEL_DISPLAY_NAMES[name]
        assert config.MODEL_DESCRIPTIONS[name]
        assert _supports_probability(estimator)


def test_logistic_coefficients_align_with_features(synthetic_csv):
    df = prepare_dataset(synthetic_csv)
    X_train, _, y_train, _, _, _ = split_dataset(df)
    pipeline = build_pipeline("LogisticRegression").fit(X_train, y_train)
    coefficients = pipeline.named_steps["classifier"].coef_
    assert coefficients.shape == (1, len(feature_names(pipeline)))
    assert np.isfinite(coefficients).all()


def test_pipeline_clone_has_no_fitted_state(synthetic_csv):
    from sklearn.base import clone
    from sklearn.exceptions import NotFittedError

    pipeline = build_pipeline("RandomForest")
    cloned = clone(pipeline)
    assert isinstance(cloned, Pipeline)
    with pytest.raises(NotFittedError):
        cloned.predict(pd.DataFrame([{"tenure": 1}]))
