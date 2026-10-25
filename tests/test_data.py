"""Tests for loading, cleaning, feature engineering and splitting."""

from __future__ import annotations

import pandas as pd
import pytest

from churn import config
from churn.data import (
    add_engineered_features,
    clean_data,
    dataset_fingerprint,
    load_raw,
    prepare_dataset,
    split_dataset,
)

requires_dataset = pytest.mark.skipif(
    not config.DATA_PATH.exists(), reason="IBM dataset not downloaded"
)


@requires_dataset
def test_real_dataset_shape_and_target():
    df = prepare_dataset()
    assert len(df) == 7043
    assert set(df[config.TARGET].unique()) == {0, 1}
    assert 0.25 < df[config.TARGET].mean() < 0.28
    assert df["TotalCharges"].dtype.kind == "f"
    assert not df["TotalCharges"].isna().any()
    assert config.TARGET not in config.FEATURE_COLUMNS
    assert config.ID_COLUMN not in config.FEATURE_COLUMNS


@requires_dataset
def test_real_dataset_blank_total_charges_become_zero():
    raw = load_raw()
    blank_rows = raw["TotalCharges"].astype(str).str.strip().eq("")
    assert blank_rows.sum() == 11
    cleaned = clean_data(raw)
    zero_tenure = cleaned["tenure"] == 0
    assert (cleaned.loc[zero_tenure, "TotalCharges"] == 0).all()


def test_clean_data_maps_target_and_fills_blank_charges():
    raw = pd.DataFrame(
        {
            "customerID": ["a", "b"],
            "tenure": [0, 24],
            "MonthlyCharges": [30.0, 60.0],
            "TotalCharges": ["", "1440.0"],
            "Churn": ["No", "Yes"],
        }
    )
    cleaned = clean_data(raw)
    assert cleaned.loc[0, "TotalCharges"] == 0.0
    assert cleaned["churn"].tolist() == [0, 1]
    assert "Churn" not in cleaned.columns


def test_clean_data_rejects_unknown_target():
    raw = pd.DataFrame(
        {"customerID": ["a"], "tenure": [1], "TotalCharges": [10.0], "Churn": ["Maybe"]}
    )
    with pytest.raises(ValueError):
        clean_data(raw)


def test_clean_data_requires_target():
    raw = pd.DataFrame({"customerID": ["a"], "tenure": [1]})
    with pytest.raises(ValueError):
        clean_data(raw)


def test_engineered_features_are_consistent():
    raw = pd.DataFrame(
        {
            "customerID": ["a", "b"],
            "gender": ["Female", "Male"],
            "SeniorCitizen": [0, 1],
            "Partner": ["Yes", "No"],
            "Dependents": ["No", "Yes"],
            "tenure": [0, 24],
            "PhoneService": ["Yes", "No"],
            "MultipleLines": ["No", "No phone service"],
            "InternetService": ["Fiber optic", "No"],
            "OnlineSecurity": ["Yes", "No internet service"],
            "OnlineBackup": ["No", "No internet service"],
            "DeviceProtection": ["Yes", "No internet service"],
            "TechSupport": ["No", "No internet service"],
            "StreamingTV": ["Yes", "No internet service"],
            "StreamingMovies": ["No", "No internet service"],
            "Contract": ["Month-to-month", "Two year"],
            "PaperlessBilling": ["Yes", "No"],
            "PaymentMethod": ["Electronic check", "Credit card (automatic)"],
            "MonthlyCharges": [80.0, 20.0],
            "TotalCharges": [0.0, 480.0],
            "Churn": ["No", "No"],
        }
    )
    df = add_engineered_features(raw)
    assert df.loc[0, "NumServices"] == 4  # phone + security + device protection + streaming TV
    assert df.loc[1, "NumServices"] == 0
    assert df.loc[0, "SupportServices"] == 2
    assert df.loc[0, "StreamingServices"] == 1
    assert df["IsNewCustomer"].tolist() == [1, 0]
    assert df["HasFamily"].tolist() == [1, 1]


def test_prepare_dataset_derived_columns(synthetic_csv):
    df = prepare_dataset(synthetic_csv)
    for column in [
        "NumServices",
        "SupportServices",
        "StreamingServices",
        "IsNewCustomer",
        "HasFamily",
    ]:
        assert column in df.columns
    assert not df[config.FEATURE_COLUMNS].isna().any().any()
    assert df["NumServices"].between(0, 8).all()
    assert df["SupportServices"].between(0, 4).all()
    assert set(df["IsNewCustomer"].unique()) <= {0, 1}


def test_split_dataset_is_stratified_and_disjoint(synthetic_csv):
    df = prepare_dataset(synthetic_csv)
    X_train, X_test, y_train, y_test, ids_train, ids_test = split_dataset(df, test_size=0.2)
    assert len(X_train) + len(X_test) == len(df)
    assert len(X_test) == round(len(df) * 0.2)
    assert set(X_train.index).isdisjoint(set(X_test.index))
    assert set(ids_train).isdisjoint(set(ids_test))
    assert abs(y_train.mean() - y_test.mean()) < 0.05
    assert list(X_train.columns) == config.FEATURE_COLUMNS


def test_dataset_fingerprint(synthetic_csv):
    df = prepare_dataset(synthetic_csv)
    fingerprint = dataset_fingerprint(df)
    assert fingerprint["rows"] == len(df)
    assert fingerprint["unique_customers"] == len(df)
    assert 0 <= fingerprint["churn_rate"] <= 1


def test_load_raw_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_raw(tmp_path / "nope.csv")


def test_add_engineered_features_does_not_mutate_input():
    raw = pd.DataFrame({"tenure": [5], "MonthlyCharges": [50.0], "TotalCharges": [250.0]})
    original = raw.copy(deep=True)
    add_engineered_features(raw)
    pd.testing.assert_frame_equal(raw, original)


def test_engineered_features_handle_missing_columns():
    df = add_engineered_features(pd.DataFrame({"tenure": [10], "MonthlyCharges": [40.0]}))
    assert df.loc[0, "NumServices"] == 0
    assert df.loc[0, "HasFamily"] == 0
