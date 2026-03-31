"""TransformerModel — attention-weighted average stand-in.

The interface is designed so a real multi-head self-attention Transformer can
be swapped in without changing callers.  The stand-in computes a simple
softmax-attention-weighted average over the per-region SSM feature vectors,
returning a global context vector for each region.
"""

from __future__ import annotations

from typing import Dict

import numpy as np


class TransformerModel:
    """Lightweight Transformer stand-in: attention-weighted average.

    Args:
        feature_dim: Dimensionality of input/output feature vectors.
        temperature: Softmax temperature.  Lower = sharper attention.
    """

    def __init__(self, feature_dim: int = 16, temperature: float = 1.0) -> None:
        if temperature <= 0:
            raise ValueError(f"temperature must be > 0, got {temperature}")
        self.feature_dim = feature_dim
        self.temperature = temperature

        # Fixed query vector used to compute attention scores.
        rng = np.random.default_rng(seed=7)
        self.query = rng.standard_normal(feature_dim).astype(np.float32)

    def compute_context(
        self, region_features: Dict[str, np.ndarray]
    ) -> Dict[str, np.ndarray]:
        """Compute a global context vector for each region.

        Args:
            region_features: Mapping of region_id → SSM feature vector
                             (shape: (feature_dim,)).

        Returns:
            Mapping of region_id → context vector (shape: (feature_dim,)).
            Each context vector is the attention-weighted average of *all*
            region feature vectors, giving each region a global view.
        """
        if not region_features:
            return {}

        region_ids = list(region_features.keys())
        # Stack into (N, feature_dim) matrix.
        feature_matrix = np.stack(
            [region_features[rid] for rid in region_ids], axis=0
        )  # (N, D)

        # Attention scores: dot product of each feature vector with the query.
        scores = feature_matrix @ self.query / self.temperature  # (N,)
        # Softmax normalisation.
        scores = scores - scores.max()  # numerical stability
        weights = np.exp(scores)
        weights = weights / weights.sum()  # (N,)

        # Global context = weighted average of all feature vectors.
        global_context = (weights[:, None] * feature_matrix).sum(axis=0)  # (D,)

        # Each region gets the same global context (stand-in for cross-attention).
        return {rid: global_context.astype(np.float32) for rid in region_ids}
