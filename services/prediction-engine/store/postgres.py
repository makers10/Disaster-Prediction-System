"""PredictionStore — persists PredictionRecord to PostgreSQL via psycopg2."""

from __future__ import annotations

import logging
from typing import Optional

from models.prediction import PredictionRecord

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id         UUID PRIMARY KEY,
    region_id             TEXT NOT NULL,
    disaster_type         TEXT NOT NULL,
    forecast_horizon_h    INT NOT NULL,
    risk_level            TEXT NOT NULL,
    probability_pct       FLOAT NOT NULL,
    time_to_impact_h      FLOAT,
    severity_index        FLOAT NOT NULL,
    generated_at          TIMESTAMPTZ NOT NULL,
    model_version         TEXT NOT NULL,
    input_data_snapshot_id TEXT NOT NULL
);
"""

_INSERT_SQL = """
INSERT INTO predictions (
    prediction_id, region_id, disaster_type, forecast_horizon_h,
    risk_level, probability_pct, time_to_impact_h, severity_index,
    generated_at, model_version, input_data_snapshot_id
) VALUES (
    %s, %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s
)
ON CONFLICT (prediction_id) DO NOTHING;
"""


class PredictionStore:
    """Stores prediction records in PostgreSQL.

    Args:
        postgres_url: libpq connection string, e.g.
            "postgresql://user:pass@host:5432/dbname"
    """

    def __init__(self, postgres_url: str) -> None:
        self.postgres_url = postgres_url
        self._conn = None
        self._connect()

    def _connect(self) -> None:
        try:
            import psycopg2  # type: ignore

            self._conn = psycopg2.connect(self.postgres_url)
            self._conn.autocommit = False
            self._ensure_table()
            logger.info("Connected to PostgreSQL.")
        except Exception as exc:
            logger.error("PostgreSQL connection failed: %s", exc)
            self._conn = None

    def _ensure_table(self) -> None:
        if self._conn is None:
            return
        with self._conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
        self._conn.commit()

    def save(self, record: PredictionRecord) -> None:
        """Insert a PredictionRecord into the predictions table.

        Args:
            record: The prediction record to persist.

        Raises:
            RuntimeError: If the database connection is unavailable.
        """
        if self._conn is None:
            raise RuntimeError("PostgreSQL connection is not available.")

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    _INSERT_SQL,
                    (
                        record.prediction_id,
                        record.region_id,
                        record.disaster_type,
                        record.forecast_horizon_h,
                        record.risk_level,
                        record.probability_pct,
                        record.time_to_impact_h,
                        record.severity_index,
                        record.generated_at,
                        record.model_version,
                        record.input_data_snapshot_id,
                    ),
                )
            self._conn.commit()
            logger.debug("Saved prediction %s to PostgreSQL.", record.prediction_id)
        except Exception as exc:
            self._conn.rollback()
            logger.error("Failed to save prediction %s: %s", record.prediction_id, exc)
            raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
