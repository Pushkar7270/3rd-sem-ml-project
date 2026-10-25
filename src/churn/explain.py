"""Explainability utilities: SHAP values, coefficients and feature importances."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

from . import config
from .features import feature_names, raw_features_to_frame

logger = logging.getLogger(__name__)

TREE_MODELS = (
    DecisionTreeClassifier,
    RandomForestClassifier,
    GradientBoostingClassifier,
    ExtraTreesClassifier,
    XGBClassifier,
)


@dataclass
class ShapResult:
    values: np.ndarray
    base_value: float
    feature_names: list[str]
    transformed: np.ndarray

    @property
    def mean_abs(self) -> np.ndarray:
        return np.abs(self.values).mean(axis=0)


def explainer_kind(pipeline: Pipeline) -> str:
    """Pick the cheapest exact/approximate SHAP algorithm for the classifier."""
    classifier = pipeline.named_steps["classifier"]
    if isinstance(classifier, TREE_MODELS):
        return "tree"
    if isinstance(classifier, LogisticRegression):
        return "linear"
    return "permutation"


def _extract_binary(values: Any) -> np.ndarray:
    """Normalise SHAP output across versions/models to (n_samples, n_features)."""
    if isinstance(values, list):
        values = values[-1]
    array = np.asarray(values, dtype=float)
    if array.ndim == 3:
        array = array[:, :, -1]
    if array.ndim == 2 and array.shape[0] == 1 and array.shape[1] != 1:
        # Single sample returned as (1, n_features) is already correct.
        pass
    return array


def _extract_base(base: Any) -> float:
    if isinstance(base, (list, tuple)):
        base = base[-1]
    array = np.asarray(base, dtype=float).ravel()
    return float(array[-1]) if array.size else 0.0


def pretty_feature_name(encoded_name: str) -> tuple[str, str, str]:
    """Map an encoded feature back to (label, source_column, category_value).

    ``Contract_Month-to-month`` becomes
    ``("Contract: Month-to-month", "Contract", "Month-to-month")``.
    Numeric features keep their raw value as the third element (empty string).
    """
    for column in sorted(config.CATEGORICAL_FEATURES, key=len, reverse=True):
        prefix = f"{column}_"
        if encoded_name.startswith(prefix):
            value = encoded_name[len(prefix) :]
            label = config.FEATURE_LABELS.get(column, column)
            return f"{label}: {value}", column, value
    label = config.FEATURE_LABELS.get(encoded_name, encoded_name)
    return label, encoded_name, ""


def _clean_value(value: Any) -> Any:
    """Render a raw feature value for JSON without numpy scalar types."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return round(float(value), 2)
    if isinstance(value, (int, bool)):
        return value
    return str(value)


