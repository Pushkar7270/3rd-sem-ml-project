"""Scikit-learn preprocessing and model pipelines."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

from . import config


def build_preprocessor() -> ColumnTransformer:
    """Numeric imputation/scaling plus one-hot encoding of categoricals.

    Scaling is required by the distance/gradient based learners and harmless
    for tree ensembles; keeping one transformer for all models guarantees a
    like-for-like comparison and makes SHAP values directly comparable.
    """
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "onehot",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float64),
            ),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("num", numeric, config.NUMERIC_FEATURES),
            ("cat", categorical, config.CATEGORICAL_FEATURES),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
        sparse_threshold=0.0,
    )


def build_estimator(name: str) -> object:
    """Return an unfitted estimator with tuned-for-this-dataset defaults."""
    if name == "LogisticRegression":
        return LogisticRegression(
            C=1.0,
            solver="lbfgs",
            max_iter=2000,
            random_state=config.RANDOM_STATE,
        )
    if name == "DecisionTree":
        return DecisionTreeClassifier(
            max_depth=6,
            min_samples_leaf=25,
            random_state=config.RANDOM_STATE,
        )
    if name == "RandomForest":
        return RandomForestClassifier(
            n_estimators=400,
            max_depth=None,
            min_samples_leaf=2,
            max_features="sqrt",
            n_jobs=config.N_JOBS,
            random_state=config.RANDOM_STATE,
        )
    if name == "XGBoost":
        return XGBClassifier(
            n_estimators=400,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.8,
            min_child_weight=1,
            reg_lambda=1.0,
            tree_method="hist",
            eval_metric="logloss",
            n_jobs=config.N_JOBS,
            random_state=config.RANDOM_STATE,
        )
    if name == "KNN":
        return KNeighborsClassifier(
            n_neighbors=25,
            weights="distance",
            metric="minkowski",
            n_jobs=config.N_JOBS,
        )
    if name == "SVM":
        # SVC's built-in ``probability=True`` is deprecated (scikit-learn 1.9+);
        # use an explicit Platt-calibrated SVM instead so predict_proba stays
        # available for risk scoring.
        return CalibratedClassifierCV(
            SVC(
                C=1.0,
                kernel="rbf",
                gamma="scale",
                cache_size=1000,
                random_state=config.RANDOM_STATE,
            ),
            method="sigmoid",
            cv=5,
            ensemble=False,
        )
    raise ValueError(f"Unknown model '{name}'. Choose from {config.MODEL_NAMES}")


def build_pipeline(name: str) -> Pipeline:
    """Full unfitted pipeline: preprocessing + classifier."""
    if name not in config.MODEL_NAMES:
        raise ValueError(f"Unknown model '{name}'. Choose from {config.MODEL_NAMES}")
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            ("classifier", build_estimator(name)),
        ]
    )


def build_all_pipelines() -> dict[str, Pipeline]:
    return {name: build_pipeline(name) for name in config.MODEL_NAMES}


def feature_names(pipeline: Pipeline) -> list[str]:
    """Encoded feature names produced by the fitted preprocessor."""
    preprocessor: ColumnTransformer = pipeline.named_steps["preprocessor"]
    return [str(n) for n in preprocessor.get_feature_names_out()]


def raw_features_to_frame(records: list[dict] | dict[str, object]) -> pd.DataFrame:
    """Turn one or more raw customer payloads into a model-ready dataframe.

    Engineered features are derived here, which guarantees that training and
    serving use exactly the same transformations.
    """
    from .data import add_engineered_features

    if isinstance(records, dict):
        records = [records]
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(columns=config.FEATURE_COLUMNS)
    for column in config.FEATURE_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan
    enriched = add_engineered_features(frame)
    return enriched[config.FEATURE_COLUMNS]
