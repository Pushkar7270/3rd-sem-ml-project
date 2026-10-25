"""Pydantic request/response schemas and the frontend field specification."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .. import config

INTERNET_SERVICES = ["DSL", "Fiber optic", "No"]
ADDON_VALUES = ["Yes", "No", "No internet service"]
PAYMENT_METHODS = [
    "Electronic check",
    "Mailed check",
    "Bank transfer (automatic)",
    "Credit card (automatic)",
]
INTERNET_ADDONS = [
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
]


class CustomerInput(BaseModel):
    """Raw customer attributes used by the churn model.

    Derived features (average monthly charges, service counts, etc.) are
    calculated server-side. ``TotalCharges`` may be omitted for new customers;
    it then defaults to ``MonthlyCharges * tenure``.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "customerID": "7590-VHVEG",
                "gender": "Female",
                "SeniorCitizen": 0,
                "Partner": "Yes",
                "Dependents": "No",
                "tenure": 2,
                "PhoneService": "Yes",
                "MultipleLines": "No",
                "InternetService": "Fiber optic",
                "OnlineSecurity": "No",
                "OnlineBackup": "No",
                "DeviceProtection": "No",
                "TechSupport": "No",
                "StreamingTV": "Yes",
                "StreamingMovies": "No",
                "Contract": "Month-to-month",
                "PaperlessBilling": "Yes",
                "PaymentMethod": "Electronic check",
                "MonthlyCharges": 85.0,
                "TotalCharges": 170.0,
            }
        },
    )

    customerID: str | None = Field(None, description="Optional external identifier.")
    gender: Literal["Female", "Male"] = "Female"
    SeniorCitizen: int = Field(
        0, ge=0, le=1, strict=True, description="1 if the customer is a senior citizen."
    )
    Partner: Literal["Yes", "No"] = "No"
    Dependents: Literal["Yes", "No"] = "No"
    tenure: int = Field(12, ge=0, le=100, strict=True, description="Months as a customer.")
    PhoneService: Literal["Yes", "No"] = "Yes"
    MultipleLines: Literal["Yes", "No", "No phone service"] = "No"
    InternetService: Literal["DSL", "Fiber optic", "No"] = "Fiber optic"
    OnlineSecurity: Literal["Yes", "No", "No internet service"] = "No"
    OnlineBackup: Literal["Yes", "No", "No internet service"] = "No"
    DeviceProtection: Literal["Yes", "No", "No internet service"] = "No"
    TechSupport: Literal["Yes", "No", "No internet service"] = "No"
    StreamingTV: Literal["Yes", "No", "No internet service"] = "Yes"
    StreamingMovies: Literal["Yes", "No", "No internet service"] = "No"
    Contract: Literal["Month-to-month", "One year", "Two year"] = "Month-to-month"
    PaperlessBilling: Literal["Yes", "No"] = "Yes"
    PaymentMethod: Literal[
        "Electronic check",
        "Mailed check",
        "Bank transfer (automatic)",
        "Credit card (automatic)",
    ] = "Electronic check"
    MonthlyCharges: float = Field(70.0, ge=0, le=1000)
    TotalCharges: float | None = Field(None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def _harmonise_services(self) -> CustomerInput:
        """Keep service answers internally consistent.

        A customer without internet cannot subscribe to internet add-ons, and a
        customer without phone service cannot have multiple lines.  The API
        normalises instead of rejecting, because forms often send stale values
        when a user switches the parent option.

        ``tenure`` and ``MonthlyCharges`` are mandatory: scoring an empty or
        almost-empty payload would otherwise silently assign a fabricated
        default customer and a misleading risk level.
        """
        required_core = {"tenure", "MonthlyCharges"}
        missing = sorted(required_core - set(self.model_fields_set))
        if missing:
            raise ValueError(f"Missing required customer attributes: {', '.join(missing)}")

        if self.InternetService == "No":
            for field_name in INTERNET_ADDONS:
                setattr(self, field_name, "No internet service")
        else:
            for field_name in INTERNET_ADDONS:
                if getattr(self, field_name) == "No internet service":
                    setattr(self, field_name, "No")

        if self.PhoneService == "No":
            self.MultipleLines = "No phone service"
        elif self.MultipleLines == "No phone service":
            self.MultipleLines = "No"

        if self.TotalCharges is None:
            self.TotalCharges = round(self.MonthlyCharges * self.tenure, 2)
        return self

    def to_record(self) -> dict[str, Any]:
        return self.model_dump()


class BatchRequest(BaseModel):
    customers: list[CustomerInput] = Field(..., min_length=1, max_length=config.MAX_BATCH_SIZE)
    include_drivers: bool = True
    include_recommendations: bool = True


class DriverOut(BaseModel):
    feature: str
    label: str
    source: str
    value: str | float | int | None = None
    contribution: float
    impact: Literal["increases", "decreases"]


class RecommendationOut(BaseModel):
    id: str
    category: str
    title: str
    description: str
    action: str
    offer: str
    priority: Literal["critical", "high", "medium"]
    priority_score: int
    expected_impact: str
    channels: list[str]
    triggered_by: list[str]


class FinancialImpactOut(BaseModel):
    monthly_charges: float
    annual_revenue_at_risk: float
    expected_remaining_months: float
    estimated_clv: float


class ModelRefOut(BaseModel):
    name: str
    display_name: str
    version: str


class PredictionOut(BaseModel):
    customer_id: str | None = None
    churn_probability: float
    churn_prediction: bool
    risk_level: Literal["low", "medium", "high"]
    threshold: float
    top_drivers: list[DriverOut]
    top_risk_driver: DriverOut | None = None
    recommendations: list[RecommendationOut]
    financial_impact: FinancialImpactOut
    summary: str
    model: ModelRefOut


class BatchSummaryOut(BaseModel):
    total: int
    predicted_churners: int
    high_risk: int
    medium_risk: int
    low_risk: int
    average_probability: float
    annual_revenue_at_risk: float


class BatchPredictionOut(BaseModel):
    summary: BatchSummaryOut
    predictions: list[PredictionOut]


class HighRiskCustomerOut(BaseModel):
    customer_id: str
    churn_probability: float
    risk_level: str
    tenure: int
    contract: str
    internet_service: str
    payment_method: str
    monthly_charges: float
    annual_revenue_at_risk: float
    estimated_clv: float
    top_risk_driver: str


class HighRiskListOut(BaseModel):
    total_matching: int
    returned: int
    filters: dict[str, Any]
    customers: list[HighRiskCustomerOut]


ActionStatus = Literal["pending", "contacted", "accepted", "declined"]


class ActionCreate(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=64)
    recommendation_id: str = Field(..., min_length=1, max_length=32)
    status: ActionStatus = "pending"
    note: str | None = Field(None, max_length=1000)
    # Optional snapshot for ad-hoc scores that are not in the customer book.
    # When the customer exists, the server validates the recommendation and
    # overwrites these fields with canonical values.
    title: str | None = Field(None, max_length=300)
    offer: str | None = Field(None, max_length=500)
    risk_level: Literal["low", "medium", "high"] | None = None
    churn_probability: float | None = Field(None, ge=0.0, le=1.0)


class ActionUpdate(BaseModel):
    status: ActionStatus | None = None
    note: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _require_change(self) -> ActionUpdate:
        if self.status is None and self.note is None:
            raise ValueError("Provide at least one of status or note")
        return self


class ActionOut(BaseModel):
    id: int
    customer_id: str
    recommendation_id: str
    title: str
    offer: str
    risk_level: str
    churn_probability: float
    status: ActionStatus
    note: str | None = None
    created_at: str
    updated_at: str


class ActionListOut(BaseModel):
    total: int
    actions: list[ActionOut]


class HealthOut(BaseModel):
    status: str
    model_loaded: bool
    model_name: str | None
    model_version: str | None
    threshold: float | None
    scored_customers: int
    api_version: str


class FeedbackIn(BaseModel):
    """Close the loop: record whether a scored customer actually churned."""

    prediction_id: int = Field(..., ge=1, description="Row id returned by /history.")
    actual_churn: bool = Field(..., description="True if the customer later churned.")
    notes: str | None = Field(None, max_length=500, description="Optional reviewer note.")


# --------------------------------------------------------------------------- #
# Frontend field specification
# --------------------------------------------------------------------------- #
INPUT_FIELDS: list[dict[str, Any]] = [
    {
        "name": "customerID",
        "label": "Customer ID",
        "type": "string",
        "default": None,
        "required": False,
        "description": "Optional external identifier.",
    },
    {
        "name": "gender",
        "label": "Gender",
        "type": "select",
        "options": ["Female", "Male"],
        "default": "Female",
        "description": "Customer gender recorded on the account.",
    },
    {
        "name": "SeniorCitizen",
        "label": "Senior citizen",
        "type": "select",
        "options": [0, 1],
        "default": 0,
        "description": "1 if the customer is a senior citizen, otherwise 0.",
    },
    {
        "name": "Partner",
        "label": "Has partner",
        "type": "select",
        "options": ["Yes", "No"],
        "default": "No",
        "description": "Whether the customer lives with a partner.",
    },
    {
        "name": "Dependents",
        "label": "Has dependents",
        "type": "select",
        "options": ["Yes", "No"],
        "default": "No",
        "description": "Whether the customer has dependents.",
    },
    {
        "name": "tenure",
        "label": "Tenure (months)",
        "type": "integer",
        "min": 0,
        "max": 100,
        "default": 12,
        "required": True,
        "description": "Number of months the customer has stayed.",
    },
    {
        "name": "PhoneService",
        "label": "Phone service",
        "type": "select",
        "options": ["Yes", "No"],
        "default": "Yes",
        "description": "Whether the customer has phone service.",
    },
    {
        "name": "MultipleLines",
        "label": "Multiple lines",
        "type": "select",
        "options": ["Yes", "No", "No phone service"],
        "default": "No",
        "description": "Whether the customer has multiple phone lines.",
    },
    {
        "name": "InternetService",
        "label": "Internet service",
        "type": "select",
        "options": INTERNET_SERVICES,
        "default": "Fiber optic",
        "description": "Internet technology subscribed to.",
    },
    {
        "name": "OnlineSecurity",
        "label": "Online security",
        "type": "select",
        "options": ADDON_VALUES,
        "default": "No",
        "description": "Online security add-on.",
    },
    {
        "name": "OnlineBackup",
        "label": "Online backup",
        "type": "select",
        "options": ADDON_VALUES,
        "default": "No",
        "description": "Online backup add-on.",
    },
    {
        "name": "DeviceProtection",
        "label": "Device protection",
        "type": "select",
        "options": ADDON_VALUES,
        "default": "No",
        "description": "Device protection add-on.",
    },
    {
        "name": "TechSupport",
        "label": "Tech support",
        "type": "select",
        "options": ADDON_VALUES,
        "default": "No",
        "description": "Premium tech support add-on.",
    },
    {
        "name": "StreamingTV",
        "label": "Streaming TV",
        "type": "select",
        "options": ADDON_VALUES,
        "default": "Yes",
        "description": "Streaming TV add-on.",
    },
    {
        "name": "StreamingMovies",
        "label": "Streaming movies",
        "type": "select",
        "options": ADDON_VALUES,
        "default": "No",
        "description": "Streaming movies add-on.",
    },
    {
        "name": "Contract",
        "label": "Contract",
        "type": "select",
        "options": ["Month-to-month", "One year", "Two year"],
        "default": "Month-to-month",
        "description": "Current contract term.",
    },
    {
        "name": "PaperlessBilling",
        "label": "Paperless billing",
        "type": "select",
        "options": ["Yes", "No"],
        "default": "Yes",
        "description": "Whether billing is paperless.",
    },
    {
        "name": "PaymentMethod",
        "label": "Payment method",
        "type": "select",
        "options": PAYMENT_METHODS,
        "default": "Electronic check",
        "description": "Payment method on file.",
    },
    {
        "name": "MonthlyCharges",
        "label": "Monthly charges ($)",
        "type": "number",
        "min": 0,
        "max": 1000,
        "step": 0.05,
        "default": 70.0,
        "required": True,
        "description": "Current monthly bill.",
    },
    {
        "name": "TotalCharges",
        "label": "Total charges ($)",
        "type": "number",
        "min": 0,
        "max": 1000000,
        "step": 0.05,
        "default": None,
        "required": False,
        "description": "Lifetime charges. Leave empty to derive from tenure x monthly charges.",
    },
]

INPUT_FIELD_NAMES = {field["name"] for field in INPUT_FIELDS}
