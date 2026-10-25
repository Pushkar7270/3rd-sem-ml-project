# Telco Churn Intelligence

An end-to-end, explainable customer-churn system built on the **IBM Telco Customer Churn** dataset. It scores every customer, explains *why* they are at risk with SHAP, converts risk into business-friendly bands, and generates a personalised retention playbook — served through a documented FastAPI backend.

<p align="left">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="scikit-learn" src="https://img.shields.io/badge/scikit--learn-1.9-F7931E?logo=scikitlearn&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green">
</p>

---

## 1. What the system does

| Capability | Implementation |
| --- | --- |
| Predict churn | Six classifiers compared with stratified 5-fold CV; final model chosen on ROC-AUC |
| Quantify risk | Calibrated-style churn probability + `low` / `medium` / `high` risk bands |
| Explain predictions | Global and per-customer SHAP, native coefficients/importances, EDA |
| Find likely leavers | Ranked `/customers/high-risk` endpoint over the scored customer book |
| Retain customers | 14-rule playbook driven by risk level and SHAP drivers, ranked by priority |
| Serve a frontend | FastAPI + OpenAPI docs, field specification, EDA JSON, static report figures |
| Prove quality | 148 automated tests, lint-clean, reproducible training artifacts |

### Results at a glance

Trained on 5,634 customers, evaluated on a held-out set of 1,409 customers (26.5% churn).

| Model | CV ROC-AUC (5-fold) | Test ROC-AUC | Test F1 @0.5 | Test PR-AUC | Test Brier |
| --- | --- | --- | --- | --- | --- |
| **Logistic Regression** (selected) | **0.8475 ± 0.0118** | **0.8456** | 0.5854 | 0.6519 | **0.1362** |
| XGBoost (Gradient Boosting) | 0.8409 ± 0.0102 | 0.8397 | 0.5929 | 0.6557 | 0.1376 |
| Random Forest | 0.8359 ± 0.0106 | 0.8337 | 0.5676 | 0.6396 | 0.1399 |
| Decision Tree | 0.8265 ± 0.0101 | 0.8335 | 0.5607 | 0.6270 | 0.1396 |
| K-Nearest Neighbours | 0.8117 ± 0.0138 | 0.8058 | 0.5722 | 0.5857 | 0.1528 |
| Support Vector Machine | 0.7984 ± 0.0168 | 0.7946 | 0.5292 | 0.6219 | 0.1459 |

At the deployed threshold (**0.32**, tuned on out-of-fold predictions for F1):

| Metric | Value |
| --- | --- |
| ROC-AUC | 0.8456 |
| PR-AUC | 0.6519 |
| Recall | 0.7406 (277 of 374 churners caught) |
| Precision | 0.5410 |
| F1 | 0.6253 |
| Accuracy | 0.7644 |
| Brier score | 0.1362 |

**Risk distribution:** 4,552 low (64.6%), 1,489 medium (21.1%), 1,002 high (14.2%).

**Top churn drivers (mean |SHAP|):** internet service, contract type, tenure, monthly charges, streaming services, payment method, new-customer status, online security.

> Logistic Regression won on the pre-registered selection metric (5-fold CV ROC-AUC). XGBoost was close (~0.007 ROC-AUC behind), so the extra nonlinearity did not justify its complexity on this dataset; the linear model is also easier to explain. Selection was not changed after seeing test results.

---

## 2. Architecture

```text
                    ┌─────────────────────────────────────────────┐
  Frontend / curl ──▶│              FastAPI backend                │
                    │  /predict  /predict/batch  /customers/*     │
                    │  /model/*  /eda/summary     /figures/*       │
                    └──────────────────┬──────────────────────────┘
                                       │
                            ┌──────────▼──────────┐
                            │    ChurnService     │
                            │  scoring + explain  │
                            │  + recommendations  │
                            └────┬───────────┬────┘
                                 │           │
            ┌────────────────────▼──┐   ┌────▼─────────────────────┐
            │ artifacts/model.joblib│   │ data/processed/          │
            │ pipeline + threshold  │   │ scored_customers.csv     │
            │ background + metadata │   │ raw Telco CSV            │
            └───────────────────────┘   └──────────────────────────┘
```

### Project layout

