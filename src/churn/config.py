"""Central configuration for the churn prediction system.

All paths, column definitions, risk bands and model hyper-parameters live here so
that training, evaluation, the recommendation engine and the API stay in sync.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ROOT_DIR = Path(__file__).resolve().parents[2]

DATA_PATH = Path(
    os.getenv("CHURN_DATA_PATH", ROOT_DIR / "data" / "raw" / "Telco-Customer-Churn.csv")
)
PROCESSED_DIR = Path(os.getenv("CHURN_PROCESSED_DIR", ROOT_DIR / "data" / "processed"))
ARTIFACT_DIR = Path(os.getenv("CHURN_ARTIFACT_DIR", ROOT_DIR / "artifacts"))
REPORT_DIR = Path(os.getenv("CHURN_REPORT_DIR", ROOT_DIR / "reports"))
FIGURE_DIR = REPORT_DIR / "figures"

MODEL_PATH = ARTIFACT_DIR / "model.joblib"
METADATA_PATH = ARTIFACT_DIR / "metadata.json"
SCORED_CUSTOMERS_PATH = PROCESSED_DIR / "scored_customers.csv"
MODEL_CARD_PATH = REPORT_DIR / "model_card.md"

# --------------------------------------------------------------------------- #
# Reproducibility
# --------------------------------------------------------------------------- #
RANDOM_STATE = 42
TEST_SIZE = 0.20
CV_FOLDS = 5
N_JOBS = -1

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
ID_COLUMN = "customerID"
TARGET = "churn"
TARGET_RAW = "Churn"

SERVICE_COLUMNS = [
    "PhoneService",
    "MultipleLines",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
]

SUPPORT_COLUMNS = ["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport"]
STREAMING_COLUMNS = ["StreamingTV", "StreamingMovies"]

NUMERIC_FEATURES = [
    "SeniorCitizen",
    "tenure",
    "MonthlyCharges",
    "TotalCharges",
    "NumServices",
    "SupportServices",
    "StreamingServices",
    "IsNewCustomer",
    "HasFamily",
]

CATEGORICAL_FEATURES = [
    "gender",
    "Partner",
    "Dependents",
    "PhoneService",
    "MultipleLines",
    "InternetService",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
    "Contract",
    "PaperlessBilling",
    "PaymentMethod",
]

FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Human friendly names used in explanations and the UI.
FEATURE_LABELS = {
    "gender": "Gender",
    "SeniorCitizen": "Senior citizen",
    "Partner": "Partner",
    "Dependents": "Dependents",
    "tenure": "Tenure (months)",
    "PhoneService": "Phone service",
    "MultipleLines": "Multiple lines",
    "InternetService": "Internet service",
    "OnlineSecurity": "Online security",
    "OnlineBackup": "Online backup",
    "DeviceProtection": "Device protection",
    "TechSupport": "Tech support",
    "StreamingTV": "Streaming TV",
    "StreamingMovies": "Streaming movies",
    "Contract": "Contract",
    "PaperlessBilling": "Paperless billing",
    "PaymentMethod": "Payment method",
    "MonthlyCharges": "Monthly charges ($)",
    "TotalCharges": "Total charges ($)",
    "NumServices": "Number of services",
    "SupportServices": "Support services",
    "StreamingServices": "Streaming services",
    "IsNewCustomer": "New customer (<= 6 months)",
    "HasFamily": "Has partner or dependents",
}

# --------------------------------------------------------------------------- #
# Risk scoring
# --------------------------------------------------------------------------- #
# Ordered (name, lower_bound_inclusive, upper_bound_exclusive) tuples.
RISK_BANDS: tuple[tuple[str, float, float], ...] = (
    ("low", 0.00, 0.35),
    ("medium", 0.35, 0.60),
    ("high", 0.60, 1.0001),
)

RISK_COLORS = {"low": "#2e7d32", "medium": "#f9a825", "high": "#c62828"}

# Annual revenue at risk assumes 12 billing cycles at the current monthly rate.
MONTHS_PER_YEAR = 12
MAX_EXPECTED_REMAINING_MONTHS = 72

# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
MODEL_NAMES = [
    "LogisticRegression",
    "DecisionTree",
    "RandomForest",
    "XGBoost",
    "KNN",
    "SVM",
]

MODEL_DISPLAY_NAMES = {
    "LogisticRegression": "Logistic Regression",
    "DecisionTree": "Decision Tree",
    "RandomForest": "Random Forest",
    "XGBoost": "XGBoost (Gradient Boosting)",
    "KNN": "K-Nearest Neighbours",
    "SVM": "Support Vector Machine",
}

MODEL_DESCRIPTIONS = {
    "LogisticRegression": "Linear baseline; interpretable coefficients.",
    "DecisionTree": "Rule-based tree; easy to explain but high variance.",
    "RandomForest": "Bagged trees; strong tabular performance and feature importance.",
    "XGBoost": "Gradient boosted trees; usually the strongest tabular classifier.",
    "KNN": "Distance based; sensitive to feature scaling.",
    "SVM": "RBF-kernel margin classifier with probability calibration.",
}

SCORING_METRICS = {
    "roc_auc": "roc_auc",
    "pr_auc": "average_precision",
    "accuracy": "accuracy",
    "precision": "precision",
    "recall": "recall",
    "f1": "f1",
}

# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
API_TITLE = "Telco Churn Intelligence API"
API_VERSION = "1.0.0"
CORS_ORIGINS = os.getenv("CHURN_CORS_ORIGINS", "*").split(",")
MAX_BATCH_SIZE = 1000
