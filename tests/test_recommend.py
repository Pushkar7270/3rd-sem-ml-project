"""Tests for the rule-based retention recommendation engine."""

from __future__ import annotations

from churn.recommend import recommend, recommendation_summary
from tests.synthetic import high_risk_payload, low_risk_payload


def _drivers(*sources: str) -> list[dict]:
    return [
        {
            "feature": source,
            "label": source,
            "source": source,
            "value": None,
            "contribution": 0.5 - 0.1 * index,
            "impact": "increases",
        }
        for index, source in enumerate(sources)
    ]


def test_high_risk_customer_gets_full_playbook():
    drivers = _drivers("Contract", "MonthlyCharges", "PaymentMethod", "tenure")
    recs = recommend(high_risk_payload(), 0.85, "high", drivers, limit=8)
    ids = {rec["id"] for rec in recs}
    assert {"RET-01", "RET-02", "RET-03", "RET-04", "RET-07"} <= ids
    assert "RET-13" in ids  # high probability save offer
    assert len(recs) <= 8


def test_recommendations_are_ranked_and_unique():
    recs = recommend(high_risk_payload(), 0.85, "high", _drivers("Contract", "tenure"), limit=5)
    assert len(recs) == 5
    ids = [rec["id"] for rec in recs]
    assert len(ids) == len(set(ids))
    scores = [rec["priority_score"] for rec in recs]
    assert scores == sorted(scores, reverse=True)
    for rec in recs:
        assert rec["priority"] in {"critical", "high", "medium"}
        assert rec["title"]
        assert rec["description"]
        assert rec["action"]
        assert rec["offer"]
        assert rec["channels"]


def test_limit_is_applied():
    recs = recommend(high_risk_payload(), 0.85, "high", [], limit=2)
    assert len(recs) == 2
    assert len(recommend(high_risk_payload(), 0.85, "high", [], limit=0)) == 1
    assert len(recommend(high_risk_payload(), 0.85, "high", [], limit=100)) <= 8


def test_low_risk_gets_nurture_and_no_pricing_offers():
    recs = recommend(low_risk_payload(), 0.04, "low", [], limit=8)
    ids = {rec["id"] for rec in recs}
    assert "RET-14" in ids
    assert "RET-08" in ids  # long tenure loyalty
    assert all(rec["category"] != "pricing" for rec in recs)
    assert "RET-02" not in ids
    assert "RET-13" not in ids


def test_no_internet_customer_has_no_internet_addon_offers():
    profile = high_risk_payload()
    profile["InternetService"] = "No"
    for field in [
        "OnlineSecurity",
        "OnlineBackup",
        "DeviceProtection",
        "TechSupport",
        "StreamingTV",
        "StreamingMovies",
    ]:
        profile[field] = "No internet service"
    ids = {rec["id"] for rec in recommend(profile, 0.8, "high", [], limit=8)}
    assert "RET-03" not in ids  # fiber pricing
    assert "RET-05" not in ids  # tech support
    assert "RET-06" not in ids  # online security
    assert "RET-12" not in ids  # device protection


def test_senior_customer_receives_priority_support():
    profile = low_risk_payload()
    profile["SeniorCitizen"] = 1
    ids = {rec["id"] for rec in recommend(profile, 0.3, "medium", [], limit=8)}
    assert "RET-09" in ids


def test_driver_alignment_increases_priority():
    without_drivers = recommend(high_risk_payload(), 0.7, "high", [], limit=8)
    with_drivers = recommend(
        high_risk_payload(), 0.7, "high", _drivers("Contract", "PaymentMethod"), limit=8
    )
    contract_without = next(r for r in without_drivers if r["id"] == "RET-02")
    contract_with = next(r for r in with_drivers if r["id"] == "RET-02")
    assert contract_with["priority_score"] > contract_without["priority_score"]


def test_billing_clarity_rule():
    profile = low_risk_payload()
    profile.update(
        {"PaperlessBilling": "Yes", "MonthlyCharges": 80.0, "tenure": 30, "Contract": "Two year"}
    )
    ids = {rec["id"] for rec in recommend(profile, 0.45, "medium", [], limit=8)}
    assert "RET-10" in ids


def test_streaming_bundle_rule():
    profile = low_risk_payload()
    profile.update(
        {
            "StreamingTV": "Yes",
            "StreamingMovies": "Yes",
            "MonthlyCharges": 85.0,
            "InternetService": "DSL",
        }
    )
    ids = {rec["id"] for rec in recommend(profile, 0.45, "medium", [], limit=8)}
    assert "RET-11" in ids


def test_medium_band_uses_medium_treatment():
    """A band-aligned medium risk (0.32-0.60) must not receive low-risk nurture copy."""
    profile = high_risk_payload()
    recs = recommend(profile, 0.333, "medium", [], limit=8)
    ids = {rec["id"] for rec in recs}
    assert "RET-14" not in ids
    assert any(rec["category"] == "pricing" for rec in recs)


def test_service_and_protection_rules_trigger_positively():
    profile = low_risk_payload()
    profile.update(
        {
            "tenure": 30,
            "Contract": "Two year",
            "InternetService": "DSL",
            "TechSupport": "No",
            "OnlineSecurity": "No",
            "DeviceProtection": "No",
            "StreamingTV": "No",
            "StreamingMovies": "No",
            "MonthlyCharges": 50.0,
        }
    )
    ids = {rec["id"] for rec in recommend(profile, 0.45, "medium", [], limit=8)}
    assert {"RET-05", "RET-06", "RET-12"} <= ids


def test_summary_text():
    recs = recommend(high_risk_payload(), 0.85, "high", [], limit=3)
    summary = recommendation_summary(recs, "high")
    assert "High churn risk" in summary
    assert summary.endswith("actions suggested).")
    assert recommendation_summary([], "low") == "No retention action required at this time."
