"""InfluxStore — writes PredictionRecord time-series data to InfluxDB."""

from __future__ import annotations

import logging
from typing import Optional

from models.prediction import PredictionRecord

logger = logging.getLogger(__name__)

_BUCKET = "predictions"
_MEASUREMENT = "disaster_prediction"


class InfluxStore:
    """Writes prediction records to InfluxDB.

    Args:
        url: InfluxDB server URL, e.g. "http://localhost:8086".
        token: InfluxDB API token.
        org: InfluxDB organisation name.
        bucket: Target bucket name (default: "predictions").
    """

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str = _BUCKET,
    ) -> None:
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self._client = None
        self._write_api = None
        self._connect()

    def _connect(self) -> None:
        try:
            from influxdb_client import InfluxDBClient, WriteOptions  # type: ignore
            from influxdb_client.client.write_api import SYNCHRONOUS  # type: ignore

            self._client = InfluxDBClient(
                url=self.url, token=self.token, org=self.org
            )
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            logger.info("Connected to InfluxDB at %s.", self.url)
        except Exception as exc:
            logger.error("InfluxDB connection failed: %s", exc)
            self._client = None
            self._write_api = None

    def write(self, record: PredictionRecord) -> None:
        """Write a PredictionRecord to InfluxDB.

        Tags:  region_id, disaster_type, risk_level
        Fields: probability_pct, severity_index, time_to_impact_h

        Args:
            record: The prediction record to write.

        Raises:
            RuntimeError: If the InfluxDB client is unavailable.
        """
        if self._write_api is None:
            raise RuntimeError("InfluxDB write API is not available.")

        try:
            from influxdb_client import Point  # type: ignore

            point = (
                Point(_MEASUREMENT)
                .tag("region_id", record.region_id)
                .tag("disaster_type", record.disaster_type)
                .tag("risk_level", record.risk_level)
                .field("probability_pct", record.probability_pct)
                .field("severity_index", record.severity_index)
                .field(
                    "time_to_impact_h",
                    record.time_to_impact_h if record.time_to_impact_h is not None else -1.0,
                )
                .field("forecast_horizon_h", float(record.forecast_horizon_h))
                .time(record.generated_at)
            )
            self._write_api.write(bucket=self.bucket, org=self.org, record=point)
            logger.debug(
                "Wrote prediction %s to InfluxDB.", record.prediction_id
            )
        except Exception as exc:
            logger.error(
                "Failed to write prediction %s to InfluxDB: %s",
                record.prediction_id,
                exc,
            )
            raise

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._write_api = None
