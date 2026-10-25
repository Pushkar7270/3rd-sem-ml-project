"""HTTP tests for the dashboard, prediction history, feedback and actions."""

from __future__ import annotations

from tests.synthetic import high_risk_payload


def test_dashboard_summary(client):
    body = client.get("/dashboard/summary").json()
    assert body["model"]["name"] == "LogisticRegression"
    assert body["customers"]["total"] > 0
    assert set(body["risk"]) >= {"low", "medium", "high", "high_share"}
    assert body["revenue_at_risk"]["total"] >= body["revenue_at_risk"]["high"]
    assert body["actions"]["total"] == 0
    assert body["history"]["total_predictions"] == 0
    assert body["top_drivers"]


def test_prediction_is_logged_and_feedback_is_recorded(client):
    prediction = client.post("/predict", json=high_risk_payload()).json()
    history = client.get("/history?limit=5").json()
    assert history["returned"] == 1
    item = history["items"][0]
    assert item["customer_id"] == "TEST-HIGH"
    assert item["churn_prediction"] is True
    assert item["actual_churn"] is None
    assert item["id"] >= 1

    feedback = client.post(
        "/feedback",
        json={"prediction_id": item["id"], "actual_churn": True, "notes": "Confirmed churn"},
    )
    assert feedback.status_code == 201
    assert feedback.json()["actual_churn"] is True

    refreshed = client.get("/history?limit=5").json()["items"][0]
    assert refreshed["actual_churn"] is True
    stats = client.get("/history/stats").json()
    assert stats["total_predictions"] == 1
    assert stats["feedback_count"] == 1
    assert stats["observed_churn_rate"] == 1.0
    status = client.get("/db/status").json()
    assert status["engine"] == "SQLite"
    assert status["tables"]["predictions"] == 1
    assert status["tables"]["feedback"] == 1
    assert prediction["churn_probability"] >= 0


def test_feedback_unknown_prediction_returns_400(client):
    response = client.post("/feedback", json={"prediction_id": 9999, "actual_churn": True})
    # ValueError is mapped to 400 by the application handler.
    assert response.status_code == 400


def test_action_workflow(api_paths, client):
    customer_id = str(api_paths.scored.iloc[1]["customerID"])
    detail = client.get(f"/customers/{customer_id}").json()
    recommendation = detail["recommendations"][0]

    created = client.post(
        "/actions",
        json={
            "customer_id": customer_id,
            "recommendation_id": recommendation["id"],
            "note": "Priority outreach",
        },
    )
    assert created.status_code == 201, created.text
    action = created.json()
    assert action["customer_id"] == customer_id
    assert action["recommendation_id"] == recommendation["id"]
    assert action["title"] == recommendation["title"]
    assert action["status"] == "pending"

    listing = client.get("/actions").json()
    assert listing["total"] == 1
    assert listing["actions"][0]["id"] == action["id"]

    summary = client.get("/actions/summary").json()
    assert summary == {"pending": 1, "contacted": 0, "accepted": 0, "declined": 0, "total": 1}

    updated = client.patch(
        f"/actions/{action['id']}",
        json={"status": "contacted", "note": "Spoke to customer"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "contacted"
    assert updated.json()["note"] == "Spoke to customer"

    filtered = client.get("/actions?status=contacted").json()
    assert filtered["total"] == 1

    dashboard = client.get("/dashboard/summary").json()
    assert dashboard["actions"]["contacted"] == 1
    assert dashboard["actions"]["total"] == 1

    deleted = client.delete(f"/actions/{action['id']}")
    assert deleted.status_code == 204
    assert client.get("/actions").json()["total"] == 0


def test_action_save_is_idempotent(api_paths, client):
    customer_id = str(api_paths.scored.iloc[2]["customerID"])
    recommendation_id = client.get(f"/customers/{customer_id}").json()["recommendations"][0]["id"]
    first = client.post(
        "/actions",
        json={"customer_id": customer_id, "recommendation_id": recommendation_id},
    ).json()
    second = client.post(
        "/actions",
        json={
            "customer_id": customer_id,
            "recommendation_id": recommendation_id,
            "status": "accepted",
            "note": "Accepted by customer",
        },
    ).json()
    assert first["id"] == second["id"]
    assert second["status"] == "accepted"
    assert client.get("/actions").json()["total"] == 1


def test_action_validation(api_paths, client):
    customer_id = str(api_paths.scored.iloc[3]["customerID"])
    missing = client.post(
        "/actions", json={"customer_id": "DOES-NOT-EXIST", "recommendation_id": "RET-01"}
    )
    assert missing.status_code == 404

    invalid_rec = client.post(
        "/actions", json={"customer_id": customer_id, "recommendation_id": "RET-99"}
    )
    assert invalid_rec.status_code == 404

    assert client.post(
        "/actions", json={"customer_id": customer_id, "recommendation_id": "RET-01"}
    ).status_code in {201, 404}
    assert client.patch("/actions/9999", json={"status": "contacted"}).status_code == 404
    assert client.delete("/actions/9999").status_code == 404


def test_ad_hoc_action_can_be_saved_with_snapshot(client):
    prediction = client.post("/predict", json=high_risk_payload()).json()
    recommendation = prediction["recommendations"][0]
    response = client.post(
        "/actions",
        json={
            "customer_id": "TEST-HIGH",
            "recommendation_id": recommendation["id"],
            "title": recommendation["title"],
            "offer": recommendation["offer"],
            "risk_level": prediction["risk_level"],
            "churn_probability": prediction["churn_probability"],
        },
    )
    assert response.status_code == 201, response.text
    action = response.json()
    assert action["customer_id"] == "TEST-HIGH"
    assert action["title"] == recommendation["title"]
    assert action["risk_level"] == prediction["risk_level"]


def test_frontend_is_served(client):
    import re

    index = client.get("/app/")
    assert index.status_code == 200
    assert "RetainIQ" in index.text
    assert 'id="root"' in index.text
    assert "/app/assets/" in index.text

    assets = re.findall(r'(?:src|href)="(/app/assets/[^"]+)"', index.text)
    assert assets
    for asset in assets:
        assert client.get(asset).status_code == 200, asset

    script_url = next(asset for asset in assets if asset.endswith(".js"))
    script = client.get(script_url)
    assert script.status_code == 200
    assert "dashboard/summary" in script.text

    css_url = next(asset for asset in assets if asset.endswith(".css"))
    styles = client.get(css_url)
    assert styles.status_code == 200
    assert "--green" in styles.text

    font_urls = re.findall(r"url\((/app/assets/[^)]+\.woff2)\)", styles.text)
    assert font_urls
    font = client.get(font_urls[0])
    assert font.status_code == 200
    assert "font" in font.headers.get("content-type", "")
