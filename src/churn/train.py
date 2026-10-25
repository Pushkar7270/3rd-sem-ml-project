"""End-to-end training pipeline.

Usage:
    python -m churn.train
    uv run churn-train --cv-folds 5 --no-figures

The pipeline compares six classifiers with stratified 5-fold cross-validation,
selects the best ROC-AUC model, tunes the decision threshold on out-of-fold
predictions, evaluates on a held-out test set, computes explanations, scores
every customer, and writes a deployable artifact bundle plus reports.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve, roc_curve
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

from . import config
from .artifacts import save_bundle, write_metadata
from .data import dataset_fingerprint, prepare_dataset, split_dataset
from .evaluate import (
    cross_validate_pipeline,
    curve_points,
    cv_summary_table,
    evaluate_predictions,
    flatten_cv_results,
    tune_threshold,
)
from .explain import ChurnExplainer, native_importance
from .features import build_pipeline, feature_names
from .risk import (
    financial_impact,
    probability_to_risk,
    risk_band_details,
    risk_bands_for_threshold,
)

logger = logging.getLogger(__name__)


def _versions() -> dict[str, str]:
    import shap
    import sklearn
    import xgboost

    return {
        "python": f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}",
        "scikit-learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
        "shap": shap.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }


def _markdown_table(frame: pd.DataFrame) -> str:
    headers = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.tolist()) + " |")
    return "\n".join(lines)


def _model_card(
    model_name: str,
    metadata: dict[str, Any],
    cv_table: pd.DataFrame,
    test_table: pd.DataFrame,
    figures: list[str],
) -> str:
    cv = metadata["cv_results"][model_name]
    final = metadata["final_test_metrics"]
    bands = "\n".join(
        f"- **{b['level'].title()}**: {b['min_probability']:.0%} - {b['max_probability']:.0%}"
        for b in metadata["risk_bands"]
    )
    drivers = "\n".join(
        f"{i}. {row['label']} - mean |SHAP| {row['importance']:.4f}"
        for i, row in enumerate(metadata["global_importance"][:10], start=1)
    )
    return f"""# Model card - Telco Churn Intelligence

## Overview

| Field | Value |
| --- | --- |
| Selected model | {config.MODEL_DISPLAY_NAMES.get(model_name, model_name)} |
| Task | Binary classification (churn vs stay) |
| Selection metric | 5-fold cross-validated ROC-AUC |
| CV ROC-AUC | {cv["roc_auc"]["mean"]:.4f} +/- {cv["roc_auc"]["std"]:.4f} |
| CV PR-AUC | {cv["pr_auc"]["mean"]:.4f} +/- {cv["pr_auc"]["std"]:.4f} |
| Decision threshold | {metadata["threshold"]:.2f} (F1-maximising on out-of-fold predictions) |
| Test ROC-AUC | {final["roc_auc"]:.4f} |
| Test PR-AUC | {final["pr_auc"]:.4f} |
| Test F1 | {final["f1"]:.4f} |
| Test recall | {final["recall"]:.4f} |
| Test precision | {final["precision"]:.4f} |
| Test Brier score | {final["brier"]:.4f} |
| Trained at | {metadata["trained_at"]} |

## Dataset

- Source: IBM Telco Customer Churn (public Kaggle dataset).
- Rows: {metadata["dataset"]["rows"]:,} customers, churn rate {metadata["dataset"]["churn_rate"]:.2%}.
- Train/test split: {metadata["dataset"]["train_rows"]:,} / {metadata["dataset"]["test_rows"]:,} (stratified).
- Features: {len(metadata["features"]["raw_numeric"])} numeric, {len(metadata["features"]["raw_categorical"])} categorical, plus domain-engineered service counts, a new-customer flag and a family flag.
- `TotalCharges` blanks (new customers with tenure 0) are set to 0, not imputed with the median.

## Methodology

