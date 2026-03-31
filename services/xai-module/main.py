"""XAI Module Service — SHAP-based explanation generation for predictions."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")
POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction",
)
GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))
INPUT_TOPIC = "prediction.generated"
GROUP_ID = "xai-module"


def _extract_feature_values(prediction: Dict[str, Any]) -> Dict[str, float]:
    """Extract a best-effort feature value dict from a prediction record.

    In production the prediction record would carry the input snapshot.
    Here we derive proxy values from the prediction outputs.
    """
    prob = float(prediction.get("probability_pct", 50.0))
    severity = float(prediction.get("severity_index", 50.0))
    tti = float(prediction.get("time_to_impact_h") or 24.0)
    disaster_type = prediction.get("disaster_type", "flood")

    # Map prediction outputs back to plausible feature values as proxies
    base: Dict[str, float] = {}
    if disaster_type == "flood":
        base = {
            "rainfall_mm": prob * 0.5,
            "river_level_m": prob * 0.03,
            "soil_moisture_pct": severity * 0.8,
            "elevation": max(0.0, 100.0 - severity),
            "drainage_capacity": max(0.0, 100.0 - prob * 0.8),
        }
    elif disaster_type == "heatwave":
        base = {
            "temperature_c": 20.0 + prob * 0.2,
            "humidity": severity * 0.7,
            "wind_speed_kmh": max(0.0, 30.0 - prob * 0.2),
            "historical_heatwave_flag": 1.0 if prob > 50 else 0.0,
        }
    elif disaster_type == "drought":
        base = {
            "rainfall_deficit_mm": -prob * 0.4,
            "soil_moisture_trend": -severity * 0.3,
            "temperature_anomaly_c": prob * 0.1,
            "rolling_window_days": 30.0,
        }
    elif disaster_type == "landslide":
        base = {
            "rainfall_intensity_mm": prob * 0.4,
            "soil_moisture_pct": severity * 0.8,
            "elevation_gradient": prob * 0.005,
            "terrain_slope": severity * 0.3,
        }
    elif disaster_type == "cyclone":
        base = {
            "wind_speed_kmh": prob * 1.5,
            "cloud_density": prob * 0.008,
            "sea_surface_temp_c": 25.0 + prob * 0.05,
            "wind_direction_deg": 180.0,
        }
    return base


def run_consumer(explainer, store) -> None:
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

    logger.info("XAI consumer started on topic: %s", INPUT_TOPIC)

    for message in consumer:
        try:
            prediction: Dict[str, Any] = message.value
            prediction_id = prediction.get("prediction_id", "")
            disaster_type = prediction.get("disaster_type", "flood")
            risk_level = prediction.get("risk_level", "Low")

            feature_values = _extract_feature_values(prediction)

            explanation = explainer.explain(
                prediction_id=prediction_id,
                disaster_type=disaster_type,
                risk_level=risk_level,
                feature_values=feature_values,
            )

            if store:
                try:
                    store.save(explanation)
                except Exception as exc:
                    logger.error("Failed to save explanation: %s", exc)

            logger.info(
                "Explanation generated: prediction_id=%s summary=%s",
                prediction_id,
                explanation.plain_language_summary,
            )
        except Exception as exc:
            logger.error("Error generating explanation: %s", exc)

    consumer.close()


def start_grpc_server(store, port: int) -> None:
    """Start a minimal HTTP server as a stand-in for the gRPC endpoint.

    Exposes GET /explanation?prediction_id=<uuid> returning JSON within 10s SLA.
    A real gRPC server would be wired here in production.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse, parse_qs

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/explanation":
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(parsed.query)
            prediction_id = (params.get("prediction_id") or [""])[0]
            if not prediction_id:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"prediction_id required"}')
                return
            result = store.get_by_prediction_id(prediction_id) if store else None
            if result is None:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error":"not found"}')
                return
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            logger.debug("XAI HTTP: " + fmt, *args)

    server = HTTPServer(("0.0.0.0", port), Handler)
    logger.info("XAI explanation endpoint listening on port %d", port)
    server.serve_forever()


def main() -> None:
    logger.info("Starting XAI Module Service...")
    logger.info("Kafka brokers: %s", KAFKA_BROKERS)
    logger.info("PostgreSQL URL: %s", POSTGRES_URL)
    logger.info("Explanation endpoint port: %d", GRPC_PORT)

    from explainer import SHAPExplainer
    from store import ExplanationStore

    explainer = SHAPExplainer()
    store = None
    try:
        store = ExplanationStore(POSTGRES_URL)
    except Exception as exc:
        logger.warning("PostgreSQL unavailable, explanations will not be persisted: %s", exc)

    # Start HTTP explanation endpoint in background thread
    threading.Thread(
        target=start_grpc_server, args=(store, GRPC_PORT), daemon=True, name="xai-http"
    ).start()

    # Start Kafka consumer in background thread
    threading.Thread(
        target=run_consumer, args=(explainer, store), daemon=True, name="xai-consumer"
    ).start()

    def shutdown(signum, frame):
        logger.info("Shutting down XAI Module Service...")
        if store:
            store.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    signal.pause()


if __name__ == "__main__":
    main()