class ChurnExplainer:
    """Reusable SHAP wrapper for a fitted churn pipeline."""

    def __init__(
        self,
        pipeline: Pipeline,
        background: pd.DataFrame,
        *,
        kind: str | None = None,
        background_size: int = 100,
    ) -> None:
        self.pipeline = pipeline
        self.kind = kind or explainer_kind(pipeline)
        self.feature_names = feature_names(pipeline)
        self.background = background[config.FEATURE_COLUMNS].head(background_size).copy()
        self._background_transformed: np.ndarray | None = None
        self._explainer: Any = None

    @property
    def background_transformed(self) -> np.ndarray:
        if self._background_transformed is None:
            self._background_transformed = np.asarray(
                self.pipeline.named_steps["preprocessor"].transform(self.background), dtype=float
            )
        return self._background_transformed

    def _get_explainer(self) -> Any:
        if self._explainer is not None:
            return self._explainer
        classifier = self.pipeline.named_steps["classifier"]
        if self.kind == "tree":
            self._explainer = shap.TreeExplainer(classifier)
        elif self.kind == "linear":
            masker = shap.maskers.Independent(self.background_transformed, max_samples=100)
            self._explainer = shap.LinearExplainer(classifier, masker)
        else:
            masker = shap.maskers.Independent(self.background_transformed, max_samples=20)
            max_evals = 2 * len(self.feature_names) + 1
            self._explainer = shap.PermutationExplainer(
                classifier.predict_proba, masker, max_evals=max_evals
            )
        return self._explainer

    def explain(
        self, X_raw: pd.DataFrame | list[dict] | dict, *, max_rows: int | None = None
    ) -> ShapResult:
        """Compute SHAP values for raw customer records."""
        if isinstance(X_raw, (list, dict)):
            X_raw = pd.DataFrame(X_raw if isinstance(X_raw, list) else [X_raw])
        frame = raw_features_to_frame(X_raw)
        if max_rows is not None:
            frame = frame.head(max_rows)

        transformed = np.asarray(
            self.pipeline.named_steps["preprocessor"].transform(frame), dtype=float
        )
        explainer = self._get_explainer()
        if self.kind == "permutation":
            max_evals = 2 * len(self.feature_names) + 1
            explanation = explainer(transformed, max_evals=max_evals)
            values = explanation.values
            base = explanation.base_values
        else:
            values = explainer.shap_values(transformed)
            base = explainer.expected_value
        return ShapResult(
            values=_extract_binary(values),
            base_value=_extract_base(base),
            feature_names=list(self.feature_names),
            transformed=transformed,
        )

    # ------------------------------------------------------------------ #
    # Per-customer explanations
    # ------------------------------------------------------------------ #
    def top_drivers(
        self,
        raw_row: dict[str, Any] | pd.Series,
        values: np.ndarray,
        *,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return the ``k`` source features with the largest absolute impact.

        One-hot columns are collapsed to the category the customer actually
        holds.  Showing ``InternetService: Fiber optic`` to a customer with no
        internet (because the dummy is 0) would contradict the input; instead we
        report ``Internet service: No`` with the SHAP value of that category.
        """
        row = pd.Series(raw_row) if isinstance(raw_row, dict) else raw_row
        contributions = np.asarray(values, dtype=float).ravel()
        if contributions.shape[0] != len(self.feature_names):
            raise ValueError(
                f"Expected {len(self.feature_names)} SHAP values, got {contributions.shape[0]}"
            )

        candidates: list[dict[str, Any]] = []
        for encoded, contribution in zip(self.feature_names, contributions, strict=True):
            label, source, category_value = pretty_feature_name(encoded)
            if category_value:
                actual = row.get(source)
                if pd.isna(actual) or str(actual).strip() != category_value:
                    continue
                display_value: Any = str(actual).strip()
            else:
                display_value = _clean_value(row.get(source))
            contribution = float(contribution)
            candidates.append(
                {
                    "feature": encoded,
                    "label": label,
                    "source": source,
                    "value": display_value,
                    "contribution": round(contribution, 4),
                    "impact": "increases" if contribution > 0 else "decreases",
                }
            )

        candidates.sort(key=lambda driver: -abs(driver["contribution"]))
        return candidates[: max(1, int(k))]

    def explain_customer(
        self, raw: dict[str, Any], *, k: int = 5
    ) -> tuple[list[dict[str, Any]], ShapResult]:
        frame = pd.DataFrame([raw])
        result = self.explain(frame)
        drivers = self.top_drivers(frame.iloc[0], result.values[0], k=k)
        return drivers, result

    # ------------------------------------------------------------------ #
    # Global explanations
    # ------------------------------------------------------------------ #
    def global_importance(
        self, result: ShapResult, *, top_n: int | None = 20, aggregate: bool = False
    ) -> list[dict[str, Any]]:
        """Rank features by mean absolute SHAP value.

        With ``aggregate=True`` one-hot columns are summed back to their source
        feature, which is easier to communicate to business stakeholders.
        """
        mean_abs = result.mean_abs
        if aggregate:
            totals: dict[str, float] = defaultdict(float)
            labels: dict[str, str] = {}
            for name, value in zip(result.feature_names, mean_abs, strict=True):
                label, source, _ = pretty_feature_name(name)
                totals[source] += float(value)
                labels[source] = config.FEATURE_LABELS.get(source, source)
            rows = [
                {
                    "feature": source,
                    "label": labels[source],
                    "importance": round(value, 4),
                }
                for source, value in totals.items()
            ]
        else:
            rows = []
            for name, value in zip(result.feature_names, mean_abs, strict=True):
                label, source, _ = pretty_feature_name(name)
                rows.append(
                    {
                        "feature": name,
                        "label": label,
                        "source": source,
                        "importance": round(float(value), 4),
                    }
                )
        rows.sort(key=lambda item: -item["importance"])
        return rows[:top_n] if top_n else rows


def native_importance(pipeline: Pipeline, *, top_n: int = 20) -> list[dict[str, Any]]:
    """Model-native coefficients or feature importances.

    Logistic regression exposes signed coefficients (log-odds); tree ensembles
    expose impurity/gain based importances.  For KNN/SVM an empty list is
    returned because no native global importance exists.
    """
    classifier = pipeline.named_steps["classifier"]
    names = feature_names(pipeline)
    values: np.ndarray | None = None
    kind = ""
    if hasattr(classifier, "coef_"):
        values = np.asarray(classifier.coef_).ravel()
        kind = "coefficient"
    elif hasattr(classifier, "feature_importances_"):
        values = np.asarray(classifier.feature_importances_).ravel()
        kind = "feature_importance"
    if values is None:
        return []

    rows = []
    for name, value in zip(names, values, strict=True):
        label, source, category_value = pretty_feature_name(name)
        rows.append(
            {
                "feature": name,
                "label": label,
                "source": source,
                "value": round(float(value), 4),
                "abs_value": round(abs(float(value)), 4),
                "kind": kind,
                "direction": ("increases risk" if value > 0 else "decreases risk")
                if kind == "coefficient"
                else "importance",
            }
        )
    rows.sort(key=lambda item: -item["abs_value"])
    return rows[:top_n]


def shap_summary_frame(result: ShapResult) -> pd.DataFrame:
    """Dataframe of SHAP values with human readable columns (for plots/exports)."""
    labels = [pretty_feature_name(name)[0] for name in result.feature_names]
    return pd.DataFrame(result.values, columns=labels)


def main_risk_driver(drivers: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the strongest risk-*increasing* driver for customer-facing copy.

    A high-risk customer can have a large protective factor (e.g. a long
    tenure) that outweighs the reasons they are at risk.  Retention messaging
    should surface a factor that actually pushes risk up; fall back to the
    largest absolute contributor when every driver is protective.
    """
    if not drivers:
        return None
    for driver in drivers:
        if float(driver.get("contribution", 0.0)) > 0:
            return driver
    return drivers[0]
