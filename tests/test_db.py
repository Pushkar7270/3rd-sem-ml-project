"""Tests for SQLite persistence: prediction history, feedback and actions."""

from __future__ import annotations

import pandas as pd
import pytest

from churn.db import ACTION_STATUSES, ActionRepository, PredictionStore


def _prediction(customer_id: str = "TEST-001", probability: float = 0.82) -> dict:
    risk_level = "high" if probability >= 0.6 else "medium" if probability >= 0.32 else "low"
    return {
        "customer_id": customer_id,
        "churn_probability": probability,
        "churn_prediction": probability >= 0.32,
        "risk_level": risk_level,
        "threshold": 0.32,
        "top_risk_driver": {"label": "Tenure (months)", "source": "tenure"},
        "financial_impact": {
            "monthly_charges": 80.0,
            "annual_revenue_at_risk": 787.2,
            "estimated_clv": 97.56,
        },
        "model": {"name": "LogisticRegression", "version": "v1-test"},
        "recommendations": [],
        "summary": "High churn risk",
    }


def test_prediction_store_logs_and_reads(tmp_path):
    store = PredictionStore(tmp_path / "history.db")
    prediction_id = store.log_prediction(_prediction())
    assert prediction_id == 1
    rows = store.recent(10)
    assert len(rows) == 1
    assert rows[0]["customer_id"] == "TEST-001"
    assert rows[0]["churn_prediction"] is True
    assert rows[0]["actual_churn"] is None
    assert "payload" not in rows[0]


def test_prediction_store_stats_and_status(tmp_path):
    store = PredictionStore(tmp_path / "history.db")
    store.log_prediction(_prediction("A", 0.9))
    store.log_prediction(_prediction("B", 0.4))
    store.log_prediction(_prediction("C", 0.1))
    stats = store.stats()
    assert stats["total_predictions"] == 3
    assert stats["predicted_churners"] == 2  # threshold 0.32
    assert stats["by_risk"] == {"high": 1, "medium": 1, "low": 1}
    status = store.status()
    assert status["engine"] == "SQLite"
    assert status["tables"]["predictions"] == 3
    assert status["tables"]["feedback"] == 0


def test_feedback_closes_loop(tmp_path):
    store = PredictionStore(tmp_path / "history.db")
    prediction_id = store.log_prediction(_prediction())
    feedback = store.add_feedback(prediction_id, True, "Left after billing change")
    assert feedback["actual_churn"] is True
    assert feedback["prediction_id"] == prediction_id
    row = store.recent(1)[0]
    assert row["actual_churn"] is True
    stats = store.stats()
    assert stats["feedback_count"] == 1
    assert stats["observed_churn_rate"] == 1.0


def test_feedback_unknown_prediction(tmp_path):
    store = PredictionStore(tmp_path / "history.db")
    with pytest.raises(ValueError, match="Unknown prediction id"):
        store.add_feedback(999, False)


def test_prediction_store_limit_is_clamped(tmp_path):
    store = PredictionStore(tmp_path / "history.db")
    for index in range(5):
        store.log_prediction(_prediction(f"C{index}", 0.5))
    assert len(store.recent(2)) == 2
    assert len(store.recent(999)) == 5


def test_action_repository_crud(tmp_path):
    repo = ActionRepository(tmp_path / "actions.db")
    saved = repo.save_action(
        customer_id="CUST-1",
        recommendation_id="RET-01",
        title="Retention outreach",
        offer="Call within 48h",
        risk_level="high",
        churn_probability=0.85,
    )
    assert saved["status"] == "pending"
    assert saved["id"] == 1
    assert repo.summary() == {
        "pending": 1,
        "contacted": 0,
        "accepted": 0,
        "declined": 0,
        "total": 1,
    }

    updated = repo.update_action(saved["id"], status="contacted", note="Left voicemail")
    assert updated["status"] == "contacted"
    assert updated["note"] == "Left voicemail"
    assert repo.list_actions(status="contacted")[0]["id"] == saved["id"]
    assert repo.delete_action(saved["id"]) is True
    assert repo.delete_action(saved["id"]) is False
    assert repo.summary()["total"] == 0


def test_action_upsert_is_idempotent(tmp_path):
    repo = ActionRepository(tmp_path / "actions.db")
    first = repo.save_action(
        customer_id="CUST-1",
        recommendation_id="RET-01",
        title="Retention outreach",
        offer="Call",
        risk_level="high",
        churn_probability=0.8,
    )
    second = repo.save_action(
        customer_id="CUST-1",
        recommendation_id="RET-01",
        title="Retention outreach v2",
        offer="Call + credit",
        risk_level="high",
        churn_probability=0.9,
        note="Updated offer",
    )
    assert second["id"] == first["id"]
    assert second["title"] == "Retention outreach v2"
    assert repo.summary()["total"] == 1


def test_action_repository_rejects_invalid_status(tmp_path):
    repo = ActionRepository(tmp_path / "actions.db")
    with pytest.raises(ValueError):
        repo.save_action(
            customer_id="C",
            recommendation_id="R",
            title="T",
            offer="O",
            risk_level="high",
            churn_probability=0.5,
            status="unknown",
        )
    with pytest.raises(ValueError):
        repo.list_actions(status="unknown")


def test_action_statuses_constant():
    assert ACTION_STATUSES == ("pending", "contacted", "accepted", "declined")


def test_both_stores_share_one_database_file(tmp_path):
    path = tmp_path / "shared.db"
    PredictionStore(path).log_prediction(_prediction())
    ActionRepository(path).save_action(
        customer_id="CUST-1",
        recommendation_id="RET-01",
        title="T",
        offer="O",
        risk_level="high",
        churn_probability=0.8,
    )
    store = PredictionStore(path)
    actions = ActionRepository(path)
    assert store.status()["tables"]["predictions"] == 1
    assert actions.summary()["total"] == 1
    assert pd.notna(store.recent(1)[0]["id"])
