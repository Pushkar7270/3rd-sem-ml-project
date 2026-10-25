"""Shared fixtures: a small trained bundle and API client (no network needed)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from churn import config
from churn.api.main import create_app
from churn.artifacts import save_bundle
from churn.data import dataset_fingerprint, prepare_dataset, split_dataset
from churn.evaluate import evaluate_predictions
from churn.explain import native_importance
from churn.features import build_pipeline, feature_names
from churn.risk import (
    financial_impact,
    probability_to_risk,
    risk_band_details,
    risk_bands_for_threshold,
)
from tests.synthetic import make_synthetic_raw


@pytest.fixture(scope="session")
def api_paths(tmp_path_factory):
    root = tmp_path_factory.mktemp("api")
    raw = make_synthetic_raw()
    raw_path = root / "raw.csv"
    raw.to_csv(raw_path, index=False)

    prepared = prepare_dataset(raw_path)
    X_train, X_test, y_train, y_test, _, _ = split_dataset(prepared)
    pipeline = build_pipeline("LogisticRegression")
    pipeline.fit(X_train, y_train)

    test_metrics = evaluate_predictions(y_test, pipeline.predict_proba(X_test)[:, 1], 0.5)
    probabilities = pipeline.predict_proba(prepared[config.FEATURE_COLUMNS])[:, 1]
    threshold = 0.5
    bands = risk_bands_for_threshold(threshold)

    scored = pd.DataFrame(
        {
            "customerID": prepared[config.ID_COLUMN],
            "actual_churn": prepared[config.TARGET],
            "churn_probability": np.round(probabilities, 6),
            "risk_level": [probability_to_risk(float(p), bands) for p in probabilities],
            "predicted_churn": (probabilities >= threshold).astype(int),
            "tenure": prepared["tenure"].astype(int),
            "Contract": prepared["Contract"],
            "InternetService": prepared["InternetService"],
            "PaymentMethod": prepared["PaymentMethod"],
            "MonthlyCharges": prepared["MonthlyCharges"],
        }
    )
    scored["annual_revenue_at_risk"] = [
        financial_impact(float(m), float(p))["annual_revenue_at_risk"]
        for m, p in zip(prepared["MonthlyCharges"], probabilities, strict=True)
    ]
    scored["estimated_clv"] = [
        financial_impact(float(m), float(p))["estimated_clv"]
        for m, p in zip(prepared["MonthlyCharges"], probabilities, strict=True)
    ]
    scored["top_driver"] = "Contract: Month-to-month"
    scored["top_driver_source"] = "Contract"
    scored = scored.sort_values("churn_probability", ascending=False).reset_index(drop=True)
    scored_path = root / "scored.csv"
    scored.to_csv(scored_path, index=False)

    metadata = {
        "model_version": "v1-test",
        "trained_at": "2026-01-01T00:00:00+00:00",
        "model_name": "LogisticRegression",
        "model_display_name": config.MODEL_DISPLAY_NAMES["LogisticRegression"],
        "model_description": config.MODEL_DESCRIPTIONS["LogisticRegression"],
        "selection_metric": "roc_auc",
        "selection_reason": "test fixture",
        "cv_folds": 2,
        "threshold": threshold,
        "threshold_selection": {"method": "test", "threshold": threshold},
        "dataset": dataset_fingerprint(prepared),
        "features": {
            "raw_numeric": config.NUMERIC_FEATURES,
            "raw_categorical": config.CATEGORICAL_FEATURES,
            "encoded_count": len(feature_names(pipeline)),
        },
        "cv_results": {},
        "test_results": {"LogisticRegression": test_metrics},
        "final_test_metrics": test_metrics,
        "pr_baseline": round(float(y_test.mean()), 4),
        "global_importance": [
            {"feature": "tenure", "label": "Tenure (months)", "importance": 0.61},
            {"feature": "Contract", "label": "Contract", "importance": 0.52},
            {"feature": "MonthlyCharges", "label": "Monthly charges ($)", "importance": 0.34},
        ],
        "global_importance_encoded": [],
        "native_importance": native_importance(pipeline),
        "explainability": {
            "kind": "linear",
            "method": "LinearSHAP",
            "shap_rows": 20,
            "native_method": "Coefficients",
        },
        "risk_bands": risk_band_details(bands),
        "risk_distribution": {},
        "curves": {},
        "libraries": {"scikit-learn": "test"},
    }

    bundle = {
        "format_version": 1,
        "trained_at": metadata["trained_at"],
        "model_name": "LogisticRegression",
        "model_version": "v1-test",
        "pipeline": pipeline,
        "threshold": threshold,
        "background": X_train.head(50)[config.FEATURE_COLUMNS].copy(),
        "feature_columns": list(config.FEATURE_COLUMNS),
        "explainer_kind": "linear",
        "metadata": metadata,
    }
    bundle_path = root / "model.joblib"
    save_bundle(bundle, bundle_path)

    report_dir = root / "reports"
    (report_dir / "figures").mkdir(parents=True)
    (report_dir / "model_card.md").write_text("# Test model card\n", encoding="utf-8")

    return SimpleNamespace(
        root=root,
        raw_path=raw_path,
        scored_path=scored_path,
        bundle_path=bundle_path,
        report_dir=report_dir,
        raw=raw,
        prepared=prepared,
        scored=scored,
        pipeline=pipeline,
        metadata=metadata,
    )


@pytest.fixture()
def app(api_paths, tmp_path):
    return create_app(
        bundle_path=api_paths.bundle_path,
        scored_path=api_paths.scored_path,
        data_path=api_paths.raw_path,
        report_dir=api_paths.report_dir,
        db_path=tmp_path / "operational.db",
        mount_static=True,
    )


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def no_model_client(tmp_path):
    app = create_app(
        bundle_path=tmp_path / "missing.joblib",
        scored_path=tmp_path / "missing.csv",
        data_path=tmp_path / "missing_raw.csv",
        report_dir=tmp_path / "reports",
        mount_static=False,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def fitted(api_paths):
    """Fitted pipeline plus a raw sample for explainability tests."""
    prepared = api_paths.prepared
    sample = prepared[config.FEATURE_COLUMNS].head(12)
    background = prepared[config.FEATURE_COLUMNS].head(40)
    return SimpleNamespace(
        pipeline=api_paths.pipeline,
        sample=sample,
        background=background,
        prepared=prepared,
        metadata=api_paths.metadata,
    )


@pytest.fixture(scope="session")
def synthetic_csv(api_paths):
    return api_paths.raw_path
