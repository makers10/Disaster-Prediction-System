"""Dijkstra/A* evacuation route computation over a road network graph.

The road network is stored as an adjacency list in PostgreSQL.
Routes avoid predicted flood inundation zones and high landslide risk zones.
"""

from __future__ import annotations

import heapq
import logging
import math
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Node: (lat, lon, label)
Node = Dict[str, Any]
# Edge: (neighbour_node_id, distance_km, road_id)
Edge = Tuple[str, float, str]
# Graph: node_id → list of edges
RoadGraph = Dict[str, List[Edge]]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in km between two GPS points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def dijkstra(
    graph: RoadGraph,
    start_id: str,
    end_id: str,
    blocked_roads: Set[str],
    hazard_nodes: Set[str],
) -> Optional[List[str]]:
    """Find shortest path from start to end avoiding blocked roads and hazard nodes.

    Returns list of node_ids on the path, or None if no path exists.
    """
    dist: Dict[str, float] = {start_id: 0.0}
    prev: Dict[str, Optional[str]] = {start_id: None}
    heap: List[Tuple[float, str]] = [(0.0, start_id)]

    while heap:
        d, node = heapq.heappop(heap)
        if node == end_id:
            # Reconstruct path
            path = []
            cur: Optional[str] = end_id
            while cur is not None:
                path.append(cur)
                cur = prev.get(cur)
            return list(reversed(path))

        if d > dist.get(node, float("inf")):
            continue

        for neighbour, edge_dist, road_id in graph.get(node, []):
            if road_id in blocked_roads:
                continue
            if neighbour in hazard_nodes:
                continue
            new_dist = d + edge_dist
            if new_dist < dist.get(neighbour, float("inf")):
                dist[neighbour] = new_dist
                prev[neighbour] = node
                heapq.heappush(heap, (new_dist, neighbour))

    return None


def load_road_graph(postgres_url: str) -> Tuple[RoadGraph, Dict[str, Node]]:
    """Load road network from PostgreSQL.

    Tables:
      road_nodes(node_id TEXT PK, lat FLOAT, lon FLOAT, label TEXT)
      road_edges(edge_id TEXT PK, from_node TEXT, to_node TEXT, distance_km FLOAT, road_id TEXT, is_blocked BOOL)
    """
    graph: RoadGraph = {}
    nodes: Dict[str, Node] = {}
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(postgres_url)
        with conn.cursor() as cur:
            cur.execute("SELECT node_id, lat, lon, label FROM road_nodes")
            for row in cur.fetchall():
                nodes[row[0]] = {"node_id": row[0], "lat": row[1], "lon": row[2], "label": row[3] or row[0]}

            cur.execute(
                "SELECT from_node, to_node, distance_km, road_id FROM road_edges WHERE NOT is_blocked"
            )
            for row in cur.fetchall():
                from_node, to_node, dist_km, road_id = row
                graph.setdefault(from_node, []).append((to_node, float(dist_km), road_id))
                graph.setdefault(to_node, []).append((from_node, float(dist_km), road_id))  # bidirectional

        conn.close()
        logger.info("Road graph loaded: %d nodes, %d edges", len(nodes), sum(len(v) for v in graph.values()) // 2)
    except Exception as exc:
        logger.warning("Road graph load failed (using empty graph): %s", exc)
    return graph, nodes


def get_blocked_roads(postgres_url: str) -> Set[str]:
    """Get currently blocked road IDs from crowd reports."""
    blocked: Set[str] = set()
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(postgres_url)
        with conn.cursor() as cur:
            cur.execute("SELECT road_id FROM road_edges WHERE is_blocked = true")
            for row in cur.fetchall():
                blocked.add(row[0])
        conn.close()
    except Exception as exc:
        logger.warning("Could not load blocked roads: %s", exc)
    return blocked


def get_hazard_nodes(postgres_url: str, region_id: str) -> Set[str]:
    """Get node IDs in flood inundation or high landslide risk zones for a region."""
    hazard: Set[str] = set()
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(postgres_url)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT rn.node_id FROM road_nodes rn
                   JOIN hazard_zones hz ON ST_Contains(hz.geometry, ST_SetSRID(ST_MakePoint(rn.lon, rn.lat), 4326))
                   WHERE hz.region_id = %s AND hz.hazard_type IN ('flood_inundation', 'landslide_high')""",
                (region_id,),
            )
            for row in cur.fetchall():
                hazard.add(row[0])
        conn.close()
    except Exception as exc:
        logger.debug("Hazard node query failed (PostGIS may not be available): %s", exc)
    return hazard
