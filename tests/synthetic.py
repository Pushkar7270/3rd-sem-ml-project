"""Synthetic Telco-shaped data used by the test-suite (no network required)."""

from __future__ import annotations

import numpy as np
import pandas as pd

INTERNET_ADDONS = [
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
]


def make_synthetic_raw(n: int = 180, seed: int = 7) -> pd.DataFrame:
    """Create a small, schema-compatible dataset with both churn classes.

    The generative process makes month-to-month fiber customers with short
    tenure and high charges more likely to churn, so models can learn signal
    and the recommendation rules can be exercised.
    """
    rng = np.random.default_rng(seed)

    contract = rng.choice(["Month-to-month", "One year", "Two year"], size=n, p=[0.5, 0.3, 0.2])
    internet = rng.choice(["DSL", "Fiber optic", "No"], size=n, p=[0.35, 0.45, 0.2])
    tenure = rng.integers(0, 72, size=n)
    monthly = np.round(rng.uniform(20, 115, size=n), 2)
    senior = rng.integers(0, 2, size=n)
    phone = rng.choice(["Yes", "No"], size=n, p=[0.9, 0.1])

    logit = (
        -1.4
        + 1.35 * (contract == "Month-to-month")
        + 0.65 * (internet == "Fiber optic")
        + 0.018 * (monthly - 65)
        - 0.045 * (tenure - 20)
    )
    probability = 1.0 / (1.0 + np.exp(-logit))
    churn = rng.binomial(1, probability)
    churn[:8] = 1
    churn[8:16] = 0

    frame = pd.DataFrame(
        {
            "customerID": [f"TEST-{i:04d}" for i in range(n)],
            "gender": rng.choice(["Female", "Male"], size=n),
            "SeniorCitizen": senior,
            "Partner": rng.choice(["Yes", "No"], size=n),
            "Dependents": rng.choice(["Yes", "No"], size=n, p=[0.3, 0.7]),
            "tenure": tenure,
            "PhoneService": phone,
            "MultipleLines": [
                "No phone service" if p == "No" else ("Yes" if rng.random() < 0.4 else "No")
                for p in phone
            ],
            "InternetService": internet,
            "Contract": contract,
            "PaperlessBilling": rng.choice(["Yes", "No"], size=n),
            "PaymentMethod": rng.choice(
                [
                    "Electronic check",
                    "Mailed check",
                    "Bank transfer (automatic)",
                    "Credit card (automatic)",
                ],
                size=n,
            ),
            "MonthlyCharges": monthly,
        }
    )

    for column in INTERNET_ADDONS:
        frame[column] = [
            "No internet service" if service == "No" else ("Yes" if rng.random() < 0.4 else "No")
            for service in internet
        ]

    total = np.round(monthly * tenure + rng.normal(0, 15, size=n), 2)
    total = np.maximum(total, 0)
    frame["TotalCharges"] = total.astype(object)
    # Mimic the real dataset's blank TotalCharges for brand-new customers.
    blank = (tenure == 0) & (rng.random(n) < 0.6)
    frame.loc[blank, "TotalCharges"] = ""
    frame["Churn"] = np.where(churn == 1, "Yes", "No")

    ordered = [
        "customerID",
        "gender",
        "SeniorCitizen",
        "Partner",
        "Dependents",
        "tenure",
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
        "MonthlyCharges",
        "TotalCharges",
        "Churn",
    ]
    return frame[ordered]


def high_risk_payload() -> dict:
    """A customer that every retention rule should fire for."""
    return {
        "customerID": "TEST-HIGH",
        "gender": "Female",
        "SeniorCitizen": 1,
        "Partner": "No",
        "Dependents": "No",
        "tenure": 2,
        "PhoneService": "Yes",
        "MultipleLines": "Yes",
        "InternetService": "Fiber optic",
        "OnlineSecurity": "No",
        "OnlineBackup": "No",
        "DeviceProtection": "No",
        "TechSupport": "No",
        "StreamingTV": "Yes",
        "StreamingMovies": "Yes",
        "Contract": "Month-to-month",
        "PaperlessBilling": "Yes",
        "PaymentMethod": "Electronic check",
        "MonthlyCharges": 105.0,
        "TotalCharges": 210.0,
    }


def low_risk_payload() -> dict:
    return {
        "customerID": "TEST-LOW",
        "gender": "Male",
        "SeniorCitizen": 0,
        "Partner": "Yes",
        "Dependents": "Yes",
        "tenure": 60,
        "PhoneService": "Yes",
        "MultipleLines": "No",
        "InternetService": "DSL",
        "OnlineSecurity": "Yes",
        "OnlineBackup": "Yes",
        "DeviceProtection": "Yes",
        "TechSupport": "Yes",
        "StreamingTV": "No",
        "StreamingMovies": "No",
        "Contract": "Two year",
        "PaperlessBilling": "No",
        "PaymentMethod": "Credit card (automatic)",
        "MonthlyCharges": 35.0,
        "TotalCharges": 2100.0,
    }
