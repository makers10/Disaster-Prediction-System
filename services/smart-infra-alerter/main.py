"""Smart Infrastructure Alerter Service.

Consumes prediction.generated events. For flood predictions with
risk_level Medium or High, checks if the affected region contains
registered infrastructure assets (dams, urban drainage) and generates
infrastructure-specific alerts dispatched within 5 minutes.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")
POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction",
)
INPUT_TOPIC = "prediction.generated"
ALERT_TOPIC = "alert.dispatched"
GROUP_ID = "smart-infra-alerter"

_CREATE_INFRA_TABLE = """
CREATE TABLE IF NOT EXISTS infrastructure_assets (
    asset_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_id       TEXT NOT NULL,
    asset_type      TEXT NOT NULL CHECK (asset_type IN ('dam', 'urban_drainage')),
    name            TEXT NOT NULL,
    lat             FLOAT NOT NULL,
    lon             FLOAT NOT NULL,
    operator_user_ids TEXT[] NOT NULL DEFAULT '{}',
    capacity_m3     FLOAT
);
CREATE INDEX IF NOT EXISTS idx_infra_region ON infrastructure_assets(region_id);
"""


def ensure_schema(postgres_url: str) -> None:
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(postgres_url)
        with conn.cursor() as cur:
            cur.execute(_CREATE_INFRA_TABLE)
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("Could not ensure infrastructure schema: %s", exc)


def get_assets_for_region(postgres_url: str, region_id: str) -> List[Dict[str, Any]]:
    """Query registered infrastructure assets for a region."""
    assets = []
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(postgres_url)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT asset_id::text, region_id, asset_type, name,
                          lat, lon, operator_user_ids, capacity_m3
                   FROM infrastructure_assets
                   WHERE region_id = %s""",
                (region_id,),
            )
            for row in cur.fetchall():
                assets.append({
                    "asset_id": row[0],
                    "region_id": row[1],
                    "asset_type": row[2],
                    "name": row[3],
                    "lat": row[4],
                    "lon": row[5],
                    "operator_user_ids": list(row[6] or []),
                    "capacity_m3": row[7],
                })
        conn.close()
    except Exception as exc:
        logger.warning("Could not query infrastructure assets: %s", exc)
    return assets


def build_infra_alert(
    prediction: Dict[str, Any],
    asset: Dict[str, Any],
) -> Dict[str, Any]:
    """Build an infrastructure-specific alert record."""
    asset_type = asset["asset_type"]
    risk_level = prediction.get("risk_level", "Medium")
    tti = prediction.get("time_to_impact_h")

    if asset_type == "dam":
        recommended_action = (
            f"Dam overflow risk detected at {asset['name']}. "
            f"Inspect dam levels immediately. "
            + (f"Estimated time to impact: {tti}h." if tti else "")
        )
    else:
        recommended_action = (
            f"Urban drainage failure likely at {asset['name']}. "
            f"Check drainage capacity and clear blockages. "
            + (f"Estimated time to impact: {tti}h." if tti else "")
        )

    return {
        "alert_id": str(uuid.uuid4()),
        "prediction_id": prediction.get("prediction_id", ""),
        "region_id": prediction.get("region_id", ""),
        "disaster_type": "flood",
        "risk_level": risk_level,
        "time_to_impact_h": tti or 0,
        "recommended_action": recommended_action,
        "evacuation_route_id": None,
        "language_code": "en",
        "channel": "push",
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "delivery_status": "sent",
        "retry_count": 0,
        "infrastructure_asset_id": asset["asset_id"],
        "infrastructure_asset_type": asset_type,
        "infrastructure_asset_name": asset["name"],
        "operator_user_ids": asset["operator_user_ids"],
    }


def run_consumer(publisher) -> None:
    try:
        from kafka import KafkaConsumer  # type: ignore
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

    logger.info("Smart Infrastructure Alerter consumer started")

    for message in consumer:
        try:
            prediction: Dict[str, Any] = message.value
            disaster_type = prediction.get("disaster_type", "")
            risk_level = prediction.get("risk_level", "Low")
            region_id = prediction.get("region_id", "")

            # Only process flood predictions with Medium or High risk
            if disaster_type != "flood" or risk_level not in ("Medium", "High"):
                continue

            assets = get_assets_for_region(POSTGRES_URL, region_id)
            if not assets:
                continue

            for asset in assets:
                alert = build_infra_alert(prediction, asset)
                if publisher:
                    try:
                        future = publisher.send(ALERT_TOPIC, value=json.dumps(alert).encode())
                        future.get(timeout=10)
                        logger.info(
                            "Infrastructure alert dispatched: region=%s asset=%s type=%s risk=%s",
                            region_id, asset["name"], asset["asset_type"], risk_level,
                        )
                    except Exception as exc:
                        logger.error("Failed to publish infrastructure alert: %s", exc)

        except Exception as exc:
            logger.error("Smart infra alerter error: %s", exc)

    consumer.close()


def main() -> None:
    logger.info("Starting Smart Infrastructure Alerter Service...")
    logger.info("Kafka brokers: %s", KAFKA_BROKERS)
    logger.info("PostgreSQL URL: %s", POSTGRES_URL)

    ensure_schema(POSTGRES_URL)

    publisher = None
    try:
        from kafka import KafkaProducer  # type: ignore
        publisher = KafkaProducer(
            bootstrap_servers=KAFKA_BROKERS.split(","),
            acks="all",
            retries=3,
        )
    except Exception as exc:
        logger.warning("Kafka publisher unavailable: %s", exc)

    threading.Thread(
        target=run_consumer,
        args=(publisher,),
        daemon=True,
        name="infra-consumer",
    ).start()

    def shutdown(signum, frame):
        logger.info("Shutting down Smart Infrastructure Alerter Service...")
        if publisher:
            publisher.flush()
            publisher.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    signal.pause()


if __name__ == "__main__":
    main()
