"""PostgreSQL store for evacuation routes."""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS evacuation_routes (
    route_id            UUID PRIMARY KEY,
    region_id           TEXT NOT NULL,
    prediction_id       UUID NOT NULL,
    origin_lat          FLOAT NOT NULL,
    origin_lon          FLOAT NOT NULL,
    origin_label        TEXT NOT NULL,
    destination_lat     FLOAT NOT NULL,
    destination_lon     FLOAT NOT NULL,
    destination_label   TEXT NOT NULL,
    waypoints           JSONB NOT NULL,
    distance_km         FLOAT NOT NULL,
    estimated_duration_min FLOAT NOT NULL,
    avoids              JSONB NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_blocked          BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_evac_routes_region ON evacuation_routes(region_id);
"""

_UPSERT_SQL = """
INSERT INTO evacuation_routes
    (route_id, region_id, prediction_id, origin_lat, origin_lon, origin_label,
     destination_lat, destination_lon, destination_label, waypoints,
     distance_km, estimated_duration_min, avoids, computed_at, is_blocked)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (route_id) DO UPDATE SET
    waypoints = EXCLUDED.waypoints,
    distance_km = EXCLUDED.distance_km,
    estimated_duration_min = EXCLUDED.estimated_duration_min,
    avoids = EXCLUDED.avoids,
    computed_at = EXCLUDED.computed_at,
    is_blocked = EXCLUDED.is_blocked;
"""


class RouteStore:
    def __init__(self, postgres_url: str) -> None:
        self._conn = None
        try:
            import psycopg2  # type: ignore
            self._conn = psycopg2.connect(postgres_url)
            self._conn.autocommit = False
            with self._conn.cursor() as cur:
                cur.execute(_CREATE_SQL)
            self._conn.commit()
            logger.info("RouteStore connected to PostgreSQL.")
        except Exception as exc:
            logger.error("RouteStore: connection failed: %s", exc)

    def save(self, route: dict) -> None:
        if not self._conn:
            return
        try:
            with self._conn.cursor() as cur:
                cur.execute(_UPSERT_SQL, (
                    route["route_id"], route["region_id"], route["prediction_id"],
                    route["origin"]["lat"], route["origin"]["lon"], route["origin"]["label"],
                    route["destination"]["lat"], route["destination"]["lon"], route["destination"]["label"],
                    json.dumps(route["waypoints"]),
                    route["distance_km"], route["estimated_duration_min"],
                    json.dumps(route["avoids"]),
                    route["computed_at"], route.get("is_blocked", False),
                ))
            self._conn.commit()
        except Exception as exc:
            self._conn.rollback()
            logger.error("RouteStore.save failed: %s", exc)

    def mark_blocked(self, route_id: str) -> None:
        if not self._conn:
            return
        try:
            with self._conn.cursor() as cur:
                cur.execute("UPDATE evacuation_routes SET is_blocked=TRUE WHERE route_id=%s", (route_id,))
            self._conn.commit()
        except Exception as exc:
            self._conn.rollback()
            logger.error("RouteStore.mark_blocked failed: %s", exc)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
