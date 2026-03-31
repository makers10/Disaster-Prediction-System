"""Prediction Engine Service — SSM + Transformer ensemble for disaster prediction."""

from __future__ import annotations

import logging
import os
import signal
import sys
import uuid
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")
POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction",
)
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "disaster_org")
PREDICTION_INTERVAL_SECONDS = int(os.getenv("PREDICTION_INTERVAL_SECONDS", "3600"))
MODEL_VERSION = os.getenv("MODEL_VERSION", "1.0.0")

SUPPORTED_DISASTER_TYPES = ["flood", "heatwave"]
FORECAST_HORIZONS = [6, 24, 72]


def build_prediction_cycle(
    ssm_model,
    transformer_model,
    ensemble,
    feature_router,
    postgres_store,
    influx_store,
    publisher,
):
    """Return a closure that runs a full prediction cycle for one region."""

    def on_prediction_cycle(region_id: str, readings: List[Dict[str, Any]]) -> None:
        logger.info(
            "Running prediction cycle for region=%s (%d readings)",
            region_id,
            len(readings),
        )
        snapshot_id = str(uuid.uuid4())

        # Collect SSM features per disaster type.
        ssm_features: Dict[str, Any] = {}
        for disaster_type in SUPPORTED_DISASTER_TYPES:
            routed = feature_router.route(disaster_type, readings, region_id)
            ssm_features[disaster_type] = ssm_model.extract_features(routed)

        # Transformer: build region feature map (single region for Phase 1).
        # Use flood SSM vector as the representative region feature.
        region_feature_map = {region_id: ssm_features["flood"]}
        context_map = transformer_model.compute_context(region_feature_map)
        transformer_vector = context_map.get(region_id)

        from models.prediction import PredictionRecord

        for disaster_type in SUPPORTED_DISASTER_TYPES:
            ssm_vec = ssm_features[disaster_type]
            for horizon in FORECAST_HORIZONS:
                risk_level, prob_pct, tti, severity = ensemble.predict(
                    disaster_type=disaster_type,
                    ssm_vector=ssm_vec,
                    transformer_vector=transformer_vector,
                    forecast_horizon_h=horizon,
                )
                record = PredictionRecord.create(
                    region_id=region_id,
                    disaster_type=disaster_type,
                    forecast_horizon_h=horizon,
                    risk_level=risk_level,
                    probability_pct=prob_pct,
                    time_to_impact_h=tti,
                    severity_index=severity,
                    model_version=MODEL_VERSION,
                    input_data_snapshot_id=snapshot_id,
                )

                # Persist to PostgreSQL.
                if postgres_store:
                    try:
                        postgres_store.save(record)
                    except Exception as exc:
                        logger.error("PostgreSQL save failed: %s", exc)

                # Write to InfluxDB.
                if influx_store:
                    try:
                        influx_store.write(record)
                    except Exception as exc:
                        logger.error("InfluxDB write failed: %s", exc)

                # Publish to Kafka.
                if publisher:
                    try:
                        publisher.publish_prediction(record)
                    except Exception as exc:
                        logger.error("Kafka publish failed: %s", exc)

                logger.info(
                    "Prediction: region=%s type=%s horizon=%dh risk=%s prob=%.1f%%",
                    region_id,
                    disaster_type,
                    horizon,
                    risk_level,
                    prob_pct,
                )

    return on_prediction_cycle


def main() -> None:
    logger.info("Starting Prediction Engine Service...")
    logger.info("Kafka brokers: %s", KAFKA_BROKERS)
    logger.info("PostgreSQL URL: %s", POSTGRES_URL)
    logger.info("InfluxDB URL: %s", INFLUXDB_URL)
    logger.info("Prediction interval: %ds", PREDICTION_INTERVAL_SECONDS)

    # --- Engine components ---
    from engine.ssm import SSMModel
    from engine.transformer import TransformerModel
    from engine.ensemble import EnsembleAggregator
    from engine.feature_router import FeatureRouter

    ssm_model = SSMModel()
    transformer_model = TransformerModel()
    ensemble = EnsembleAggregator()
    feature_router = FeatureRouter()

    # --- Storage ---
    from store.postgres import PredictionStore
    from store.influx import InfluxStore

    postgres_store = None
    influx_store = None
    try:
        postgres_store = PredictionStore(POSTGRES_URL)
    except Exception as exc:
        logger.warning("PostgreSQL unavailable, predictions will not be persisted: %s", exc)

    try:
        influx_store = InfluxStore(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG,
        )
    except Exception as exc:
        logger.warning("InfluxDB unavailable, time-series writes disabled: %s", exc)

    # --- Publisher ---
    from publisher import KafkaPublisher

    publisher = None
    try:
        publisher = KafkaPublisher(KAFKA_BROKERS)
    except Exception as exc:
        logger.warning("Kafka publisher unavailable: %s", exc)

    # --- Consumer ---
    from consumer import PredictionConsumer

    on_cycle = build_prediction_cycle(
        ssm_model, transformer_model, ensemble, feature_router,
        postgres_store, influx_store, publisher,
    )

    consumer = PredictionConsumer(
        kafka_brokers=KAFKA_BROKERS,
        prediction_interval_seconds=PREDICTION_INTERVAL_SECONDS,
        on_prediction_cycle=on_cycle,
    )
    consumer.start()

    def shutdown(signum, frame):
        logger.info("Shutting down Prediction Engine Service...")
        consumer.stop()
        if postgres_store:
            postgres_store.close()
        if influx_store:
            influx_store.close()
        if publisher:
            publisher.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    signal.pause()


if __name__ == "__main__":
    main()
