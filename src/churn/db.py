"""SQLite persistence for prediction history, feedback and retention actions.

SQLite is part of the Python standard library: there is no server to install,
no credentials and no network, which keeps the demo portable while still
providing ACID storage and SQL.  Two related stores live in the same file:

* :class:`PredictionStore` – audit trail of every score plus closed-loop
  feedback ("did the customer actually churn?").
* :class:`ActionRepository` – retention recommendations saved by the team,
  with a workflow status (pending / contacted / accepted / declined).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import config

PREDICTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at              TEXT    NOT NULL,
    customer_id             TEXT,
    churn_probability       REAL    NOT NULL,
    risk_level              TEXT    NOT NULL,
    churn_prediction        INTEGER NOT NULL,
    threshold               REAL,
    monthly_charges         REAL,
    annual_revenue_at_risk  REAL,
    estimated_clv           REAL,
    top_driver              TEXT,
    top_driver_source       TEXT,
    model_name              TEXT,
    model_version           TEXT,
    payload                 TEXT
);

CREATE INDEX IF NOT EXISTS idx_predictions_created
    ON predictions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_risk
    ON predictions (risk_level);

CREATE TABLE IF NOT EXISTS feedback (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id  INTEGER NOT NULL REFERENCES predictions (id) ON DELETE CASCADE,
    actual_churn   INTEGER NOT NULL,
    notes          TEXT,
    created_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_prediction
    ON feedback (prediction_id);
"""

ACTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS retention_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    title TEXT NOT NULL,
    offer TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    churn_probability REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'contacted', 'accepted', 'declined')),
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (customer_id, recommendation_id)
);
CREATE INDEX IF NOT EXISTS idx_actions_status ON retention_actions(status);
CREATE INDEX IF NOT EXISTS idx_actions_customer ON retention_actions(customer_id);
"""

ACTION_STATUSES = ("pending", "contacted", "accepted", "declined")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


class PredictionStore:
    """Thin, thread-safe-by-connection wrapper around the prediction database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialise()

    def _connect(self) -> sqlite3.Connection:
        return _connect(self.path)

    def initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(PREDICTION_SCHEMA)

    def log_prediction(self, prediction: dict[str, Any]) -> int:
        """Persist a scored prediction and return the audit row id."""
        financial = prediction.get("financial_impact") or {}
        driver = prediction.get("top_risk_driver") or {}
        model = prediction.get("model") or {}
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO predictions (
                    created_at, customer_id, churn_probability, risk_level,
                    churn_prediction, threshold, monthly_charges,
                    annual_revenue_at_risk, estimated_clv, top_driver,
                    top_driver_source, model_name, model_version, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utcnow(),
                    prediction.get("customer_id"),
                    float(prediction.get("churn_probability", 0.0)),
                    str(prediction.get("risk_level", "low")),
                    int(bool(prediction.get("churn_prediction"))),
                    prediction.get("threshold"),
                    financial.get("monthly_charges"),
                    financial.get("annual_revenue_at_risk"),
                    financial.get("estimated_clv"),
                    driver.get("label"),
                    driver.get("source"),
                    model.get("name"),
                    model.get("version"),
                    json.dumps(prediction, separators=(",", ":"), default=str),
                ),
            )
            return int(cursor.lastrowid or 0)

    def add_feedback(
        self,
        prediction_id: int,
        actual_churn: bool,
        notes: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM predictions WHERE id = ?", (prediction_id,)
            ).fetchone()
            if exists is None:
                raise ValueError(f"Unknown prediction id: {prediction_id}")
            cursor = connection.execute(
                """
                INSERT INTO feedback (prediction_id, actual_churn, notes, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (prediction_id, int(bool(actual_churn)), notes, _utcnow()),
            )
        return {
            "id": int(cursor.lastrowid or 0),
            "prediction_id": prediction_id,
            "actual_churn": bool(actual_churn),
            "notes": notes,
            "created_at": _utcnow(),
        }

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT p.*, (
                    SELECT f.actual_churn FROM feedback f
                    WHERE f.prediction_id = p.id
                    ORDER BY f.id DESC LIMIT 1
                ) AS actual_churn
                FROM predictions p
                ORDER BY p.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        since = (datetime.now(UTC) - timedelta(hours=24)).isoformat(timespec="seconds")
        with self._connect() as connection:
            totals = connection.execute(
                """
                SELECT
                    COUNT(*)                                        AS total_predictions,
                    COALESCE(SUM(churn_prediction), 0)              AS predicted_churners,
                    COALESCE(SUM(annual_revenue_at_risk), 0)        AS revenue_at_risk,
                    COALESCE(AVG(churn_probability), 0)             AS average_probability,
                    COALESCE(SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END), 0)   AS high,
                    COALESCE(SUM(CASE WHEN risk_level = 'medium' THEN 1 ELSE 0 END), 0) AS medium,
                    COALESCE(SUM(CASE WHEN risk_level = 'low' THEN 1 ELSE 0 END), 0)    AS low
                FROM predictions
                """
            ).fetchone()
            last_24h = connection.execute(
                "SELECT COUNT(*) AS n FROM predictions WHERE created_at >= ?", (since,)
            ).fetchone()["n"]
            feedback = connection.execute(
                """
                SELECT COUNT(*) AS n, COALESCE(AVG(actual_churn), 0) AS churn_rate
                FROM feedback
                """
            ).fetchone()
        total = int(totals["total_predictions"])
        return {
            "total_predictions": total,
            "predicted_churners": int(totals["predicted_churners"]),
            "average_probability": round(float(totals["average_probability"]), 4),
            "revenue_at_risk": round(float(totals["revenue_at_risk"]), 2),
            "by_risk": {
                "high": int(totals["high"]),
                "medium": int(totals["medium"]),
                "low": int(totals["low"]),
            },
            "last_24h": int(last_24h),
            "feedback_count": int(feedback["n"]),
            "observed_churn_rate": round(float(feedback["churn_rate"]), 4),
        }

    def status(self) -> dict[str, Any]:
        size = self.path.stat().st_size if self.path.exists() else 0
        with self._connect() as connection:
            counts = {}
            for table in ("predictions", "feedback", "retention_actions"):
                try:
                    counts[table] = int(
                        connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                    )
                except sqlite3.OperationalError:
                    counts[table] = 0
            journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
        return {
            "engine": "SQLite",
            "path": str(self.path),
            "size_bytes": size,
            "journal_mode": journal,
            "tables": counts,
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data.pop("payload", None)
        data["churn_prediction"] = bool(data.get("churn_prediction"))
        data["actual_churn"] = (
            None if data.get("actual_churn") is None else bool(data["actual_churn"])
        )
        return data


class ActionRepository:
    """Retention action workflow stored alongside prediction history."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else config.DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        return _connect(self.path)

    def init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(ACTION_SCHEMA)

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["churn_probability"] = round(float(result["churn_probability"]), 6)
        return result

    def save_action(
        self,
        *,
        customer_id: str,
        recommendation_id: str,
        title: str,
        offer: str,
        risk_level: str,
        churn_probability: float,
        status: str = "pending",
        note: str | None = None,
    ) -> dict[str, Any]:
        """Insert an action or update the existing one for the same recommendation."""
        if status not in ACTION_STATUSES:
            raise ValueError(f"Unknown action status: {status}")
        now = _utcnow()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO retention_actions (
                    customer_id, recommendation_id, title, offer, risk_level,
                    churn_probability, status, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id, recommendation_id) DO UPDATE SET
                    title = excluded.title,
                    offer = excluded.offer,
                    risk_level = excluded.risk_level,
                    churn_probability = excluded.churn_probability,
                    status = excluded.status,
                    note = COALESCE(excluded.note, retention_actions.note),
                    updated_at = excluded.updated_at
                """,
                (
                    customer_id,
                    recommendation_id,
                    title,
                    offer,
                    risk_level,
                    float(churn_probability),
                    status,
                    note,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM retention_actions WHERE customer_id = ? AND recommendation_id = ?",
                (customer_id, recommendation_id),
            ).fetchone()
        return self._row_to_dict(row)

    def list_actions(
        self,
        *,
        status: str | None = None,
        customer_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM retention_actions WHERE 1=1"
        params: list[Any] = []
        if status:
            if status not in ACTION_STATUSES:
                raise ValueError(f"Unknown action status: {status}")
            query += " AND status = ?"
            params.append(status)
        if customer_id:
            query += " AND customer_id = ?"
            params.append(customer_id)
        query += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def update_action(
        self,
        action_id: int,
        *,
        status: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        if status is not None and status not in ACTION_STATUSES:
            raise ValueError(f"Unknown action status: {status}")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM retention_actions WHERE id = ?", (action_id,)
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE retention_actions SET status = ?, note = ?, updated_at = ? WHERE id = ?",
                (
                    status if status is not None else row["status"],
                    note if note is not None else row["note"],
                    _utcnow(),
                    action_id,
                ),
            )
            updated = connection.execute(
                "SELECT * FROM retention_actions WHERE id = ?", (action_id,)
            ).fetchone()
        return self._row_to_dict(updated)

    def delete_action(self, action_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM retention_actions WHERE id = ?", (action_id,))
        return cursor.rowcount > 0

    def summary(self) -> dict[str, int]:
        counts = {status: 0 for status in ACTION_STATUSES}
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM retention_actions GROUP BY status"
            ).fetchall()
        for row in rows:
            counts[str(row["status"])] = int(row["count"])
        counts["total"] = sum(counts.values())
        return counts
