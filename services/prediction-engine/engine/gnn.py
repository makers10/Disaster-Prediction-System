"""GNN (Graph Neural Network) component for region-to-region impact propagation.

Models upstream→downstream flood propagation and cross-region spread for
landslides and cyclones. Uses a Graph Attention Network (GAT) stand-in
based on weighted message passing over a region adjacency graph.

The interface is stable so a real PyTorch Geometric GAT can be swapped in.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Adjacency list: region_id → list of (neighbour_region_id, edge_weight)
# Edge weight represents hydrological/geographic proximity (0–1).
RegionGraph = Dict[str, List[Tuple[str, float]]]


class GNNModel:
    """Lightweight GAT stand-in using weighted message passing.

    For each region, aggregates neighbour feature vectors weighted by
    edge weights and attention scores, then combines with the region's
    own features.

    Args:
        feature_dim: Dimensionality of input/output feature vectors.
        num_iterations: Number of message-passing iterations.
        degraded_mode: If True, skip GNN and return input features unchanged.
    """

    def __init__(
        self,
        feature_dim: int = 16,
        num_iterations: int = 2,
        degraded_mode: bool = False,
    ) -> None:
        self.feature_dim = feature_dim
        self.num_iterations = num_iterations
        self.degraded_mode = degraded_mode

        # Fixed attention projection (seeded for reproducibility)
        rng = np.random.default_rng(seed=77)
        self._attn_proj = rng.standard_normal(feature_dim).astype(np.float32)

    def propagate(
        self,
        region_features: Dict[str, np.ndarray],
        graph: RegionGraph,
    ) -> Dict[str, np.ndarray]:
        """Run GNN message passing over the region graph.

        Args:
            region_features: Mapping of region_id → feature vector (shape: (feature_dim,)).
            graph: Adjacency list with edge weights.

        Returns:
            Updated mapping of region_id → propagated feature vector.
        """
        if self.degraded_mode:
            logger.warning("GNN running in degraded mode — returning input features unchanged")
            return region_features

        if not region_features:
            return region_features

        current = {rid: vec.copy() for rid, vec in region_features.items()}

        for _ in range(self.num_iterations):
            updated: Dict[str, np.ndarray] = {}
            for region_id, own_vec in current.items():
                neighbours = graph.get(region_id, [])
                if not neighbours:
                    updated[region_id] = own_vec
                    continue

                # Compute attention-weighted neighbour aggregation
                neighbour_vecs = []
                edge_weights = []
                for neighbour_id, edge_weight in neighbours:
                    if neighbour_id in current:
                        neighbour_vecs.append(current[neighbour_id])
                        edge_weights.append(edge_weight)

                if not neighbour_vecs:
                    updated[region_id] = own_vec
                    continue

                # Attention scores: dot product with projection vector
                scores = np.array([
                    float(np.dot(v, self._attn_proj)) * w
                    for v, w in zip(neighbour_vecs, edge_weights)
                ])
                # Softmax normalisation
                scores = scores - scores.max()
                attn_weights = np.exp(scores) / np.exp(scores).sum()

                # Aggregate neighbour messages
                aggregated = sum(
                    a * v for a, v in zip(attn_weights, neighbour_vecs)
                )

                # Combine own features with aggregated neighbour features (0.6/0.4 split)
                updated[region_id] = (0.6 * own_vec + 0.4 * aggregated).astype(np.float32)

            current = updated

        return current

    def enable_degraded_mode(self) -> None:
        """Fall back to pass-through mode on computation failure."""
        self.degraded_mode = True
        logger.warning("GNN switched to degraded mode")

    def disable_degraded_mode(self) -> None:
        self.degraded_mode = False


def build_graph_from_db(postgres_url: str) -> RegionGraph:
    """Load region adjacency graph from PostgreSQL (PostGIS).

    Queries the region_adjacency table:
      CREATE TABLE region_adjacency (
        region_id TEXT, neighbour_id TEXT, edge_weight FLOAT
      );

    Falls back to an empty graph if the table doesn't exist.
    """
    graph: RegionGraph = {}
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(postgres_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT region_id, neighbour_id, edge_weight FROM region_adjacency"
            )
            for row in cur.fetchall():
                region_id, neighbour_id, weight = row
                graph.setdefault(region_id, []).append((neighbour_id, float(weight)))
        conn.close()
        logger.info("GNN graph loaded: %d regions", len(graph))
    except Exception as exc:
        logger.warning("GNN graph load failed (using empty graph): %s", exc)
    return graph
