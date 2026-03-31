"""XAI Module Service — SHAP-based explanation generation for predictions."""

import logging
import os
import signal
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Starting XAI Module Service...")

    kafka_brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
    postgres_url = os.getenv("POSTGRES_URL", "postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction")
    grpc_port = int(os.getenv("GRPC_PORT", "50051"))

    logger.info("Kafka brokers: %s", kafka_brokers)
    logger.info("PostgreSQL URL: %s", postgres_url)
    logger.info("gRPC port: %d", grpc_port)

    # TODO: Initialize Kafka consumer for prediction.generated
    # TODO: Initialize SHAP explainer
    # TODO: Start gRPC server for on-demand explanation retrieval (SLA <= 10s)
    # TODO: Persist XAIExplanation records to PostgreSQL

    def shutdown(signum, frame):
        logger.info("Shutting down XAI Module Service...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    signal.pause()


if __name__ == "__main__":
    main()
