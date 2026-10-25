"""HTTP contract tests for the FastAPI backend."""

from __future__ import annotations

import pytest

from churn import config
from churn.api.schemas import INPUT_FIELD_NAMES, CustomerInput
from tests.synthetic import high_risk_payload, low_risk_payload


def test_root_lists_endpoints(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == config.API_TITLE
    assert "predict" in body["endpoints"]


def test_health_reports_loaded_model(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["model_name"] == "LogisticRegression"
    assert body["scored_customers"] > 0
    assert 0 <= body["threshold"] <= 1


def test_model_info(client):
    body = client.get("/model/info").json()
    assert body["model"]["name"] == "LogisticRegression"
    assert body["threshold"] == 0.5
    assert len(body["risk_bands"]) == 3
    assert body["dataset"]["rows"] > 0
    assert isinstance(body["global_importance"], list)


def test_model_metrics(client):
    body = client.get("/model/metrics").json()
    assert body["selection_metric"] == "roc_auc"
    assert "LogisticRegression" in body["test_results"]
    assert body["final_test_metrics"]["roc_auc"] > 0.5
    assert body["threshold"] == 0.5


def test_model_features_match_schema(client):
    body = client.get("/model/features").json()
    names = {field["name"] for field in body["fields"]}
    assert names == set(CustomerInput.model_fields)
    assert names == INPUT_FIELD_NAMES
    for field in body["fields"]:
        assert field["label"]
        assert field["type"] in {"string", "select", "number", "integer"}
    assert body["example"]["customerID"] == "7590-VHVEG"
    assert body["defaults"]["TotalCharges"] is None
    assert body["defaults"]["tenure"] == 12
    assert set(body["required_fields"]) == {"tenure", "MonthlyCharges"}


def test_predict_returns_probability_drivers_and_playbook(client):
    response = client.post("/predict", json=high_risk_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["customer_id"] == "TEST-HIGH"
    assert 0.0 <= body["churn_probability"] <= 1.0
    assert body["risk_level"] in {"low", "medium", "high"}
    assert body["churn_prediction"] is (body["churn_probability"] >= body["threshold"])
    assert len(body["top_drivers"]) == 5
    assert body["top_risk_driver"] is not None
    assert body["top_risk_driver"]["source"] in {d["source"] for d in body["top_drivers"]}
    assert len(body["recommendations"]) > 0
    scores = [rec["priority_score"] for rec in body["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    assert body["financial_impact"]["annual_revenue_at_risk"] >= 0
    assert body["summary"]
    assert body["model"]["name"] == "LogisticRegression"

    driver = body["top_drivers"][0]
    assert driver["impact"] in {"increases", "decreases"}
    assert driver["label"]
    assert driver["source"]
    assert any(driver["source"] in config.CATEGORICAL_FEATURES for driver in body["top_drivers"])
    assert body["top_risk_driver"]["contribution"] == max(
        d["contribution"] for d in body["top_drivers"] if d["contribution"] > 0
    )

    recommendation = body["recommendations"][0]
    assert recommendation["priority"] in {"critical", "high", "medium"}
    assert recommendation["action"]


def test_predict_low_risk_and_derived_total_charges(client):
    payload = low_risk_payload()
    explicit_total = payload.pop("TotalCharges")
    body = client.post("/predict", json=payload).json()
    assert body["customer_id"] == "TEST-LOW"
    assert body["risk_level"] == "low"
    assert body["financial_impact"]["monthly_charges"] == 35.0

    with_total = client.post("/predict", json={**payload, "TotalCharges": explicit_total}).json()
    assert with_total["churn_probability"] == body["churn_probability"]


def test_predict_normalises_inconsistent_service_answers(client):
    payload = high_risk_payload()
    payload["InternetService"] = "No"
    payload["OnlineSecurity"] = "Yes"  # invalid without internet
    payload["PhoneService"] = "No"
    payload["MultipleLines"] = "Yes"  # invalid without phone

    normalised = high_risk_payload()
    normalised["InternetService"] = "No"
    normalised["PhoneService"] = "No"
    normalised["MultipleLines"] = "No phone service"
    for field in [
        "OnlineSecurity",
        "OnlineBackup",
        "DeviceProtection",
        "TechSupport",
        "StreamingTV",
        "StreamingMovies",
    ]:
        normalised[field] = "No internet service"

    first = client.post("/predict", json=payload)
    second = client.post("/predict", json=normalised)
    assert first.status_code == second.status_code == 200
    assert first.json()["churn_probability"] == second.json()["churn_probability"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tenure": 500},
        {"tenure": 5},
        {"tenure": True, "MonthlyCharges": 70},
        {"tenure": "12", "MonthlyCharges": 70},
        {"Contract": "Weekly"},
        {"InternetService": "Satellite"},
        {"MonthlyCharges": -1},
        {"unknown_field": 1},
        {"gender": "Other"},
    ],
)
def test_predict_rejects_invalid_payloads(client, payload):
    assert client.post("/predict", json=payload).status_code == 422


def test_batch_prediction(client):
    payload = {
        "customers": [high_risk_payload(), low_risk_payload()],
        "include_drivers": True,
        "include_recommendations": True,
    }
    response = client.post("/predict/batch", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["total"] == 2
    assert len(body["predictions"]) == 2
    counts = (
        body["summary"]["high_risk"] + body["summary"]["medium_risk"] + body["summary"]["low_risk"]
    )
    assert counts == 2
    assert body["summary"]["predicted_churners"] <= 2
    assert len(body["predictions"][0]["top_drivers"]) == 5


def test_batch_can_skip_explanations(client):
    payload = {
        "customers": [high_risk_payload()],
        "include_drivers": False,
        "include_recommendations": False,
    }
    body = client.post("/predict/batch", json=payload).json()
    assert body["predictions"][0]["top_drivers"] == []
    assert body["predictions"][0]["recommendations"] == []
    assert body["predictions"][0]["churn_probability"] >= 0


@pytest.mark.parametrize(
    "payload",
    [
        {"customers": []},
        {"customers": [{"tenure": -2}]},
        {"customers": [{}]},
        {"customers": [{}] * 1001},
        {},
    ],
)
def test_batch_validation(client, payload):
    assert client.post("/predict/batch", json=payload).status_code == 422


def test_high_risk_ranking_and_filters(api_paths, client):
    body = client.get("/customers/high-risk", params={"limit": 200}).json()
    assert body["filters"]["risk_level"] == "high"
    assert body["returned"] <= 200
    assert body["returned"] == len(body["customers"])
    assert body["total_matching"] > 0
    probabilities = [customer["churn_probability"] for customer in body["customers"]]
    assert probabilities == sorted(probabilities, reverse=True)
    assert all(customer["risk_level"] == "high" for customer in body["customers"])
    assert all("top_risk_driver" in customer for customer in body["customers"])

    filtered = client.get("/customers/high-risk", params={"risk_level": "high", "limit": 10}).json()
    assert filtered["total_matching"] >= filtered["returned"]
    assert all(customer["risk_level"] == "high" for customer in filtered["customers"])

    high = client.get(
        "/customers/high-risk", params={"risk_level": "high", "min_probability": 0.7}
    ).json()
    assert all(customer["churn_probability"] >= 0.7 for customer in high["customers"])


def test_high_risk_rejects_invalid_filters(client):
    assert client.get("/customers/high-risk", params={"risk_level": "extreme"}).status_code == 422
    assert client.get("/customers/high-risk", params={"limit": 0}).status_code == 422
    assert client.get("/customers/high-risk", params={"limit": 501}).status_code == 422


def test_customer_detail_from_scored_book(api_paths, client):
    customer_id = str(api_paths.scored.iloc[0]["customerID"])
    response = client.get(f"/customers/{customer_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["customer_id"] == customer_id
    assert 0 <= body["churn_probability"] <= 1
    assert body["top_drivers"]
    assert body["top_risk_driver"] is not None
    assert body["recommendations"]


def test_customer_detail_unknown_returns_404(client):
    response = client.get("/customers/DOES-NOT-EXIST")
    assert response.status_code == 404


def test_eda_summary_matches_dataset(api_paths, client):
    body = client.get("/eda/summary").json()
    assert body["customers"] == len(api_paths.prepared)
    assert body["churned"] + body["retained"] == body["customers"]
    assert 0 <= body["churn_rate"] <= 1
    assert len(body["churn_by_contract"]) >= 1
    assert len(body["churn_by_tenure_bucket"]) == 5
    assert len(body["monthly_charges"]["histogram"]["bin_edges"]) == 21
    assert body["numeric_correlations"]


def test_openapi_and_docs(client):
    schema = client.get("/openapi.json").json()
    assert "/predict" in schema["paths"]
    assert "/predict/batch" in schema["paths"]
    assert "/customers/high-risk" in schema["paths"]
    assert "/eda/summary" in schema["paths"]
    assert client.get("/docs").status_code == 200


def test_model_card_endpoint(client):
    response = client.get("/model/card")
    assert response.status_code == 200
    assert "Test model card" in response.text


def test_figures_index(client):
    response = client.get("/figures")
    assert response.status_code == 200
    assert isinstance(response.json()["figures"], list)
    assert client.get("/figures/").status_code == 200


def test_service_unavailable_without_model(no_model_client):
    health = no_model_client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "degraded"
    assert health.json()["model_loaded"] is False

    assert no_model_client.post("/predict", json=high_risk_payload()).status_code == 503
    assert no_model_client.get("/model/info").status_code == 503
    assert no_model_client.get("/model/metrics").status_code == 503
    assert no_model_client.get("/eda/summary").status_code == 503
    assert no_model_client.get("/customers/high-risk").status_code == 503
    assert no_model_client.get("/model/card").status_code == 404
