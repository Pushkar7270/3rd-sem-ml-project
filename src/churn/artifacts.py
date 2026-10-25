"""Persistence for the trained model bundle."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import joblib

from . import config

logger = logging.getLogger(__name__)

BUNDLE_FORMAT_VERSION = 1


class ModelNotTrainedError(FileNotFoundError):
    """Raised when the API or CLI needs a bundle that has not been produced yet."""


def save_bundle(bundle: dict[str, Any], path: str | Path | None = None) -> Path:
    """Atomically persist the bundle so a running API never reads a partial file."""
    path = Path(path) if path is not None else config.MODEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    required = {
        "format_version",
        "trained_at",
        "model_name",
        "pipeline",
        "threshold",
        "background",
        "feature_columns",
        "metadata",
    }
    missing = required - set(bundle)
    if missing:
        raise ValueError(f"Bundle is missing required keys: {sorted(missing)}")

    handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".joblib.tmp")
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        joblib.dump(bundle, temp_path, compress=3)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    logger.info("Saved model bundle to %s", path)
    return path


def load_bundle(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate a model bundle."""
    path = Path(path) if path is not None else config.MODEL_PATH
    if not path.exists():
        raise ModelNotTrainedError(
            f"No trained model found at {path}. "
            "Run `uv run churn-train` (or `python -m churn.train`) first."
        )
    bundle = joblib.load(path)
    if not isinstance(bundle, dict):
        raise ValueError(f"Invalid model bundle at {path}")
    version = bundle.get("format_version")
    if version != BUNDLE_FORMAT_VERSION:
        raise ValueError(
            f"Bundle format {version!r} is incompatible with API format "
            f"{BUNDLE_FORMAT_VERSION}. Retrain the model."
        )
    for key in ("pipeline", "threshold", "metadata"):
        if key not in bundle:
            raise ValueError(f"Bundle at {path} is missing '{key}'")
    return bundle


def write_metadata(metadata: dict[str, Any], path: str | Path | None = None) -> Path:
    path = Path(path) if path is not None else config.METADATA_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, default=str)
    logger.info("Saved metadata to %s", path)
    return path


def read_metadata(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path) if path is not None else config.METADATA_PATH
    if not path.exists():
        raise ModelNotTrainedError(f"No metadata found at {path}. Train the model first.")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