1. Clean and enrich the raw data; keep `customerID` out of the feature matrix.
2. Compare Logistic Regression, Decision Tree, Random Forest, XGBoost, KNN and SVM.
3. Every model shares the same preprocessing pipeline (median imputation + scaling, most-frequent imputation + one-hot encoding) inside a single scikit-learn `Pipeline`, so cross-validation cannot leak.
4. Select the model with the highest mean ROC-AUC over {metadata["cv_folds"]}-fold stratified CV.
5. Tune the probability threshold on out-of-fold predictions to maximise F1.
6. Report held-out test metrics, calibration, SHAP explanations and permutation/native importance.
7. Score the full customer base into low/medium/high risk bands and attach retention playbooks.

## Model comparison (5-fold CV, training set)

{_markdown_table(cv_table)}

## Held-out test metrics

{_markdown_table(test_table)}

## Selected model performance

Confusion matrix at the tuned threshold:

| | Predicted stay | Predicted churn |
| --- | --- | --- |
| Actual stay | {final["confusion"]["true_negative"]:,} | {final["confusion"]["false_positive"]:,} |
| Actual churn | {final["confusion"]["false_negative"]:,} | {final["confusion"]["true_positive"]:,} |

At the default 0.5 threshold the model scores ROC-AUC {metadata["test_results"][model_name]["roc_auc"]:.4f} and F1 {metadata["test_results"][model_name]["f1"]:.4f}.

## Key churn drivers (SHAP)

{drivers}

Signed per-customer contributions are available from `POST /predict`; global SHAP plots are in `reports/figures/`.

## Risk bands

{bands}

`annual_revenue_at_risk = MonthlyCharges x 12 x P(churn)`.
`estimated_clv = MonthlyCharges x expected remaining months`, where expected remaining months is `min(1 / P(churn), 72)`.

## Retention recommendations

The rule-based playbook combines risk level and SHAP drivers (contract, fiber pricing, payment method, support, security, tenure, senior status, billing and bundles). Recommendations expose priority and expected impact but are heuristics, not causal uplift estimates.

## Limitations and responsible use

- Observational data: associations are not causal effects. Retention offers should be A/B tested.
- The dataset is US-centric and synthetic-ish; performance may drift on other markets.
- Churn labels are imbalanced (~27%); precision/recall trade-offs must be set with business costs.
- Protected attributes (gender, senior status) are present for analysis. Do not use the model to deny service; use it to target support.
- SHAP values explain the model, not the customer's true reasons for leaving.
- Retrain when churn base rates or product portfolio change; monitor calibration and drift.

## Reproduction

```bash
uv sync
python -m churn.train --cv-folds {metadata["cv_folds"]}
```

