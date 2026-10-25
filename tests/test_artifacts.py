"""Tests for artifact persistence and validation."""

from __future__ import annotations

import joblib
import pytest

from churn.artifacts import (
    ModelNotTrainedError,
    load_bundle,
    read_metadata,
    save_bundle,
    write_metadata,
)


def _bundle(**overrides):
    bundle = {
        "format_version": 1,
        "trained_at": "2026-01-01T00:00:00+00:00",
        "model_name": "TestModel",
        "model_version": "v1-test",
        "pipeline": "not-a-real-pipeline",
        "threshold": 0.5,
        "background": None,
        "feature_columns": [],
        "metadata": {"model_name": "TestModel"},
    }
    bundle.update(overrides)
    return bundle


def test_save_and_load_bundle(tmp_path):
    path = save_bundle(_bundle(), tmp_path / "model.joblib")
    loaded = load_bundle(path)
    assert loaded["model_name"] == "TestModel"
    assert loaded["threshold"] == 0.5
    assert not list(tmp_path.glob("*.tmp"))


def test_trained_atomic_file_is_replaced(tmp_path):
    path = tmp_path / "model.joblib"
    save_bundle(_bundle(threshold=0.4), path)
    save_bundle(_bundle(threshold=0.7), path)
    assert load_bundle(path)["threshold"] == 0.7


def test_save_bundle_validates_required_keys(tmp_path):
    with pytest.raises(ValueError, match="missing required keys"):
        save_bundle({"format_version": 1}, tmp_path / "bad.joblib")


def test_load_missing_bundle_raises_helpful_error(tmp_path):
    with pytest.raises(ModelNotTrainedError, match="trained model"):
        load_bundle(tmp_path / "missing.joblib")


def test_load_rejects_incompatible_format(tmp_path):
    path = tmp_path / "old.joblib"
    joblib.dump(_bundle(format_version=0), path)
    with pytest.raises(ValueError, match="incompatible"):
        load_bundle(path)


def test_load_rejects_non_dict(tmp_path):
    path = tmp_path / "list.joblib"
    joblib.dump(["not", "a", "bundle"], path)
    with pytest.raises(ValueError, match="Invalid model bundle"):
        load_bundle(path)


def test_load_rejects_bundle_missing_pipeline(tmp_path):
    path = tmp_path / "no-pipeline.joblib"
    bundle = _bundle()
    del bundle["pipeline"]
    joblib.dump(bundle, path)
    with pytest.raises(ValueError, match="pipeline"):
        load_bundle(path)


def test_metadata_roundtrip(tmp_path):
    path = write_metadata({"model_name": "Test", "nested": {"a": 1}}, tmp_path / "m.json")
    assert read_metadata(path)["nested"]["a"] == 1


def test_missing_metadata_raises(tmp_path):
    with pytest.raises(ModelNotTrainedError):
        read_metadata(tmp_path / "missing.json")