```text
.
├── src/churn/
│   ├── config.py          # paths, schema, risk bands, model config
│   ├── data.py            # loading, cleaning, feature engineering, split
│   ├── features.py        # preprocessing + six model pipelines
│   ├── train.py           # CV comparison, threshold tuning, artifacts, reports
│   ├── evaluate.py        # metrics, threshold selection, curve points
│   ├── explain.py         # SHAP wrapper, drivers, native importance
│   ├── risk.py            # risk bands + revenue/CLV estimates
│   ├── recommend.py       # retention playbook engine
│   ├── plots.py           # all report figures
│   ├── artifacts.py       # atomic bundle persistence + validation
│   └── api/
│       ├── main.py        # FastAPI app factory and routes
│       ├── service.py     # framework-agnostic application service
│       └── schemas.py     # Pydantic contracts + frontend field spec
├── scripts/download_data.py
├── tests/                 # 148 unit, contract and integration tests
├── artifacts/             # generated model.joblib + metadata.json
├── data/                  # raw + scored data (gitignored)
├── reports/               # model card, metrics, 13 figures (gitignored)
├── Makefile
└── pyproject.toml
```

---

## 3. Quickstart

Requires **Python 3.12** and [uv](https://docs.astral.sh/uv/).

```bash
# 1. Install dependencies (creates .venv)
uv sync

# 2. Download the IBM Telco dataset (7,043 rows) into data/raw/
uv run python scripts/download_data.py

# 3. Train, evaluate, explain, score all customers, write reports
uv run churn-train          # ~40 seconds on a laptop

# 4. Serve the API
uv run churn-serve          # http://127.0.0.1:8000  (docs at /docs)
```

Or use the shortcuts:

```bash
make setup     # uv sync + download dataset
make train
make serve
make test
make lint
```

Environment variables: `CHURN_PORT` (default `8000`), `CHURN_HOST` (`127.0.0.1`), `CHURN_RELOAD=1`, `CHURN_CORS_ORIGINS`, `CHURN_DATA_PATH`, `CHURN_ARTIFACT_DIR`, `CHURN_REPORT_DIR`.

---

## 4. Machine-learning design

### Dataset and cleaning

- **Source:** [IBM Telco Customer Churn](https://www.kaggle.com/datasets/blastchar/telco-customer-churn) — 7,043 customers, 21 raw columns, 26.5% churn.
- `customerID` is an identifier, never a feature.
- `TotalCharges` contains 11 blank strings for customers with `tenure = 0`. These are **semantic zeros** (lifetime spend is genuinely zero), not missing-at-random, so they are filled with `0` instead of the median.
- Target mapped `Yes → 1`, `No → 0`; no duplicate customers.

### Engineered features

| Feature | Definition | Rationale |
| --- | --- | --- |
| `NumServices` | Count of subscribed services | Product depth / switching cost |
| `SupportServices` | Security + backup + device protection + tech support | Service stickiness |
| `StreamingServices` | Streaming TV + movies | Entertainment bundle behaviour |
| `IsNewCustomer` | `tenure ≤ 6` | First six months are highest-risk |
| `HasFamily` | Partner or dependents | Household stability |

No ratio features (`TotalCharges / tenure`) were used in the final model: they are almost perfectly collinear with tenure and monthly charges, and produced unstable, counter-intuitive logistic coefficients and SHAP attributions. The simpler feature set lost less than 0.001 ROC-AUC.

### Pipeline (leak-free by construction)

Every model is a single scikit-learn `Pipeline`:

```text
numeric  → median imputation → StandardScaler
categorical → most-frequent imputation → OneHotEncoder(handle_unknown="ignore")
→ classifier
```

Cross-validation clones the whole pipeline, so imputers, scalers and encoders are fitted **inside each fold**. Unseen categories at serving time are ignored rather than crashing the service.

### Model comparison protocol

1. Stratified 80/20 train–test split (`random_state=42`).
2. Stratified **5-fold CV on the training set only**, scoring ROC-AUC (primary), PR-AUC, accuracy, precision, recall and F1.
3. Highest mean CV ROC-AUC wins (tie-break: PR-AUC, then F1).
4. Decision threshold tuned on **out-of-fold** predictions to maximise F1.
5. Final model evaluated once on the untouched test set.
6. Full customer base scored with the final model for the risk dashboard.

Default hyper-parameters are deliberately comparable across models (e.g. `RandomForest(n_estimators=400, min_samples_leaf=2)`, `XGBoost(n_estimators=400, lr=0.05, max_depth=4)`, `KNN(k=25, distance-weighted)`, Platt-calibrated RBF SVM). The point of the study is a fair model-family comparison, not per-model tuning.

### Why the threshold is 0.32

The dataset is imbalanced (26.5% churn) and retention capacity is finite. At 0.5 the model catches 52.7% of churners with 65.9% precision; at 0.32 it catches **74.1%** with 54.1% precision. Missing a churner is usually more expensive than a wasted save offer, so the higher-recall operating point is the default. The threshold is stored in the artifact and returned with every prediction so the frontend can display or override it. Risk bands are derived from the same threshold, so a customer can never be both “low risk” and “predicted to churn”.

---

## 5. Explainability

| Method | Scope | Notes |
| --- | --- | --- |
| SHAP (`LinearSHAP`) | Final model | Exact for the selected logistic regression |
| SHAP (`TreeSHAP`) | Tree models | Used automatically if RF/XGBoost/DT is selected |
| Permutation SHAP | KNN/SVM fallback | Model-agnostic, sampled for runtime |
| Coefficients | Logistic regression | Signed log-odds, globally interpretable |
| Impurity/gain importance | Tree models | Native feature importance |
| EDA | Dataset | Churn rates by contract, internet, payment, tenure |

Global figures: `shap_summary.png` (beeswarm), `shap_importance.png` (aggregated by source), `feature_importance.png` (native model importance), `importance_agreement.png` (native vs SHAP).

Per-customer explanations collapse one-hot columns back to the **category the customer actually holds**, so the response never reports “Fiber optic” for a customer with no internet. The top five signed contributions look like this:

```json
{
  "source": "tenure",
  "label": "Tenure (months)",
  "value": 2,
  "contribution": 0.7793,
  "impact": "increases"
}
```

`top_risk_driver` is the strongest **risk-increasing** factor and is what the work queue and summary use; `top_drivers` keeps the full ranked list (including protective factors for context).

> **Reading SHAP:** values are *conditional* on the other features, not marginal associations. In this dataset monthly charges correlate positively with churn, but for a new fiber customer with streaming add-ons the model already expects a high bill; the incremental price contribution can therefore be negative. Coefficients and SHAP answer “why this prediction, given the rest of the profile”, not “what happens if we raise the price by $10”. The strongest risk-increasing driver is always used for customer-facing copy.

---

## 6. Risk scoring and business value

| Level | Probability | Default treatment |
| --- | --- | --- |
| Low | `< 0.32` (deployed threshold) | Nurture track, no discounts |
| Medium | `0.32 – 0.60` | Targeted service/payment offers |
| High | `≥ 0.60` | Human outreach + save offer |

Band boundaries are model-specific and stored in the artifact; the low/medium cut-off is the tuned decision threshold, so risk level and churn prediction cannot contradict each other.

```text
annual_revenue_at_risk = MonthlyCharges × 12 × P(churn)
expected_remaining_months = min(1 / P(churn), 72)
estimated_clv = MonthlyCharges × expected_remaining_months
```

The CLV is an expected-revenue upper bound for prioritisation (no margin or discounting), not an accounting figure. Probabilities are model outputs and are **not** separately calibrated; Brier score and a reliability diagram are reported for transparency.

### Retention playbook

Recommendations are generated from risk level, contract/service attributes **and** SHAP drivers. Each has a category, action, concrete offer, expected impact, channels and priority score.

| ID | Trigger | Suggested action / offer |
| --- | --- | --- |
| RET-01 | Any scored customer | Retention specialist call within 48h |
| RET-02 | Month-to-month contract | 12/24-month plan with 15–20% loyalty discount |
| RET-03 | Fiber optic + monthly ≥ $70 | Personalised plan review + $10–20/month credit |
| RET-04 | Electronic check | Assisted autopay switch + 5% credit for 6 months |
| RET-05 | No tech support (internet customer) | 3 months complimentary TechSupport |
| RET-06 | No online security | Free OnlineSecurity for 3 months |
| RET-07 | Tenure ≤ 6 months | Welcome call day 7 + check-in day 30 |
| RET-08 | Tenure ≥ 24 months | Loyalty pricing review + named account manager |
| RET-09 | Senior citizen | Priority human support + simplified billing |
| RET-10 | Paperless bill ≥ $75 | Itemised bill review + paper option |
| RET-11 | Both streaming add-ons ≥ $80 bill | Entertainment bundle discount |
| RET-12 | No device protection (> 6 months) | 6-month DeviceProtection trial |
| RET-13 | P(churn) ≥ 0.65 | 20% off for 3 months, time-boxed save offer |
| RET-14 | Low risk | Loyalty nurture track (no discount) |

The engine returns the five highest-priority actions by default. Priority scores combine risk, whether the factor is a top-3 SHAP driver, and rule-specific business value; they are **heuristics, not causal uplift estimates**.

---

## 7. API reference

Full interactive documentation: **`/docs`** (Swagger UI) and **`/openapi.json`**.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness + loaded model/version/threshold |
| `GET` | `/model/info` | Model, dataset, risk bands, top drivers, test metrics |
| `GET` | `/model/metrics` | CV results, test results, ROC/PR curve points |
| `GET` | `/model/features` | Input field spec, defaults and example payload |
| `GET` | `/model/card` | Generated Markdown model card |
| `POST` | `/predict` | Score one customer |
| `POST` | `/predict/batch` | Score 1–1,000 customers |
| `GET` | `/customers/high-risk` | Ranked at-risk customers (default: high) |
| `GET` | `/customers/{customer_id}` | Score + explanations + playbook for one existing customer |
| `GET` | `/eda/summary` | Churn rates, distributions, correlations, risk mix |
| `GET` | `/figures` | JSON index of generated figures |
| `GET` | `/figures/*`, `/reports/*` | Generated PNG figures and reports |

### Score a customer

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "customerID": "DEMO-HIGH",
    "gender": "Female", "SeniorCitizen": 1,
    "Partner": "No", "Dependents": "No", "tenure": 2,
    "PhoneService": "Yes", "MultipleLines": "Yes",
    "InternetService": "Fiber optic",
    "OnlineSecurity": "No", "OnlineBackup": "No",
    "DeviceProtection": "No", "TechSupport": "No",
    "StreamingTV": "Yes", "StreamingMovies": "Yes",
    "Contract": "Month-to-month", "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check",
    "MonthlyCharges": 105.0, "TotalCharges": 210.0
  }'
```

```json
{
  "customer_id": "DEMO-HIGH",
  "churn_probability": 0.875164,
  "churn_prediction": true,
  "risk_level": "high",
  "threshold": 0.32,
  "top_drivers": [
    {"source": "tenure", "label": "Tenure (months)", "value": 2, "contribution": 0.7793, "impact": "increases"},
    {"source": "MonthlyCharges", "label": "Monthly charges ($)", "value": 105.0, "contribution": -0.7543, "impact": "decreases"},
    {"source": "IsNewCustomer", "label": "New customer (<= 6 months)", "value": 1, "contribution": 0.6026, "impact": "increases"}
  ],
  "top_risk_driver": {
    "source": "tenure", "label": "Tenure (months)", "value": 2,
    "contribution": 0.7793, "impact": "increases"
  },
  "recommendations": [
    {"id": "RET-03", "priority": "critical", "title": "Personalised fiber plan review",
     "offer": "$10-20/month loyalty credit or a lower-cost speed tier."},
    {"id": "RET-07", "priority": "critical", "title": "New-customer onboarding programme",
     "offer": "Onboarding concierge + first-bill walkthrough."},
    {"id": "RET-13", "priority": "high", "title": "Targeted save offer",
     "offer": "20% off for 3 months, conditional on speaking with retention."}
  ],
  "financial_impact": {
    "monthly_charges": 105.0,
    "annual_revenue_at_risk": 1102.71,
    "expected_remaining_months": 1.1,
    "estimated_clv": 119.98
  },
  "summary": "High churn risk (88%). Main risk factor: Tenure (months). ...",
  "model": {"name": "LogisticRegression", "version": "v1-2026-10-24"}
}
```

### Useful queries

```bash
# Top high-risk customers (default risk_level=high)
curl 'http://127.0.0.1:8000/customers/high-risk?limit=10'

# High risk with probability ≥ 0.8, including a specific band
curl 'http://127.0.0.1:8000/customers/high-risk?risk_level=high&min_probability=0.8'

# Existing customer with live SHAP + playbook
curl 'http://127.0.0.1:8000/customers/5178-LMXOP'

# Dashboard data
curl 'http://127.0.0.1:8000/eda/summary'
```

### Frontend integration notes

1. Build the form from `GET /model/features` (types, options, ranges, defaults). `tenure` and `MonthlyCharges` are required; other fields fall back to documented defaults.
2. `POST /predict` returns everything needed for a result card: probability, band, drivers, actions, revenue exposure. Use `top_risk_driver` for the headline reason.
3. Use `/customers/high-risk` for the work queue (`top_risk_driver`, no live SHAP) and `/customers/{id}` for the drill-down (full drivers + playbook).
4. `/eda/summary` powers KPI cards and segment charts; ROC/PR points for custom charts are in `/model/metrics`.
5. Figure URLs are listed by `GET /figures` and can be embedded directly.
6. CORS is open by default for local development; set `CHURN_CORS_ORIGINS` in production.
7. The API returns `503` with a helpful message when no trained model is present, and `422` for invalid or incomplete payloads.

---

## 8. Reports and artifacts

After `uv run churn-train`:

| Artifact | Contents |
| --- | --- |
| `artifacts/model.joblib` | Fitted pipeline, threshold, background sample, metadata |
| `artifacts/metadata.json` | Full experiment metadata and metrics |
| `reports/model_card.md` | Model card: dataset, method, metrics, drivers, limitations |
| `reports/metrics.json` | Same metadata in JSON |
| `reports/cv_results.csv` / `test_results.csv` | Model comparison tables |
| `reports/figures/` | 13 figures: comparison, ROC, PR, confusion, calibration, threshold, SHAP, importance, segments, risk mix, example explanation |
| `data/processed/scored_customers.csv` | Every customer with probability, band, predicted label, value at risk, top driver |

The bundle is versioned (`format_version`) and written atomically, so a running API never reads a partially written model. Training is deterministic for a fixed `random_state`.

---

## 9. Tests and code quality

```bash
uv run pytest -q                     # 148 tests
uv run pytest --cov=churn            # optional coverage
uv run ruff check src tests scripts  # lint
```

Coverage includes:

- data cleaning (including the 11 blank `TotalCharges` rows) and feature engineering;
- all six model pipelines, unseen categories, deterministic fits, probability outputs;
- model comparison and best-CV selection, fold counts, F1-maximising threshold tuning;
- risk-band boundaries, threshold alignment, revenue/CLV math, priority labels;
- SHAP shapes, additivity, actual-category driver mapping, native importance, tree SHAP and the permutation fallback;
- all 14 recommendation rules, ranking, limits, low-risk nurture behaviour;
- every API route, required-field validation, service normalisation, batch scoring, 404/503 paths, OpenAPI;
- artifact persistence/version validation and a fast end-to-end training run that verifies figure generation, reports, metadata consistency and scoring of every customer.

Tests use a small synthetic Telco-shaped dataset, so they run without network access or the real CSV. Real-dataset and repository-artifact tests skip automatically when those files are absent.

---

## 10. Limitations and responsible use

- **Observational data:** associations are not causal effects. Every retention offer should be validated with an A/B test or uplift model.
- **Model choice:** Logistic Regression won by ~0.007 ROC-AUC. This is plausible for this dataset but may not generalise to other markets/products.
- **Calibration:** probabilities are not post-hoc calibrated; risk bands are model-specific policy thresholds derived from the deployed cut-off. Monitor Brier score and reliability over time.
- **Class imbalance:** the default threshold optimises F1. Real decisions should use the cost of a missed churner versus a wasted offer.
- **Protected attributes:** gender and senior status are present for analysis. Use the model to target *support*, never to deny service or price discriminatorily.
- **SHAP is not causality:** it explains model behaviour, not the customer's true reason for leaving.
- **Recommendation engine:** rule-based heuristics with hand-set priorities, not learned uplift. Offers may need eligibility/cost constraints in production.
- **CLV simplification:** revenue-only, capped expected tenure, no margin or discounting.
- **Drift:** retrain when churn base rates, pricing or the product portfolio change; monitor input distributions and prediction calibration.
- **Data quality:** the public dataset is US-centric and partly synthetic; validate on local data before deployment.

---

## 11. Future work

- Hyper-parameter tuning (nested CV) and probability calibration (`CalibratedClassifierCV` / isotonic).
- Cost-sensitive threshold optimisation per retention channel.
- Uplift modelling / causal retention targeting.
- Customer-level drift and calibration monitoring, scheduled retraining.
- Persist scores and decisions in a database with audit trails.
- Docker image, authentication, rate limiting and CI pipeline.
- Frontend dashboard built against the existing `/model/features` and prediction contracts.

---

## 12. Dataset and license

- **Dataset:** IBM Telco Customer Churn, publicly available on [Kaggle](https://www.kaggle.com/datasets/blastchar/telco-customer-churn). Download script: `scripts/download_data.py`.
- **Code:** MIT — see [LICENSE](LICENSE).

Built as a 3rd-semester machine-learning project: supervised binary classification with a production-style, explainable serving layer.