Generated figures: {", ".join(Path(f).name for f in figures)}
"""


def train(
    data_path: str | Path | None = None,
    *,
    artifact_dir: str | Path | None = None,
    report_dir: str | Path | None = None,
    processed_dir: str | Path | None = None,
    cv_folds: int = config.CV_FOLDS,
    test_size: float = config.TEST_SIZE,
    models: list[str] | None = None,
    make_figures: bool = True,
    shap_sample: int = 300,
    random_state: int = config.RANDOM_STATE,
) -> dict[str, Any]:
    """Train, evaluate, explain and package the churn models."""
    started = time.perf_counter()
    models = models or list(config.MODEL_NAMES)
    unknown = set(models) - set(config.MODEL_NAMES)
    if unknown:
        raise ValueError(f"Unknown models: {sorted(unknown)}")

    artifact_dir = Path(artifact_dir) if artifact_dir else config.ARTIFACT_DIR
    report_dir = Path(report_dir) if report_dir else config.REPORT_DIR
    processed_dir = Path(processed_dir) if processed_dir else config.PROCESSED_DIR
    figure_dir = report_dir / "figures"
    for directory in (artifact_dir, report_dir, figure_dir, processed_dir):
        directory.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "model.joblib"
    metadata_path = artifact_dir / "metadata.json"

    np.random.seed(random_state)

    logger.info("Loading and preparing data ...")
    df = prepare_dataset(data_path)
    fingerprint = dataset_fingerprint(df)
    X_train, X_test, y_train, y_test, ids_train, ids_test = split_dataset(
        df, test_size=test_size, random_state=random_state
    )
    logger.info(
        "Train %d rows (%.1f%% churn) | Test %d rows (%.1f%% churn)",
        len(X_train),
        100 * y_train.mean(),
        len(X_test),
        100 * y_test.mean(),
    )

    cv_results: dict[str, dict[str, dict[str, float]]] = {}
    test_results: dict[str, dict[str, Any]] = {}
    test_probabilities: dict[str, np.ndarray] = {}
    fitted: dict[str, Pipeline] = {}
    full_curves: dict[str, dict[str, Any]] = {}

    for index, name in enumerate(models, start=1):
        logger.info("[%d/%d] Training %s ...", index, len(models), name)
        pipeline = build_pipeline(name)
        cv_metrics = cross_validate_pipeline(
            pipeline, X_train, y_train, cv_folds=cv_folds, random_state=random_state
        )
        cv_results[name] = cv_metrics

        pipeline.fit(X_train, y_train)
        probabilities = pipeline.predict_proba(X_test)[:, 1]
        metrics = evaluate_predictions(y_test, probabilities, threshold=0.5)
        test_results[name] = metrics
        test_probabilities[name] = probabilities
        fitted[name] = pipeline

        fpr, tpr, _ = roc_curve(y_test, probabilities)
        precision, recall, _ = precision_recall_curve(y_test, probabilities)
        full_curves[name] = {
            "fpr": fpr,
            "tpr": tpr,
            "recall": recall,
            "precision": precision,
            "auc": metrics["roc_auc"],
            "ap": metrics["pr_auc"],
        }
        logger.info(
            "  %s | CV ROC-AUC %.4f +/- %.4f | test ROC-AUC %.4f | test F1 %.4f",
            name,
            cv_metrics["roc_auc"]["mean"],
            cv_metrics["roc_auc"]["std"],
            metrics["roc_auc"],
            metrics["f1"],
        )

    best_name = max(
        models,
        key=lambda n: (
            cv_results[n]["roc_auc"]["mean"],
            cv_results[n]["pr_auc"]["mean"],
            cv_results[n]["f1"]["mean"],
        ),
    )
    best_pipeline = fitted[best_name]
    logger.info(
        "Selected model: %s (CV ROC-AUC %.4f)", best_name, cv_results[best_name]["roc_auc"]["mean"]
    )

    # ----------------------------- threshold ----------------------------- #
    cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
    oof = cross_val_predict(
        build_pipeline(best_name),
        X_train,
        y_train,
        cv=cv,
        method="predict_proba",
        n_jobs=1,
    )[:, 1]
    threshold_info = tune_threshold(y_train, oof)
    threshold = threshold_info["threshold"]
    # Align the low-risk boundary with the operating threshold so a customer is
    # never simultaneously "low risk" and predicted to churn.
    bands = risk_bands_for_threshold(threshold)
    final_test = evaluate_predictions(y_test, test_probabilities[best_name], threshold=threshold)
    logger.info(
        "Tuned threshold %.2f -> test F1 %.4f, recall %.4f, precision %.4f",
        threshold,
        final_test["f1"],
        final_test["recall"],
        final_test["precision"],
    )

    # --------------------------- explainability -------------------------- #
    background = X_train.sample(min(200, len(X_train)), random_state=random_state)
    explainer = ChurnExplainer(best_pipeline, background)
    explain_sample = X_test.sample(min(shap_sample, len(X_test)), random_state=random_state)
    logger.info(
        "Computing SHAP explanations (%s, %d rows) ...", explainer.kind, len(explain_sample)
    )
    shap_result = explainer.explain(explain_sample)
    global_shap = explainer.global_importance(shap_result, top_n=None, aggregate=True)
    global_shap_encoded = explainer.global_importance(shap_result, top_n=25, aggregate=False)
    native_rows = native_importance(best_pipeline)
    logger.info("Top driver: %s", global_shap[0]["label"] if global_shap else "n/a")

    # ------------------------- score all customers ----------------------- #
    logger.info("Scoring the full customer base ...")
    all_probabilities = best_pipeline.predict_proba(df[config.FEATURE_COLUMNS])[:, 1]
    scored = pd.DataFrame(
        {
            "customerID": df[config.ID_COLUMN],
            "actual_churn": df[config.TARGET],
            "churn_probability": np.round(all_probabilities, 6),
            "risk_level": [probability_to_risk(float(p), bands) for p in all_probabilities],
            "predicted_churn": (all_probabilities >= threshold).astype(int),
            "tenure": df["tenure"].astype(int),
            "Contract": df["Contract"],
            "InternetService": df["InternetService"],
            "PaymentMethod": df["PaymentMethod"],
            "MonthlyCharges": df["MonthlyCharges"].round(2),
        }
    )
    financial = [
        financial_impact(float(m), float(p))
        for m, p in zip(df["MonthlyCharges"], all_probabilities, strict=True)
    ]
    scored["annual_revenue_at_risk"] = [row["annual_revenue_at_risk"] for row in financial]
    scored["estimated_clv"] = [row["estimated_clv"] for row in financial]
    scored["top_driver"] = ""
    scored["top_driver_source"] = ""

    # Per-customer SHAP for the customers the retention team will actually call.
    if explainer.kind != "permutation":
        candidates = scored[scored["risk_level"].isin(["high", "medium"])].sort_values(
            "churn_probability", ascending=False
        )
        if len(candidates):
            candidate_features = df.loc[candidates.index, config.FEATURE_COLUMNS]
            candidate_shap = explainer.explain(candidate_features)
            for position, (row_index, _) in enumerate(candidates.iterrows()):
                drivers = explainer.top_drivers(
                    df.loc[row_index, config.FEATURE_COLUMNS],
                    candidate_shap.values[position],
                    k=3,
                )
                # Only a risk-increasing factor belongs in the outbound work
                # queue; a protective factor would mislead retention agents.
                primary = next((driver for driver in drivers if driver["contribution"] > 0), None)
                if primary:
                    scored.at[row_index, "top_driver"] = primary["label"]
                    scored.at[row_index, "top_driver_source"] = primary["source"]

    scored = scored.sort_values("churn_probability", ascending=False).reset_index(drop=True)
    scored_path = processed_dir / "scored_customers.csv"
    scored.to_csv(scored_path, index=False)

    risk_counts = scored["risk_level"].value_counts().to_dict()

    # ------------------------------ metadata ----------------------------- #
    trained_at = datetime.now(UTC).isoformat(timespec="seconds")
    json_curves = {
        name: curve_points(y_test, probabilities)
        for name, probabilities in test_probabilities.items()
    }
    metadata: dict[str, Any] = {
        "model_version": f"v1-{trained_at[:10]}",
        "trained_at": trained_at,
        "model_name": best_name,
        "model_display_name": config.MODEL_DISPLAY_NAMES.get(best_name, best_name),
        "model_description": config.MODEL_DESCRIPTIONS.get(best_name, ""),
        "selection_metric": "roc_auc",
        "selection_reason": (
            f"Highest mean ROC-AUC across {cv_folds}-fold stratified cross-validation "
            "(tie-break: PR-AUC, then F1)."
        ),
        "cv_folds": cv_folds,
        "test_size": test_size,
        "random_state": random_state,
        "threshold": threshold,
        "threshold_selection": {
            "method": "F1 maximisation on out-of-fold predictions",
            **threshold_info,
        },
        "dataset": {
            **fingerprint,
            "source": "IBM Telco Customer Churn (Kaggle: blastchar/telco-customer-churn)",
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
            "train_churn_rate": round(float(y_train.mean()), 4),
            "test_churn_rate": round(float(y_test.mean()), 4),
            "positive_class": "Churn = Yes",
        },
        "features": {
            "raw_numeric": config.NUMERIC_FEATURES,
            "raw_categorical": config.CATEGORICAL_FEATURES,
            "encoded_count": len(feature_names(best_pipeline)),
            "notes": (
                "Service-count features are derived from the raw columns: "
                "NumServices counts subscribed services; SupportServices counts "
                "security/backup/protection/support add-ons; StreamingServices counts "
                "TV and movie add-ons; IsNewCustomer = tenure <= 6; HasFamily = "
                "Partner or Dependents. Ratio features were excluded to avoid "
                "collinearity-driven, counter-intuitive SHAP attributions."
            ),
        },
        "cv_results": cv_results,
        "test_results": test_results,
        "final_test_metrics": final_test,
        "pr_baseline": round(float(y_test.mean()), 4),
        "global_importance": global_shap,
        "global_importance_encoded": global_shap_encoded,
        "native_importance": native_rows,
        "explainability": {
            "kind": explainer.kind,
            "method": {
                "tree": "TreeSHAP (exact, game-theoretic)",
                "linear": "LinearSHAP (exact for linear models)",
                "permutation": "Permutation SHAP (model agnostic)",
            }[explainer.kind],
            "shap_rows": int(len(explain_sample)),
            "native_method": (
                "Coefficients"
                if native_rows and native_rows[0]["kind"] == "coefficient"
                else "Impurity/gain feature importance"
                if native_rows
                else "Not available"
            ),
            "caveat": (
                "SHAP values are conditional on the other features, not marginal "
                "causal effects. A feature with a positive marginal association "
                "(for example monthly charges) can have a negative contribution for "
                "a customer whose service mix already explains the risk. Use "
                "top_risk_driver for customer-facing copy."
            ),
        },
        "risk_bands": risk_band_details(bands),
        "risk_distribution": {k: int(v) for k, v in risk_counts.items()},
        "curves": json_curves,
        "binary_metrics_note": (
            "test_results are at threshold 0.5 for fair model comparison; "
            "final_test_metrics use the tuned threshold."
        ),
        "libraries": _versions(),
    }

    # ------------------------------- figures ----------------------------- #
    figures: list[str] = []
    if make_figures:
        from . import plots

        logger.info("Generating figures ...")
        figure_dir.mkdir(parents=True, exist_ok=True)
        figures.append(
            str(plots.plot_model_comparison(cv_results, figure_dir / "model_comparison.png"))
        )
        figures.append(str(plots.plot_roc_curves(full_curves, figure_dir / "roc_curves.png")))
        figures.append(
            str(
                plots.plot_pr_curves(
                    full_curves, figure_dir / "pr_curves.png", float(y_test.mean())
                )
            )
        )
        figures.append(
            str(
                plots.plot_confusion_matrix(
                    final_test["confusion"],
                    figure_dir / "confusion_matrix.png",
                    f"{config.MODEL_DISPLAY_NAMES.get(best_name, best_name)} - test set",
                )
            )
        )
        figures.append(
            str(
                plots.plot_calibration(
                    {
                        name: (np.asarray(y_test), probabilities)
                        for name, probabilities in test_probabilities.items()
                    },
                    figure_dir / "calibration.png",
                )
            )
        )
        figures.append(
            str(
                plots.plot_threshold_analysis(
                    y_test.to_numpy(),
                    test_probabilities[best_name],
                    threshold,
                    figure_dir / "threshold_analysis.png",
                )
            )
        )
        figures.append(str(plots.plot_shap_beeswarm(shap_result, figure_dir / "shap_summary.png")))
        figures.append(str(plots.plot_shap_bar(global_shap, figure_dir / "shap_importance.png")))
        if native_rows:
            title = (
                "Logistic Regression coefficients (signed)"
                if native_rows[0]["kind"] == "coefficient"
                else f"Native feature importance - {config.MODEL_DISPLAY_NAMES.get(best_name, best_name)}"
            )
            figures.append(
                str(
                    plots.plot_native_importance(
                        native_rows, figure_dir / "feature_importance.png", title
                    )
                )
            )
            figures.append(
                str(
                    plots.plot_global_importance_comparison(
                        native_rows, global_shap, figure_dir / "importance_agreement.png"
                    )
                )
            )
        figures.append(str(plots.plot_churn_segments(df, figure_dir / "churn_by_segment.png")))
        figures.append(
            str(
                plots.plot_risk_distribution(
                    all_probabilities, figure_dir / "risk_distribution.png", bands=bands
                )
            )
        )

        # Example explanation for the riskiest test customer.
        if len(explain_sample):
            example_index = int(np.argmax(best_pipeline.predict_proba(X_test)[:, 1]))
            example = X_test.iloc[[example_index]]
            example_drivers, _ = explainer.explain_customer(example.iloc[0].to_dict(), k=8)
            example_probability = float(best_pipeline.predict_proba(example)[0, 1])
            figures.append(
                str(
                    plots.plot_local_explanation(
                        example_drivers,
                        figure_dir / "example_explanation.png",
                        f"Why customer {ids_test.iloc[example_index]} is at risk "
                        f"(P(churn) = {example_probability:.0%})",
                    )
                )
            )

    metadata["figures"] = [str(Path(f).relative_to(report_dir)) for f in figures]
    metadata["artifacts"] = {
        "model": str(model_path),
        "metadata": str(metadata_path),
        "scored_customers": str(scored_path),
    }

    # ---------------------------- persist -------------------------------- #
    bundle = {
        "format_version": 1,
        "trained_at": trained_at,
        "model_name": best_name,
        "model_version": metadata["model_version"],
        "pipeline": best_pipeline,
        "threshold": threshold,
        "background": background[config.FEATURE_COLUMNS].copy(),
        "feature_columns": list(config.FEATURE_COLUMNS),
        "explainer_kind": explainer.kind,
        "metadata": metadata,
    }
    save_bundle(bundle, model_path)
    write_metadata(metadata, metadata_path)
    write_metadata(metadata, report_dir / "metrics.json")

    flatten_cv_results(cv_results).to_csv(report_dir / "cv_results.csv")
    pd.DataFrame(test_results).T.to_csv(report_dir / "test_results.csv")

    cv_table = cv_summary_table(cv_results)
    test_table = pd.DataFrame(
        [
            {
                "Model": config.MODEL_DISPLAY_NAMES.get(name, name),
                "ROC-AUC": f"{m['roc_auc']:.4f}",
                "PR-AUC": f"{m['pr_auc']:.4f}",
                "F1": f"{m['f1']:.4f}",
                "Recall": f"{m['recall']:.4f}",
                "Precision": f"{m['precision']:.4f}",
                "Brier": f"{m['brier']:.4f}",
            }
            for name, m in test_results.items()
        ]
    )
    (report_dir / "model_card.md").write_text(
        _model_card(best_name, metadata, cv_table, test_table, figures), encoding="utf-8"
    )

    runtime = time.perf_counter() - started
    metadata["training_seconds"] = round(runtime, 1)
    # Rewrite with runtime included (cheap, keeps the artifact self-describing).
    write_metadata(metadata, metadata_path)
    write_metadata(metadata, report_dir / "metrics.json")
    bundle["metadata"] = metadata
    save_bundle(bundle, model_path)

    logger.info("=" * 72)
    logger.info("Training complete in %.1fs", runtime)
    logger.info(
        "Best model: %s | CV ROC-AUC %.4f | test ROC-AUC %.4f | threshold %.2f",
        best_name,
        cv_results[best_name]["roc_auc"]["mean"],
        final_test["roc_auc"],
        threshold,
    )
    logger.info("Artifacts: %s", artifact_dir)
    logger.info("Reports:   %s", report_dir)
    logger.info("=" * 72)

    return {
        "model_name": best_name,
        "threshold": threshold,
        "metadata": metadata,
        "cv_results": cv_results,
        "test_results": test_results,
        "artifacts": {
            "model": str(model_path),
            "metadata": str(metadata_path),
            "scored_customers": str(scored_path),
            "figures": figures,
            "model_card": str(report_dir / "model_card.md"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data", type=Path, default=None, help="Path to the raw CSV.")
    parser.add_argument("--artifacts", type=Path, default=None, help="Artifact output directory.")
    parser.add_argument("--reports", type=Path, default=None, help="Report output directory.")
    parser.add_argument("--processed", type=Path, default=None, help="Processed data directory.")
    parser.add_argument("--cv-folds", type=int, default=config.CV_FOLDS)
    parser.add_argument("--test-size", type=float, default=config.TEST_SIZE)
    parser.add_argument("--models", nargs="+", choices=config.MODEL_NAMES, default=None)
    parser.add_argument("--shap-sample", type=int, default=300)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    result = train(
        args.data,
        artifact_dir=args.artifacts,
        report_dir=args.reports,
        processed_dir=args.processed,
        cv_folds=args.cv_folds,
        test_size=args.test_size,
        models=args.models,
        make_figures=not args.no_figures,
        shap_sample=args.shap_sample,
    )
    print(json.dumps({"model": result["model_name"], "threshold": result["threshold"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
