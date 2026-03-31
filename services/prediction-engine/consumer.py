"""Kafka consumer that buffers sensor readings and triggers prediction cycles."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Callable, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

WINDOW_SIZE = 24  # keep last 24 readings per region
SUPPORTED_DISASTER_TYPES = ["flood", "heatwave", "drought", "landslide", "cyclone"]
FORECAST_HORIZONS = [6, 24, 72]


class SensorBuffer:
    """Thread-safe sliding window buffer of sensor readings per region."""

    def __init__(self, window_size: int = WINDOW_SIZE) -> None:
        self._window_size = window_size
        self._lock = threading.Lock()
        self._buffers: Dict[str, Deque[Dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self._window_size)
        )

    def add(self, region_id: str, reading: Dict[str, Any]) -> None:
        with self._lock:
            self._buffers[region_id].append(reading)

    def get(self, region_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._buffers[region_id])

    def regions(self) -> List[str]:
        with self._lock:
            return list(self._buffers.keys())


class PredictionConsumer:
    """Consumes validated.sensor.reading and raw.weather.forecast Kafka topics.

    Buffers readings per region and calls ``on_prediction_cycle`` every
    PREDICTION_INTERVAL_SECONDS for each region that has data.

    Args:
        kafka_brokers: Comma-separated broker addresses.
        prediction_interval_seconds: How often to trigger a prediction cycle.
        on_prediction_cycle: Callback(region_id, readings) invoked each cycle.
        window_size: Number of readings to keep per region.
    """

    def __init__(
        self,
        kafka_brokers: str,
        prediction_interval_seconds: int,
        on_prediction_cycle: Callable[[str, List[Dict[str, Any]]], None],
        window_size: int = WINDOW_SIZE,
    ) -> None:
        self.kafka_brokers = kafka_brokers
        self.prediction_interval_seconds = prediction_interval_seconds
        self.on_prediction_cycle = on_prediction_cycle
        self.buffer = SensorBuffer(window_size)
        self._stop_event = threading.Event()

    def _consume_loop(self) -> None:
        """Background thread: consume Kafka messages and buffer them."""
        try:
            from kafka import KafkaConsumer  # type: ignore
        except ImportError:
            logger.error("kafka-python not installed; consumer loop disabled.")
            return

        topics = ["validated.sensor.reading", "raw.weather.forecast"]
        try:
            consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=self.kafka_brokers.split(","),
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
                group_id="prediction-engine",
            )
        except Exception as exc:
            logger.error("Failed to create Kafka consumer: %s", exc)
            return

        logger.info("Kafka consumer started on topics: %s", topics)
        for message in consumer:
            if self._stop_event.is_set():
                break
            try:
                payload: Dict[str, Any] = message.value
                region_id = payload.get("region_id")
                if region_id:
                    self.buffer.add(region_id, payload)
            except Exception as exc:
                logger.warning("Error processing Kafka message: %s", exc)

        consumer.close()

    def _prediction_timer_loop(self) -> None:
        """Background thread: fire prediction cycles on schedule."""
        while not self._stop_event.is_set():
            time.sleep(self.prediction_interval_seconds)
            for region_id in self.buffer.regions():
                readings = self.buffer.get(region_id)
                if readings:
                    try:
                        self.on_prediction_cycle(region_id, readings)
                    except Exception as exc:
                        logger.error(
                            "Prediction cycle error for region %s: %s", region_id, exc
                        )

    def start(self) -> None:
        """Start consumer and timer threads."""
        self._stop_event.clear()
        threading.Thread(target=self._consume_loop, daemon=True, name="kafka-consumer").start()
        threading.Thread(target=self._prediction_timer_loop, daemon=True, name="prediction-timer").start()
        logger.info(
            "PredictionConsumer started (interval=%ds)", self.prediction_interval_seconds
        )

    def stop(self) -> None:
        """Signal threads to stop."""
        self._stop_event.set()
        logger.info("PredictionConsumer stopping.")
