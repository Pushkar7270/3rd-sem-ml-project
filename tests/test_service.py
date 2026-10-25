"""Tests for the framework-agnostic application service."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from churn.api.service import ChurnService, DataUnavailableError
from churn.artifacts import load_bundle
from tests.synthetic import high_risk_payload


@pytest.fixture(scope="module")
def service(api_paths):
    bundle = load_bundle(api_paths.bundle_path)
    scored = pd.read_csv(api_paths.scored_path)
    return ChurnService(bundle, scored=scored, raw=None)


def test_service_uses_model_specific_bands(service, api_paths):
    assert service.risk_bands[0][2] == api_paths.metadata["threshold"]
    assert service.health()["scored_customers"] == len(api_paths.scored)


def test_scored_only_customer_detail_fallback(service, api_paths):
    customer_id = str(api_paths.scored.iloc[0]["customerID"])
    result = service.customer_detail(customer_id)
    assert result is not None
    assert result["customer_id"] == customer_id
    assert 0 <= result["churn_probability"] <= 1
    assert result["recommendations"]
    assert result["top_drivers"]
    assert service.customer_detail("UNKNOWN") is None


def test_driver_flag_does_not_change_recommendations(service):
    with_drivers = service.predict_one(high_risk_payload(), include_recommendations=True)
    without_flags = service.predict_one(
        high_risk_payload(), include_drivers=False, include_recommendations=True
    )
    assert without_flags["top_drivers"] == []
    assert without_flags["top_risk_driver"] is not None
    assert without_flags["recommendations"] == with_drivers["recommendations"]
    assert without_flags["summary"] == with_drivers["summary"]
    assert without_flags["churn_probability"] == with_drivers["churn_probability"]


def test_no_flags_skips_explanations(service):
    result = service.predict_one(
        high_risk_payload(), include_drivers=False, include_recommendations=False
    )
    assert result["top_drivers"] == []
    assert result["top_risk_driver"] is None
    assert result["recommendations"] == []
    assert result["summary"].startswith(("Low", "Medium", "High"))


def test_high_risk_nan_driver_is_normalised(service, api_paths):
    scored = api_paths.scored.copy()
    scored["top_driver"] = np.nan
    service_with_nan = ChurnService(service.bundle, scored=scored, raw=None)
    body = service_with_nan.high_risk_customers(limit=5, risk_level=None)
    assert body["customers"]
    assert all(customer["top_risk_driver"] == "" for customer in body["customers"])


def test_eda_requires_raw_data(service):
    with pytest.raises(DataUnavailableError):
        service.eda_summary()


def test_high_risk_requires_scored_data(api_paths):
    bundle = load_bundle(api_paths.bundle_path)
    empty = ChurnService(bundle, scored=None, raw=None)
    with pytest.raises(DataUnavailableError):
        empty.high_risk_customers()
