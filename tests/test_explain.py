"""Tests for SHAP explanations, native importance and driver extraction."""

from __future__ import annotations

import numpy as np
import pytest

from churn import config
from churn.explain import (
    ChurnExplainer,
    explainer_kind,
    main_risk_driver,
    native_importance,
    pretty_feature_name,
)
from churn.features import build_pipeline
from tests.synthetic import high_risk_payload


def test_pretty_feature_name_maps_one_hot_columns():
    label, source, value = pretty_feature_name("Contract_Month-to-month")
    assert label == "Contract: Month-to-month"
    assert source == "Contract"
    assert value == "Month-to-month"

    label, source, value = pretty_feature_name("tenure")
    assert label == "Tenure (months)"
    assert source == "tenure"
    assert value == ""


def test_explainer_kind_detection(fitted):
    assert explainer_kind(fitted.pipeline) == "linear"
    assert explainer_kind(build_pipeline("RandomForest")) == "tree"
    assert explainer_kind(build_pipeline("KNN")) == "permutation"


def test_linear_shap_values_and_shape(fitted):
    explainer = ChurnExplainer(fitted.pipeline, fitted.background)
    result = explainer.explain(fitted.sample)
    assert result.values.shape == (len(fitted.sample), len(explainer.feature_names))
    assert np.isfinite(result.values).all()
    assert np.isfinite(result.base_value)
    assert result.transformed.shape[0] == len(fitted.sample)


def test_linear_shap_additivity(fitted):
    """SHAP must reconstruct the model's decision function exactly."""
    explainer = ChurnExplainer(fitted.pipeline, fitted.background)
    result = explainer.explain(fitted.sample)
    classifier = fitted.pipeline.named_steps["classifier"]
    expected = classifier.decision_function(result.transformed)
    reconstructed = result.base_value + result.values.sum(axis=1)
    np.testing.assert_allclose(reconstructed, expected, rtol=1e-9, atol=1e-9)


def test_top_drivers_are_sorted_and_directional(fitted):
    explainer = ChurnExplainer(fitted.pipeline, fitted.background)
    result = explainer.explain(fitted.sample)
    drivers = explainer.top_drivers(fitted.sample.iloc[0], result.values[0], k=4)
    assert len(drivers) == 4
    magnitudes = [abs(driver["contribution"]) for driver in drivers]
    assert magnitudes == sorted(magnitudes, reverse=True)
    for driver in drivers:
        assert driver["feature"]
        assert driver["label"]
        assert driver["source"]
        expected = "increases" if driver["contribution"] > 0 else "decreases"
        assert driver["impact"] == expected


def test_top_drivers_validate_value_length(fitted):
    explainer = ChurnExplainer(fitted.pipeline, fitted.background)
    with pytest.raises(ValueError):
        explainer.top_drivers(fitted.sample.iloc[0], np.zeros(3))


def test_global_importance_aggregates_sources(fitted):
    explainer = ChurnExplainer(fitted.pipeline, fitted.background)
    result = explainer.explain(fitted.sample)
    aggregated = explainer.global_importance(result, aggregate=True)
    encoded = explainer.global_importance(result, aggregate=False)
    assert aggregated
    assert encoded
    assert aggregated[0]["importance"] >= aggregated[-1]["importance"]
    assert all("source" not in row for row in aggregated)
    assert all("source" in row for row in encoded)
    assert {row["label"] for row in aggregated} <= set(config.FEATURE_LABELS.values())


def test_native_importance_for_logistic_regression(fitted):
    rows = native_importance(fitted.pipeline)
    assert rows
    assert rows[0]["kind"] == "coefficient"
    assert rows[0]["abs_value"] >= rows[-1]["abs_value"]
    assert rows[0]["direction"] in {"increases risk", "decreases risk"}


def test_native_importance_for_tree_and_distance_models(synthetic_csv):
    from churn.data import prepare_dataset, split_dataset

    df = prepare_dataset(synthetic_csv)
    X_train, _, y_train, _, _, _ = split_dataset(df)
    tree = build_pipeline("DecisionTree").fit(X_train, y_train)
    tree_rows = native_importance(tree)
    assert tree_rows[0]["kind"] == "feature_importance"
    assert tree_rows[0]["direction"] == "importance"

    knn = build_pipeline("KNN").fit(X_train, y_train)
    assert native_importance(knn) == []


