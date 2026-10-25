"""Integration test for the full training pipeline (fast settings)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from churn import config
from churn.artifacts import load_bundle, read_metadata
from churn.train import train


@pytest.fixture(scope="module")
def training_outputs(synthetic_csv, tmp_path_factory):
    root = tmp_path_factory.mktemp("training")
    result = train(
        synthetic_csv,
        artifact_dir=root / "artifacts",
        report_dir=root / "reports",
        processed_dir=root / "processed",
        cv_folds=2,
        models=["LogisticRegression", "DecisionTree"],
        make_figures=False,
        shap_sample=20,
    )
    return root, result


def test_training_writes_bundle_and_metadata(training_outputs):
    root, result = training_outputs
    assert (root / "artifacts" / "model.joblib").exists()
    assert (root / "artifacts" / "metadata.json").exists()
    assert (root / "processed" / "scored_customers.csv").exists()
    assert (root / "reports" / "model_card.md").exists()
    assert (root / "reports" / "cv_results.csv").exists()
    assert (root / "reports" / "test_results.csv").exists()
    assert (root / "reports" / "metrics.json").exists()

    bundle = load_bundle(root / "artifacts" / "model.joblib")
    assert bundle["model_name"] == result["model_name"]
    assert bundle["metadata"]["model_name"] == result["model_name"]
    assert bundle["feature_columns"] == config.FEATURE_COLUMNS
    assert "preprocessor" in bundle["pipeline"].named_steps


def test_training_compares_models_and_selects_best_cv(training_outputs):
    root, result = training_outputs
    metadata = read_metadata(root / "artifacts" / "metadata.json")
    cv = metadata["cv_results"]
    assert set(cv) == {"LogisticRegression", "DecisionTree"}
    assert all(len(metrics["roc_auc"]["folds"]) == 2 for metrics in cv.values())
    best = max(
        cv,
        key=lambda name: (
            cv[name]["roc_auc"]["mean"],
            cv[name]["pr_auc"]["mean"],
            cv[name]["f1"]["mean"],
        ),
    )
    assert metadata["model_name"] == best
    assert result["model_name"] == best
    assert metadata["selection_metric"] == "roc_auc"


def test_training_metadata_is_internally_consistent(training_outputs):
    root, result = training_outputs
    metadata = read_metadata(root / "artifacts" / "metadata.json")
    assert metadata["cv_folds"] == 2
    assert 0 < metadata["threshold"] < 1
    assert metadata["threshold_selection"]["method"].startswith("F1")
    assert metadata["cv_results"]["LogisticRegression"]["roc_auc"]["mean"] > 0.5
    assert metadata["final_test_metrics"]["roc_auc"] > 0.5

    confusion = metadata["final_test_metrics"]["confusion"]
    assert sum(confusion.values()) == metadata["dataset"]["test_rows"]
    assert set(metadata["risk_distribution"]) <= {"low", "medium", "high"}
    assert sum(metadata["risk_distribution"].values()) == metadata["dataset"]["rows"]
    assert metadata["explainability"]["kind"] == "linear"
    assert metadata["global_importance"]
    assert metadata["libraries"]["scikit-learn"]

    # Risk bands must not contradict the operating threshold.
    bands = metadata["risk_bands"]
    assert bands[0]["max_probability"] == metadata["threshold"]
    assert bands[0]["min_probability"] == 0.0
    assert bands[-1]["max_probability"] == 1.0


def test_training_scores_every_customer(training_outputs):
    root, result = training_outputs
    scored = pd.read_csv(root / "processed" / "scored_customers.csv")
    assert len(scored) == result["metadata"]["dataset"]["rows"]
    assert scored["churn_probability"].between(0, 1).all()
    assert set(scored["risk_level"]) <= {"low", "medium", "high"}
    assert scored["annual_revenue_at_risk"].ge(0).all()
    assert scored["customerID"].is_unique
    assert not ((scored["risk_level"] == "low") & (scored["predicted_churn"] == 1)).any()

    # The retention team only receives per-customer drivers for medium/high risk,
    # and the work queue must actually be populated.
    medium_high = scored[scored["risk_level"].isin(["medium", "high"])]
    drivers = medium_high["top_driver"].fillna("").astype(str)
    sources = medium_high["top_driver_source"].fillna("").astype(str)
    assert (drivers.str.len() > 0).all()
    assert (sources.str.len() > 0).all()


def test_training_result_can_score_a_customer(training_outputs):
    root, result = training_outputs
    bundle = load_bundle(root / "artifacts" / "model.joblib")
    from churn.features import raw_features_to_frame

    frame = raw_features_to_frame({"tenure": 1, "MonthlyCharges": 90.0, "TotalCharges": 90.0})
    probability = bundle["pipeline"].predict_proba(frame)[0, 1]
    assert 0 <= probability <= 1


def test_training_rejects_unknown_model(synthetic_csv, tmp_path):
    with pytest.raises(ValueError):
        train(
            synthetic_csv,
            artifact_dir=tmp_path / "a",
            report_dir=tmp_path / "r",
            processed_dir=tmp_path / "p",
            models=["MagicNet"],
            make_figures=False,
        )


def test_training_generates_figures(synthetic_csv, tmp_path):
    result = train(
        synthetic_csv,
        artifact_dir=tmp_path / "artifacts",
        report_dir=tmp_path / "reports",
        processed_dir=tmp_path / "processed",
        cv_folds=2,
        models=["LogisticRegression"],
        make_figures=True,
        shap_sample=15,
    )
    figures = sorted((tmp_path / "reports" / "figures").glob("*.png"))
    assert len(figures) == 13
    assert all(path.stat().st_size > 0 for path in figures)
    assert (tmp_path / "reports" / "model_card.md").exists()
    assert len(result["artifacts"]["figures"]) == 13


# Optional test against the real artifacts produced by the repository training run.
@pytest.mark.skipif(not config.MODEL_PATH.exists(), reason="Repository artifacts not trained")
def test_repository_artifacts_are_usable():
    bundle = load_bundle(config.MODEL_PATH)
    metadata = read_metadata()
    assert bundle["model_name"] in config.MODEL_NAMES
    assert metadata["model_name"] == bundle["model_name"]
    assert config.SCORED_CUSTOMERS_PATH.exists()

    # The shipped model must reflect the advertised six-model, five-fold protocol.
    assert set(metadata["cv_results"]) == set(config.MODEL_NAMES)
    assert all(len(m["roc_auc"]["folds"]) == 5 for m in metadata["cv_results"].values())
    best = max(
        metadata["cv_results"],
        key=lambda n: metadata["cv_results"][n]["roc_auc"]["mean"],
    )
    assert metadata["model_name"] == best
    assert metadata["risk_bands"][0]["max_probability"] == metadata["threshold"]

    scored = pd.read_csv(config.SCORED_CUSTOMERS_PATH)
    assert len(scored) == 7043
    assert abs(scored["churn_probability"].mean() - 0.2654) < 0.10
    assert not ((scored["risk_level"] == "low") & (scored["predicted_churn"] == 1)).any()
    high = scored[scored["risk_level"] == "high"]
    assert (high["top_driver"].fillna("").astype(str).str.len() > 0).mean() > 0.9
    assert json.dumps(metadata)  # serialisable
