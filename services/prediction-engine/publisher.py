"""KafkaPublisher — serialises PredictionRecord to JSON and publishes to Kafka."""

from __future__ import annotations

import json
import logging

from models.prediction import PredictionRecord

logger = logging.getLogger(__name__)

_TOPIC = "prediction.generated"


class KafkaPublisher:
    """Publishes prediction records to the prediction.generated Kafka topic.

    Args:
        kafka_brokers: Comma-separated broker addresses.
    """

    def __init__(self, kafka_brokers: str) -> None:
        self.kafka_brokers = kafka_brokers
        self._producer = None
        self._connect()

    def _connect(self) -> None:
        try:
            from kafka import KafkaProducer  # type: ignore

            self._producer = KafkaProducer(
                bootstrap_servers=self.kafka_brokers.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
            )
            logger.info("KafkaProducer connected to %s.", self.kafka_brokers)
        except Exception as exc:
            logger.error("KafkaProducer connection failed: %s", exc)
            self._producer = None

    def publish_prediction(self, record: PredictionRecord) -> None:
        """Serialise record to JSON and publish to prediction.generated topic.

        Args:
            record: The prediction record to publish.

        Raises:
            RuntimeError: If the Kafka producer is unavailable.
        """
        if self._producer is None:
            raise RuntimeError("Kafka producer is not available.")

        payload = record.to_dict()
        try:
            future = self._producer.send(_TOPIC, value=payload)
            future.get(timeout=10)
            logger.debug(
                "Published prediction %s to %s.", record.prediction_id, _TOPIC
            )
        except Exception as exc:
            logger.error(
                "Failed to publish prediction %s: %s", record.prediction_id, exc
            )
            raise

    def close(self) -> None:
        if self._producer:
            self._producer.flush()
            self._producer.close()
            self._producer = None