def test_top_drivers_report_actual_categorical_value(fitted):
    payload = high_risk_payload()
    explainer = ChurnExplainer(fitted.pipeline, fitted.background)
    drivers, _ = explainer.explain_customer(payload, k=8)
    assert drivers
    assert any(driver["source"] in config.CATEGORICAL_FEATURES for driver in drivers)
    for driver in drivers:
        if driver["source"] in config.CATEGORICAL_FEATURES:
            assert driver["value"] == str(payload[driver["source"]])
            assert driver["label"].endswith(str(payload[driver["source"]]))

    # Dummy = 0 branch: a customer with no internet must never be shown fiber/DSL.
    no_internet = high_risk_payload()
    no_internet["InternetService"] = "No"
    for field in [
        "OnlineSecurity",
        "OnlineBackup",
        "DeviceProtection",
        "TechSupport",
        "StreamingTV",
        "StreamingMovies",
    ]:
        no_internet[field] = "No internet service"
    no_internet_drivers, _ = explainer.explain_customer(no_internet, k=30)
    assert all(
        not (driver["source"] == "InternetService" and driver["value"] in {"Fiber optic", "DSL"})
        for driver in no_internet_drivers
    )
    assert any(driver["source"] == "InternetService" for driver in no_internet_drivers)


def test_permutation_shap_fallback(synthetic_csv):
    """KNN/SVM use the model-agnostic permutation explainer."""
    from churn.data import prepare_dataset, split_dataset

    df = prepare_dataset(synthetic_csv)
    X_train, X_test, y_train, _, _, _ = split_dataset(df)
    pipeline = build_pipeline("KNN").fit(X_train, y_train)
    explainer = ChurnExplainer(pipeline, X_train.head(5), kind="permutation")
    result = explainer.explain(X_test.head(2))
    assert result.values.shape == (2, len(explainer.feature_names))
    assert np.isfinite(result.values).all()
    drivers = explainer.top_drivers(X_test.iloc[0], result.values[0], k=3)
    assert len(drivers) == 3
    expected = pipeline.named_steps["classifier"].predict_proba(result.transformed)[:, 1]
    reconstructed = result.base_value + result.values.sum(axis=1)
    np.testing.assert_allclose(reconstructed, expected, rtol=1e-6, atol=1e-6)


def test_tree_shap_explanation(synthetic_csv):
    from churn.data import prepare_dataset, split_dataset

    df = prepare_dataset(synthetic_csv)
    X_train, X_test, y_train, _, _, _ = split_dataset(df)
    pipeline = build_pipeline("RandomForest").fit(X_train, y_train)
    explainer = ChurnExplainer(pipeline, X_train.head(30))
    assert explainer.kind == "tree"
    result = explainer.explain(X_test.head(6))
    assert result.values.shape == (6, len(explainer.feature_names))
    assert np.isfinite(result.values).all()
    drivers = explainer.top_drivers(X_test.iloc[0], result.values[0], k=3)
    assert len(drivers) == 3


def test_explain_single_dict_and_customer(fitted):
    explainer = ChurnExplainer(fitted.pipeline, fitted.background)
    drivers, result = explainer.explain_customer(fitted.sample.iloc[3].to_dict(), k=2)
    assert len(drivers) == 2
    assert result.values.shape[0] == 1


def test_main_risk_driver_prefers_positive_contribution():
    drivers = [
        {"source": "tenure", "contribution": -0.9},
        {"source": "Contract", "contribution": 0.4},
        {"source": "MonthlyCharges", "contribution": 0.2},
    ]
    chosen = main_risk_driver(drivers)
    assert chosen is not None and chosen["source"] == "Contract"
    assert main_risk_driver([]) is None
    assert main_risk_driver([{"source": "tenure", "contribution": -0.5}])["source"] == "tenure"
