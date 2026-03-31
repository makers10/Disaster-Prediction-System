"""CNN Feature Extractor Service.

Consumes raw.satellite.image Kafka topic, runs CNN feature extraction,
and publishes CNNFeatures to features.satellite.cnn topic.
Must complete extraction within 5 minutes of image receipt.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")
INPUT_TOPIC = "raw.satellite.image"
OUTPUT_TOPIC = "features.satellite.cnn"
GROUP_ID = "cnn-extractor"
# SLA: must publish within 5 minutes of image receipt
SLA_SECONDS = 5 * 60


def build_cnn_features(meta: Dict[str, Any], extractor) -> Dict[str, Any]:
    """Extract CNN features from image metadata.

    The metadata may contain a base64-encoded 'image_data' field.
    If absent, we generate synthetic features (stand-in for real satellite data).
    """
    image_data_b64 = meta.get("image_data")

    if image_data_b64:
        try:
            image_bytes = base64.b64decode(image_data_b64)
            flood_pct, cloud_density, veg_index = extractor.extract(image_bytes)
        except Exception as exc:
            logger.warning("CNN extraction failed, using synthetic features: %s", exc)
            flood_pct, cloud_density, veg_index = _synthetic_features(meta)
    else:
        flood_pct, cloud_density, veg_index = _synthetic_features(meta)

    return {
        "image_id": meta.get("image_id", "unknown"),
        "region_id": meta.get("region_id", "unknown"),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "flood_inundation_pct": flood_pct,
        "cloud_density": cloud_density,
        "vegetation_index": veg_index,
    }


def _synthetic_features(meta: Dict[str, Any]):
    """Generate deterministic synthetic features when no image data is present."""
    import hashlib
    seed = int(hashlib.md5(meta.get("image_id", "x").encode()).hexdigest()[:8], 16)
    rng = __import__("numpy").random.default_rng(seed)
    flood_pct = float(rng.uniform(0, 30))
    cloud_density = float(rng.uniform(0.1, 0.6))
    veg_index = float(rng.uniform(0.3, 0.8))
    return flood_pct, cloud_density, veg_index


def run_consumer(extractor) -> None:
    try:
        from kafka import KafkaConsumer, KafkaProducer  # type: ignore
    except ImportError:
        logger.error("kafka-python not installed")
        return

    consumer = KafkaConsumer(
        INPUT_TOPIC,
        bootstrap_servers=KAFKA_BROKERS.split(","),
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
        group_id=GROUP_ID,
    )

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKERS.split(","),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=3,
    )

    logger.info("CNN extractor consumer started on topic: %s", INPUT_TOPIC)

    for message in consumer:
        try:
            meta: Dict[str, Any] = message.value
            received_at = meta.get("received_at", datetime.now(timezone.utc).isoformat())

            # Check SLA
            try:
                received_ts = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - received_ts).total_seconds()
                if elapsed > SLA_SECONDS:
                    logger.warning(
                        "SLA breach: image %s received %.0fs ago (SLA=%ds)",
                        meta.get("image_id"), elapsed, SLA_SECONDS,
                    )
            except Exception:
                pass

            features = build_cnn_features(meta, extractor)
            future = producer.send(OUTPUT_TOPIC, value=features)
            future.get(timeout=10)
            logger.info(
                "Published CNN features: image_id=%s region_id=%s flood=%.1f%% cloud=%.3f veg=%.3f",
                features["image_id"], features["region_id"],
                features["flood_inundation_pct"], features["cloud_density"],
                features["vegetation_index"],
            )
        except Exception as exc:
            logger.error("Error processing satellite image: %s", exc)

    consumer.close()
    producer.flush()
    producer.close()


def main() -> None:
    logger.info("Starting CNN Feature Extractor Service...")
    logger.info("Kafka brokers: %s", KAFKA_BROKERS)

    from models.cnn import CNNExtractor
    extractor = CNNExtractor()

    stop_event = threading.Event()

    consumer_thread = threading.Thread(
        target=run_consumer, args=(extractor,), daemon=True, name="cnn-consumer"
    )
    consumer_thread.start()

    def shutdown(signum, frame):
        logger.info("Shutting down CNN Feature Extractor Service...")
        stop_event.set()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    signal.pause()


if __name__ == "__main__":
    main()
