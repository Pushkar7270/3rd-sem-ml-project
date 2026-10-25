"""Tests for preprocessing, pipelines and feature marshalling."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from churn import config
from churn.data import prepare_dataset, split_dataset
from churn.features import (
    build_all_pipelines,
    build_pipeline,
    feature_names,
    raw_features_to_frame,
)
from tests.synthetic import high_risk_payload


@pytest.fixture(scope="module")
def split(synthetic_csv):
    df = prepare_dataset(synthetic_csv)
    return split_dataset(df)


def test_build_all_pipelines_covers_registry():
    pipelines = build_all_pipelines()
    assert set(pipelines) == set(config.MODEL_NAMES)
    for pipeline in pipelines.values():
        assert set(pipeline.named_steps) == {"preprocessor", "classifier"}


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="Unknown model"):
        build_pipeline("MagicNet")


@pytest.mark.parametrize("model_name", config.MODEL_NAMES)
def test_each_model_fits_and_predicts(model_name, split):
    X_train, X_test, y_train, y_test, _, _ = split
    pipeline = build_pipeline(model_name)
    pipeline.fit(X_train, y_train)
    probabilities = pipeline.predict_proba(X_test)[:, 1]
    assert probabilities.shape == (len(X_test),)
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0) & (probabilities <= 1)).all()
    predictions = pipeline.predict(X_test)
    assert set(np.unique(predictions)) <= {0, 1}


def test_preprocessor_imputes_and_scales(split):
    X_train, X_test, y_train, _, _, _ = split
    pipeline = build_pipeline("LogisticRegression")
    pipeline.fit(X_train, y_train)
    preprocessor = pipeline.named_steps["preprocessor"]
    transformed = preprocessor.transform(X_test)
    assert np.isfinite(transformed).all()
    assert transformed.shape[1] == len(feature_names(pipeline))
    assert len(feature_names(pipeline)) > len(config.FEATURE_COLUMNS)


def test_unseen_category_is_ignored(split):
    X_train, _, y_train, _, _, _ = split
    # Remove one contract type from training, then score it.
    mask = X_train["Contract"] != "Two year"
    pipeline = build_pipeline("LogisticRegression")
    pipeline.fit(X_train[mask], y_train[mask])
    record = high_risk_payload()
    record["Contract"] = "Two year"
    frame = raw_features_to_frame(record)
    probability = pipeline.predict_proba(frame)[0, 1]
    assert 0.0 <= probability <= 1.0

    names = feature_names(pipeline)
    assert "Contract_Two year" not in names
    transformed = pipeline.named_steps["preprocessor"].transform(frame)[0]
    contract_values = [
        value
        for name, value in zip(names, transformed, strict=True)
        if name.startswith("Contract_")
    ]
    assert contract_values and all(value == 0 for value in contract_values)


def test_feature_names_are_unique(split):
    X_train, _, y_train, _, _, _ = split
    pipeline = build_pipeline("DecisionTree")
    pipeline.fit(X_train, y_train)
    names = feature_names(pipeline)
    assert len(names) == len(set(names))


def test_raw_features_to_frame_engineers_single_dict():
    record = high_risk_payload()
    frame = raw_features_to_frame(record)
    assert len(frame) == 1
    assert list(frame.columns) == config.FEATURE_COLUMNS
    assert frame.loc[0, "NumServices"] == 4  # phone + multiple lines + streaming TV + movies
    assert frame.loc[0, "SupportServices"] == 0
    assert frame.loc[0, "StreamingServices"] == 2
    assert frame.loc[0, "IsNewCustomer"] == 1
    assert frame.loc[0, "HasFamily"] == 0


def test_raw_features_to_frame_batch_and_missing_fields():
    frames = raw_features_to_frame([{"tenure": 5, "MonthlyCharges": 50.0}])
    assert len(frames) == 1
    assert pd.isna(frames.loc[0, "Contract"])
    empty = raw_features_to_frame([])
    assert empty.empty


def test_new_customer_flags_and_charge_columns():
    frame = raw_features_to_frame({"tenure": 0, "MonthlyCharges": 42.5, "TotalCharges": 0.0})
    assert frame.loc[0, "IsNewCustomer"] == 1
    assert frame.loc[0, "TotalCharges"] == 0
    assert "AvgMonthlyCharges" not in frame.columns  # ratio features were removed
