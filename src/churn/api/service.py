"""Application service layer: scoring, explanations, analytics and playbooks.

Keeping this logic outside the HTTP layer makes it reusable from notebooks,
tests and batch jobs, and keeps the FastAPI routes thin.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import config
from ..artifacts import load_bundle
from ..data import dataset_fingerprint, prepare_dataset
from ..explain import ChurnExplainer, main_risk_driver
from ..features import raw_features_to_frame
from ..recommend import recommend, recommendation_summary
from ..risk import (
    bands_from_details,
    financial_impact,
    probability_to_risk,
    risk_band_details,
)

logger = logging.getLogger(__name__)


class DataUnavailableError(RuntimeError):
    """Raised when an endpoint needs a dataset that was not loaded."""


class ChurnService:
    """High-level façade over the trained bundle and supporting datasets."""

    def __init__(
        self,
        bundle: dict[str, Any],
        *,
        scored: pd.DataFrame | None = None,
        raw: pd.DataFrame | None = None,
    ) -> None:
        self.bundle = bundle
        self.pipeline = bundle["pipeline"]
        self.threshold = float(bundle["threshold"])
        self.metadata: dict[str, Any] = bundle.get("metadata", {})
        self.model_name: str = str(bundle.get("model_name", "unknown"))
        self.scored = scored
        self.raw = raw
        background = bundle.get("background")
        if background is None or len(background) == 0:
            background = pd.DataFrame(columns=config.FEATURE_COLUMNS)
        self.explainer = ChurnExplainer(
            self.pipeline,
            background,
            kind=bundle.get("explainer_kind"),
        )
        band_details = self.metadata.get("risk_bands") or risk_band_details()
        self.risk_bands = bands_from_details(band_details)
        self._risk_distribution: dict[str, int] | None = None

    # ------------------------------------------------------------------ #
    # Constructors
    # ------------------------------------------------------------------ #
    @classmethod
    def from_paths(
        cls,
        bundle_path: str | Path | None = None,
        *,
        scored_path: str | Path | None = None,
        data_path: str | Path | None = None,
    ) -> ChurnService:
        bundle = load_bundle(bundle_path)
        scored = None
        scored_path = Path(scored_path) if scored_path else config.SCORED_CUSTOMERS_PATH
        if scored_path.exists():
            scored = pd.read_csv(scored_path)
            scored["customerID"] = scored["customerID"].astype(str)
            if "top_driver" in scored:
                scored["top_driver"] = scored["top_driver"].fillna("")
            else:
                scored["top_driver"] = ""
            logger.info("Loaded %d scored customers from %s", len(scored), scored_path)
        else:
            logger.warning("Scored customer file not found at %s", scored_path)

        raw = None
        data_path = Path(data_path) if data_path else config.DATA_PATH
        if data_path.exists():
            try:
                raw = prepare_dataset(data_path)
                logger.info("Loaded raw dataset for analytics (%d rows)", len(raw))
            except Exception:  # pragma: no cover - defensive, analytics is optional
                logger.exception("Could not load the raw dataset for analytics")
        else:
            logger.warning("Raw dataset not found at %s; EDA endpoints are disabled", data_path)
        return cls(bundle, scored=scored, raw=raw)

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #
    def model_ref(self) -> dict[str, str]:
        return {
            "name": self.model_name,
            "display_name": config.MODEL_DISPLAY_NAMES.get(self.model_name, self.model_name),
            "version": str(self.metadata.get("model_version", "unknown")),
        }

    def model_info(self) -> dict[str, Any]:
        metadata = self.metadata
        return {
            "model": self.model_ref(),
            "model_description": metadata.get("model_description", ""),
            "trained_at": metadata.get("trained_at"),
            "selection_metric": metadata.get("selection_metric"),
            "selection_reason": metadata.get("selection_reason"),
            "cv_folds": metadata.get("cv_folds"),
            "threshold": self.threshold,
            "threshold_selection": metadata.get("threshold_selection"),
            "dataset": metadata.get("dataset"),
            "features": metadata.get("features"),
            "explainability": metadata.get("explainability"),
            "risk_bands": metadata.get("risk_bands", risk_band_details()),
            "risk_distribution": self.risk_distribution(),
            "global_importance": metadata.get("global_importance", [])[:15],
            "native_importance": metadata.get("native_importance", [])[:15],
            "test_metrics": metadata.get("final_test_metrics"),
            "libraries": metadata.get("libraries"),
        }

    def model_metrics(self) -> dict[str, Any]:
        metadata = self.metadata
        return {
            "model": self.model_ref(),
            "selection_metric": metadata.get("selection_metric"),
            "selection_reason": metadata.get("selection_reason"),
            "cv_folds": metadata.get("cv_folds"),
            "cv_results": metadata.get("cv_results", {}),
            "test_results": metadata.get("test_results", {}),
            "final_test_metrics": metadata.get("final_test_metrics", {}),
            "threshold": self.threshold,
            "pr_baseline": metadata.get("pr_baseline"),
            "curves": metadata.get("curves", {}),
            "risk_bands": metadata.get("risk_bands", risk_band_details()),
            "note": metadata.get("binary_metrics_note"),
        }

    def risk_distribution(self) -> dict[str, int]:
        if self._risk_distribution is not None:
            return self._risk_distribution
        if self.scored is not None and "risk_level" in self.scored:
            counts = self.scored["risk_level"].value_counts().to_dict()
            self._risk_distribution = {str(k): int(v) for k, v in counts.items()}
        else:
            self._risk_distribution = {}
        return self._risk_distribution

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "model_loaded": True,
            "model_name": self.model_name,
            "model_version": str(self.metadata.get("model_version", "unknown")),
            "threshold": self.threshold,
            "scored_customers": int(len(self.scored)) if self.scored is not None else 0,
            "api_version": config.API_VERSION,
        }

    # ------------------------------------------------------------------ #
    # Predictions
    # ------------------------------------------------------------------ #
    def predict_records(
        self,
        records: Iterable[dict[str, Any]],
        *,
        include_drivers: bool = True,
        include_recommendations: bool = True,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        records = list(records)
        if not records:
            return []

        frame = raw_features_to_frame(records)
        probabilities = self.pipeline.predict_proba(frame)[:, 1]
        # Recommendations depend on SHAP drivers, so explanations are computed
        # whenever either output is requested.  The response flag only controls
        # whether the drivers are returned, not whether recommendations are
        # allowed to differ.
        need_explanation = include_drivers or include_recommendations
        shap_result = self.explainer.explain(frame) if need_explanation else None

        predictions: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            probability = float(probabilities[index])
            risk_level = probability_to_risk(probability, self.risk_bands)
            drivers = (
                self.explainer.top_drivers(frame.iloc[index], shap_result.values[index], k=5)
                if shap_result is not None
                else []
            )
            profile = frame.iloc[index].to_dict()
            recs = (
                recommend(profile, probability, risk_level, drivers, limit=limit)
                if include_recommendations
                else []
            )
            monthly = float(profile.get("MonthlyCharges") or 0.0)
            customer_id = record.get("customerID")
            if customer_id is None or (isinstance(customer_id, float) and np.isnan(customer_id)):
                customer_id = None
            else:
                customer_id = str(customer_id)

            main_driver = main_risk_driver(drivers)
            primary_label = main_driver["label"] if main_driver else "the overall account profile"
            primary_is_risk = bool(main_driver and main_driver["contribution"] > 0)
            summary = f"{risk_level.title()} churn risk ({probability:.0%}). "
            if primary_is_risk:
                summary += f"Main risk factor: {primary_label}. "
            else:
                summary += "No single risk-increasing factor dominates. "
            summary += recommendation_summary(recs, risk_level) if recs else ""

            predictions.append(
                {
                    "customer_id": customer_id,
                    "churn_probability": round(probability, 6),
                    "churn_prediction": bool(probability >= self.threshold),
                    "risk_level": risk_level,
                    "threshold": round(self.threshold, 4),
                    "top_drivers": drivers if include_drivers else [],
                    "top_risk_driver": main_driver,
                    "recommendations": recs,
                    "financial_impact": financial_impact(monthly, probability),
                    "summary": summary.strip(),
                    "model": self.model_ref(),
                }
            )
        return predictions

    def predict_one(
        self,
        record: dict[str, Any],
        *,
        include_drivers: bool = True,
        include_recommendations: bool = True,
    ) -> dict[str, Any]:
        return self.predict_records(
            [record],
            include_drivers=include_drivers,
            include_recommendations=include_recommendations,
        )[0]

    def predict_batch(
        self,
        records: list[dict[str, Any]],
        *,
        include_drivers: bool = True,
        include_recommendations: bool = True,
    ) -> dict[str, Any]:
        predictions = self.predict_records(
            records,
            include_drivers=include_drivers,
            include_recommendations=include_recommendations,
        )
        counts = {"high": 0, "medium": 0, "low": 0}
        for prediction in predictions:
            counts[prediction["risk_level"]] += 1
        return {
            "summary": {
                "total": len(predictions),
                "predicted_churners": sum(int(p["churn_prediction"]) for p in predictions),
                "high_risk": counts["high"],
                "medium_risk": counts["medium"],
                "low_risk": counts["low"],
                "average_probability": round(
                    float(np.mean([p["churn_probability"] for p in predictions])), 4
                ),
                "annual_revenue_at_risk": round(
                    float(
                        sum(p["financial_impact"]["annual_revenue_at_risk"] for p in predictions)
                    ),
                    2,
                ),
            },
            "predictions": predictions,
        }

    # ------------------------------------------------------------------ #
    # Customer book
    # ------------------------------------------------------------------ #
    def _require_scored(self) -> pd.DataFrame:
        if self.scored is None:
            raise DataUnavailableError(
                "Scored customer data is unavailable. Run the training pipeline to generate "
                "data/processed/scored_customers.csv."
            )
        return self.scored

    def high_risk_customers(
        self,
        *,
        limit: int = 20,
        risk_level: str | None = None,
        min_probability: float | None = None,
    ) -> dict[str, Any]:
        scored = self._require_scored()
        if risk_level is not None and risk_level not in {"low", "medium", "high"}:
            raise ValueError("risk_level must be one of: low, medium, high")
        filtered = scored
        if risk_level:
            filtered = filtered[filtered["risk_level"] == risk_level]
        if min_probability is not None:
            filtered = filtered[filtered["churn_probability"] >= float(min_probability)]
        filtered = filtered.sort_values("churn_probability", ascending=False)
        total = int(len(filtered))
        rows = filtered.head(max(1, min(int(limit), 500)))

        customers = [
            {
                "customer_id": str(row["customerID"]),
                "churn_probability": round(float(row["churn_probability"]), 4),
                "risk_level": str(row["risk_level"]),
                "tenure": int(row["tenure"]),
                "contract": str(row["Contract"]),
                "internet_service": str(row["InternetService"]),
                "payment_method": str(row["PaymentMethod"]),
                "monthly_charges": round(float(row["MonthlyCharges"]), 2),
                "annual_revenue_at_risk": round(float(row["annual_revenue_at_risk"]), 2),
                "estimated_clv": round(float(row["estimated_clv"]), 2),
                "top_risk_driver": (
                    "" if pd.isna(row.get("top_driver")) else str(row.get("top_driver"))
                ),
            }
            for _, row in rows.iterrows()
        ]
        return {
            "total_matching": total,
            "returned": len(customers),
            "filters": {
                "limit": limit,
                "risk_level": risk_level,
                "min_probability": min_probability,
            },
            "customers": customers,
        }

    def customer_detail(self, customer_id: str) -> dict[str, Any] | None:
        customer_id = str(customer_id)
        if self.raw is not None and config.ID_COLUMN in self.raw.columns:
            matches = self.raw[self.raw[config.ID_COLUMN].astype(str) == customer_id]
            if len(matches):
                record = matches.iloc[0].to_dict()
                record["customerID"] = customer_id
                return self.predict_one(record)

        scored = self._require_scored()
        matches = scored[scored["customerID"].astype(str) == customer_id]
        if not len(matches):
            return None
        row = matches.iloc[0]
        record = {
            "customerID": customer_id,
            "tenure": int(row["tenure"]),
            "Contract": row["Contract"],
            "InternetService": row["InternetService"],
            "PaymentMethod": row["PaymentMethod"],
            "MonthlyCharges": float(row["MonthlyCharges"]),
            "TotalCharges": round(float(row["MonthlyCharges"]) * max(int(row["tenure"]), 1), 2),
        }
        return self.predict_one(record)

    # ------------------------------------------------------------------ #
    # EDA
    # ------------------------------------------------------------------ #
    def _segment(self, column: str) -> list[dict[str, Any]]:
        assert self.raw is not None
        grouped = (
            self.raw.groupby(column, observed=True)[config.TARGET]
            .agg(["size", "mean"])
            .reset_index()
        )
        return [
            {
                "segment": str(row[column]),
                "customers": int(row["size"]),
                "churn_rate": round(float(row["mean"]), 4),
            }
            for _, row in grouped.iterrows()
        ]

    def eda_summary(self) -> dict[str, Any]:
        if self.raw is None:
            raise DataUnavailableError("Raw dataset is unavailable; EDA endpoints are disabled.")
        df = self.raw
        churn = df[config.TARGET]
        churned = int(churn.sum())
        total = int(len(df))

        monthly = df["MonthlyCharges"].astype(float)
        edges = np.linspace(float(monthly.min()), float(monthly.max()), 21)
        churn_hist, _ = np.histogram(monthly[churn == 1], bins=edges)
        stay_hist, _ = np.histogram(monthly[churn == 0], bins=edges)

        tenure_bucket = pd.cut(
            df["tenure"],
            bins=[-0.1, 6, 12, 24, 48, np.inf],
            labels=["0-6", "7-12", "13-24", "25-48", "49+"],
        )
        bucket = (
            df.assign(TenureBucket=tenure_bucket)
            .groupby("TenureBucket", observed=True)[config.TARGET]
            .agg(["size", "mean"])
            .reset_index()
        )

        correlations = (
            df[config.NUMERIC_FEATURES]
            .corrwith(churn)
            .dropna()
            .sort_values(key=np.abs, ascending=False)
            .head(10)
        )

        return {
            "dataset": {
                **dataset_fingerprint(df),
                "source": "IBM Telco Customer Churn",
            },
            "churn_rate": round(float(churn.mean()), 4),
            "customers": total,
            "churned": churned,
            "retained": total - churned,
            "monthly_charges": {
                "average_churn": round(float(monthly[churn == 1].mean()), 2),
                "average_stay": round(float(monthly[churn == 0].mean()), 2),
                "histogram": {
                    "bin_edges": [round(float(v), 2) for v in edges],
                    "counts_churn": [int(v) for v in churn_hist],
                    "counts_stay": [int(v) for v in stay_hist],
                },
            },
            "tenure": {
                "average_churn": round(float(df.loc[churn == 1, "tenure"].mean()), 1),
                "average_stay": round(float(df.loc[churn == 0, "tenure"].mean()), 1),
                "median_churn": float(df.loc[churn == 1, "tenure"].median()),
                "median_stay": float(df.loc[churn == 0, "tenure"].median()),
            },
            "churn_by_contract": self._segment("Contract"),
            "churn_by_internet": self._segment("InternetService"),
            "churn_by_payment": self._segment("PaymentMethod"),
            "churn_by_tenure_bucket": [
                {
                    "segment": str(row["TenureBucket"]),
                    "customers": int(row["size"]),
                    "churn_rate": round(float(row["mean"]), 4),
                }
                for _, row in bucket.iterrows()
            ],
            "churn_by_senior": self._segment("SeniorCitizen"),
            "numeric_correlations": [
                {
                    "feature": str(feature),
                    "label": config.FEATURE_LABELS.get(str(feature), str(feature)),
                    "correlation": round(float(value), 4),
                }
                for feature, value in correlations.items()
            ],
            "risk_distribution": self.risk_distribution(),
        }
