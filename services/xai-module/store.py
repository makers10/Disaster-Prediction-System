"""PostgreSQL store for XAI explanations."""

from __future__ import annotations

import json
import logging

from models.explanation import XAIExplanation

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS xai_explanations (
    explanation_id      UUID PRIMARY KEY,
    prediction_id       UUID NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL,
    contributing_factors JSONB NOT NULL,
    plain_language_summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_xai_prediction_id ON xai_explanations(prediction_id);
"""

_INSERT_SQL = """
INSERT INTO xai_explanations
    (explanation_id, prediction_id, generated_at, contributing_factors, plain_language_summary)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (explanation_id) DO NOTHING;
"""


class ExplanationStore:
    def __init__(self, postgres_url: str) -> None:
        self._conn = None
        try:
            import psycopg2  # type: ignore
            self._conn = psycopg2.connect(postgres_url)
            self._conn.autocommit = False
            with self._conn.cursor() as cur:
                cur.execute(_CREATE_TABLE_SQL)
            self._conn.commit()
            logger.info("ExplanationStore connected to PostgreSQL.")
        except Exception as exc:
            logger.error("ExplanationStore: PostgreSQL connection failed: %s", exc)
            self._conn = None

    def save(self, explanation: XAIExplanation) -> None:
        if self._conn is None:
            raise RuntimeError("PostgreSQL not available.")
        factors_json = json.dumps([
            {"feature_name": f.feature_name, "contribution_pct": f.contribution_pct,
             "direction": f.direction}
            for f in explanation.contributing_factors
        ])
        try:
            with self._conn.cursor() as cur:
                cur.execute(_INSERT_SQL, (
                    explanation.explanation_id,
                    explanation.prediction_id,
                    explanation.generated_at,
                    factors_json,
                    explanation.plain_language_summary,
                ))
            self._conn.commit()
        except Exception as exc:
            self._conn.rollback()
            raise exc

    def get_by_prediction_id(self, prediction_id: str) -> dict | None:
        if self._conn is None:
            return None
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT explanation_id, prediction_id, generated_at, "
                "contributing_factors, plain_language_summary "
                "FROM xai_explanations WHERE prediction_id = %s LIMIT 1",
                (prediction_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "explanation_id": str(row[0]),
            "prediction_id": str(row[1]),
            "generated_at": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2]),
            "contributing_factors": row[3],
            "plain_language_summary": row[4],
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
