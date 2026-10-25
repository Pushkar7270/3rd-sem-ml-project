"""Data loading, cleaning and splitting utilities."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from . import config

logger = logging.getLogger(__name__)


def load_raw(path: str | Path | None = None) -> pd.DataFrame:
    """Load the raw IBM Telco Customer Churn CSV."""
    path = Path(path) if path is not None else config.DATA_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {path}. Run `python scripts/download_data.py` first."
        )
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    logger.info("Loaded %d rows x %d columns from %s", *df.shape, path)
    return df


def clean_data(df: pd.DataFrame, *, require_target: bool = True) -> pd.DataFrame:
    """Clean the raw dataframe and standardise the target.

    The public dataset stores ``TotalCharges`` as a string with 11 blank values
    for brand-new customers (tenure = 0).  Those blanks are semantically zero,
    not missing-at-random, so they are filled with 0.  Any remaining blanks fall
    back to the column median.

    Returns a copy with the target renamed to ``churn`` (0/1) when available.
    """
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    if "TotalCharges" in df.columns:
        df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
        # Brand-new customers (tenure = 0) have blank TotalCharges in the public
        # CSV.  Their lifetime spend really is zero, so this is a semantic fill,
        # not a statistical imputation.  Any other blanks fall back to the median.
        tenure_values = pd.to_numeric(df.get("tenure"), errors="coerce")
        missing = df["TotalCharges"].isna()
        zero_tenure = missing & (tenure_values == 0)
        df.loc[zero_tenure, "TotalCharges"] = 0.0
        remaining = df["TotalCharges"].isna()
        if remaining.any():
            logger.warning("Imputing %d TotalCharges values with median", remaining.sum())
            df["TotalCharges"] = df["TotalCharges"].fillna(df["TotalCharges"].median())

    if "tenure" in df.columns:
        df["tenure"] = pd.to_numeric(df["tenure"], errors="coerce")

    if require_target:
        if config.TARGET_RAW not in df.columns:
            raise ValueError(f"Target column '{config.TARGET_RAW}' not found")
        mapped = df[config.TARGET_RAW].astype(str).str.strip().str.lower().map({"yes": 1, "no": 0})
        if mapped.isna().any():
            bad = df.loc[mapped.isna(), config.TARGET_RAW].unique()[:5]
            raise ValueError(f"Unexpected target values: {bad}")
        df[config.TARGET] = mapped.astype(int)
        if "Churn" in df.columns and config.TARGET != "Churn":
            df = df.drop(columns=["Churn"])

    return df


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add domain-motivated features used by every model.

    * ``NumServices`` – breadth of adoption (stickiness proxy).
    * ``SupportServices`` / ``StreamingServices`` – grouped service adoption.
    * ``IsNewCustomer`` – first six months are the highest-churn period.
    * ``HasFamily`` – customers with a partner or dependents churn less.

    Deliberately no ratio features (e.g. total/tenure): they are strongly
    collinear with tenure and monthly charges and produced unstable,
    counter-intuitive SHAP attributions in the logistic model.
    """
    out = df.copy()

    tenure = (
        pd.to_numeric(out["tenure"], errors="coerce").fillna(0)
        if "tenure" in out
        else pd.Series(0.0, index=out.index)
    )

    def _count_yes(columns: list[str]) -> pd.Series:
        available = [c for c in columns if c in out.columns]
        if not available:
            return pd.Series(0, index=out.index, dtype=int)
        return (out[available] == "Yes").sum(axis=1).astype(int)

    out["NumServices"] = _count_yes(config.SERVICE_COLUMNS)
    out["SupportServices"] = _count_yes(config.SUPPORT_COLUMNS)
    out["StreamingServices"] = _count_yes(config.STREAMING_COLUMNS)
    out["IsNewCustomer"] = (tenure <= 6).astype(int)
    partner = out["Partner"] if "Partner" in out.columns else pd.Series(False, index=out.index)
    dependents = (
        out["Dependents"] if "Dependents" in out.columns else pd.Series(False, index=out.index)
    )
    out["HasFamily"] = ((partner == "Yes") | (dependents == "Yes")).astype(int)
    if "SeniorCitizen" in out:
        out["SeniorCitizen"] = (
            pd.to_numeric(out["SeniorCitizen"], errors="coerce").fillna(0).astype(int)
        )
    else:
        out["SeniorCitizen"] = 0

    return out


def prepare_dataset(path: str | Path | None = None) -> pd.DataFrame:
    """Load, clean and enrich the dataset in one call."""
    df = clean_data(load_raw(path))
    df = add_engineered_features(df)
    missing = [c for c in config.FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing expected feature columns: {missing}")
    return df


def split_dataset(
    df: pd.DataFrame,
    *,
    test_size: float = config.TEST_SIZE,
    random_state: int = config.RANDOM_STATE,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Stratified train/test split.

    Returns ``X_train, X_test, y_train, y_test, ids_train, ids_test``.
    Feature matrices contain only the columns the models consume.
    """
    X = df[config.FEATURE_COLUMNS].copy()
    y = df[config.TARGET].astype(int)
    ids = (
        df[config.ID_COLUMN]
        if config.ID_COLUMN in df.columns
        else pd.Series(df.index, index=df.index)
    )

    return train_test_split(
        X,
        y,
        ids,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )


def dataset_fingerprint(df: pd.DataFrame) -> dict[str, object]:
    """Small summary used in metadata for reproducibility checks."""
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "churn_rate": round(float(df[config.TARGET].mean()), 4),
        "unique_customers": int(df[config.ID_COLUMN].nunique())
        if config.ID_COLUMN in df.columns
        else None,
    }
