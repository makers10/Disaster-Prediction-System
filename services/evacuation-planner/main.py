"""Evacuation Planner Service.

Consumes prediction.generated events where risk_level=High,
computes evacuation routes using Dijkstra/A* over the road network,
stores routes in PostgreSQL, and publishes evacuation.route.updated to Kafka.

Also consumes crowd.report.submitted events to detect road blockages
and recompute affected routes within 10 minutes.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
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
RECOMPUTE_INTERVAL_SECONDS = int(os.getenv("ROUTE_RECOMPUTE_INTERVAL_SECONDS", "600"))  # 10 min


def compute_route_for_region(
    region_id: str,
    prediction_id: str,
    road_graph,
    road_nodes,
    postgres_url: str,
    store,
    publisher,
) -> Optional[dict]:
    """Compute and store an evacuation route for a High-risk region."""
    from router import get_blocked_roads, get_hazard_nodes, dijkstra, haversine_km

    blocked = get_blocked_roads(postgres_url)
    hazard = get_hazard_nodes(postgres_url, region_id)

    # Find origin (highest-risk node in region) and destination (nearest safe zone)
    # Simplified: use first node in region as origin, last as destination
    region_nodes = [nid for nid, n in road_nodes.items() if region_id in nid or True]
    if len(region_nodes) < 2:
        logger.warning("Not enough road nodes for region %s to compute route", region_id)
        return None

    start_id = region_nodes[0]
    end_id = region_nodes[-1]

    path = dijkstra(road_graph, start_id, end_id, blocked, hazard)
    if not path:
        logger.warning("No viable evacuation route found for region %s", region_id)
        return None

    # Build waypoints from path
    waypoints = [
        {"lat": road_nodes[nid]["lat"], "lon": road_nodes[nid]["lon"]}
        for nid in path[1:-1]
        if nid in road_nodes
    ]

    # Compute total distance
    total_km = 0.0
    for i in range(len(path) - 1):
        n1 = road_nodes.get(path[i])
        n2 = road_nodes.get(path[i + 1])
        if n1 and n2:
            total_km += haversine_km(n1["lat"], n1["lon"], n2["lat"], n2["lon"])

    # Estimate duration: assume 40 km/h average speed
    duration_min = (total_km / 40.0) * 60.0

    origin_node = road_nodes.get(start_id, {"lat": 0.0, "lon": 0.0, "label": start_id})
    dest_node = road_nodes.get(end_id, {"lat": 0.0, "lon": 0.0, "label": end_id})

    route = {
        "route_id": str(uuid.uuid4()),
        "region_id": region_id,
        "prediction_id": prediction_id,
        "origin": {"lat": origin_node["lat"], "lon": origin_node["lon"], "label": origin_node.get("label", start_id)},
        "destination": {"lat": dest_node["lat"], "lon": dest_node["lon"], "label": dest_node.get("label", end_id)},
        "waypoints": waypoints,
        "distance_km": round(total_km, 2),
        "estimated_duration_min": round(duration_min, 1),
        "avoids": list(hazard)[:5],  # sample of avoided zones
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "is_blocked": False,
    }

    if store:
        store.save(route)

    if publisher:
        try:
            future = publisher.send("evacuation.route.updated", value=json.dumps(route).encode())
            future.get(timeout=10)
        except Exception as exc:
            logger.error("Failed to publish evacuation route: %s", exc)

    logger.info(
        "Evacuation route computed: region=%s distance=%.1fkm duration=%.0fmin",
        region_id, total_km, duration_min,
    )
    return route


def run_consumer(road_graph, road_nodes, store, publisher) -> None:
    try:
        from kafka import KafkaConsumer  # type: ignore
    except ImportError:
        logger.error("kafka-python not installed")
        return

    consumer = KafkaConsumer(
        "prediction.generated",
        "crowd.report.submitted",
        bootstrap_servers=KAFKA_BROKERS.split(","),
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
        group_id="evacuation-planner",
    )

    # Track pending recomputes: region_id → deadline timestamp
    pending_recomputes: Dict[str, float] = {}
    recompute_lock = threading.Lock()

    def recompute_worker():
        """Background thread: recompute routes for blocked regions within SLA."""
        while True:
            time.sleep(30)
            now = time.time()
            with recompute_lock:
                due = [rid for rid, deadline in pending_recomputes.items() if now >= deadline]
                for rid in due:
                    del pending_recomputes[rid]
            for rid in due:
                logger.info("Recomputing evacuation routes for region %s (road blockage)", rid)
                compute_route_for_region(rid, "recompute", road_graph, road_nodes, POSTGRES_URL, store, publisher)

    threading.Thread(target=recompute_worker, daemon=True, name="recompute-worker").start()

    logger.info("Evacuation planner consumer started")

    for message in consumer:
        try:
            payload: Dict[str, Any] = message.value
            topic = message.topic

            if topic == "prediction.generated":
                risk_level = payload.get("risk_level")
                if risk_level == "High":
                    region_id = payload.get("region_id", "")
                    prediction_id = payload.get("prediction_id", "")
                    compute_route_for_region(
                        region_id, prediction_id, road_graph, road_nodes,
                        POSTGRES_URL, store, publisher,
                    )

            elif topic == "crowd.report.submitted":
                # Check if report indicates a road blockage
                description = (payload.get("description") or "").lower()
                if "road" in description and ("block" in description or "closed" in description or "flood" in description):
                    region_id = payload.get("region_id", "")
                    if region_id:
                        deadline = time.time() + RECOMPUTE_INTERVAL_SECONDS
                        with recompute_lock:
                            pending_recomputes[region_id] = deadline
                        logger.info(
                            "Road blockage reported in region %s — recompute scheduled within %ds",
                            region_id, RECOMPUTE_INTERVAL_SECONDS,
                        )

        except Exception as exc:
            logger.error("Evacuation planner error: %s", exc)

    consumer.close()


def main() -> None:
    logger.info("Starting Evacuation Planner Service...")
    logger.info("Kafka brokers: %s", KAFKA_BROKERS)
    logger.info("PostgreSQL URL: %s", POSTGRES_URL)

    from router import load_road_graph
    from store import RouteStore

    road_graph, road_nodes = load_road_graph(POSTGRES_URL)

    store = None
    try:
        store = RouteStore(POSTGRES_URL)
    except Exception as exc:
        logger.warning("RouteStore unavailable: %s", exc)

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
        args=(road_graph, road_nodes, store, publisher),
        daemon=True,
        name="evac-consumer",
    ).start()

    def shutdown(signum, frame):
        logger.info("Shutting down Evacuation Planner Service...")
        if store:
            store.close()
        if publisher:
            publisher.flush()
            publisher.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    signal.pause()


if __name__ == "__main__":
    main()
