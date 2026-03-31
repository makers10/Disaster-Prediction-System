"""Evacuation Planner Service — computes evacuation routes for High-risk regions."""

import logging
import os
import signal
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Starting Evacuation Planner Service...")

    kafka_brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
    postgres_url = os.getenv("POSTGRES_URL", "postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction")

    logger.info("Kafka brokers: %s", kafka_brokers)
    logger.info("PostgreSQL URL: %s", postgres_url)

    # TODO: Initialize Kafka consumer for prediction.generated (filter risk_level=High)
    # TODO: Load road network graph from PostgreSQL (PostGIS)
    # TODO: Implement Dijkstra/A* route computation
    # TODO: Publish evacuation.route.updated events
    # TODO: Handle crowd.report.submitted events for road blockages (recompute within 10 min)

    def shutdown(signum, frame):
        logger.info("Shutting down Evacuation Planner Service...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    signal.pause()


if __name__ == "__main__":
    main()
