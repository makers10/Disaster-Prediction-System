"""SSMModel — State Space Model stand-in using exponential moving average.

The interface is designed so a real Mamba/S4 implementation can be swapped in
without changing callers.  The EMA captures seasonal/long-term temporal trends
in sensor time-series data.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np


class SSMModel:
    """Lightweight SSM stand-in: exponential moving average over sensor fields.

    Args:
        alpha: EMA smoothing factor in (0, 1].  Closer to 1 = more weight on
               recent readings.  Default 0.3 mimics a slow-decaying memory.
        feature_dim: Size of the output feature vector.  Defaults to 16.
    """

    def __init__(self, alpha: float = 0.3, feature_dim: int = 16) -> None:
        if not (0 < alpha <= 1):
            raise ValueError(f"alpha must be in (0, 1], got {alpha}")
        self.alpha = alpha
        self.feature_dim = feature_dim

        # Ordered sensor fields we extract from each reading dict.
        self._sensor_fields = [
            "rainfall_mm",
            "temperature_c",
            "river_level_m",
            "soil_moisture_pct",
            "wind_speed_kmh",
            "wind_direction_deg",
        ]

    def extract_features(self, readings: List[Dict[str, Any]]) -> np.ndarray:
        """Compute an EMA-based feature vector from a time-ordered list of readings.

        Args:
            readings: List of sensor reading dicts (oldest first).  Each dict
                      should contain at least some of the sensor fields; missing
                      or None values are treated as 0.

        Returns:
            1-D numpy array of length ``feature_dim``.
        """
        if not readings:
            return np.zeros(self.feature_dim)

        # Build a (T, num_fields) matrix, replacing None/missing with 0.
        num_fields = len(self._sensor_fields)
        matrix = np.zeros((len(readings), num_fields))
        for t, reading in enumerate(readings):
            for f, field in enumerate(self._sensor_fields):
                val = reading.get(field)
                matrix[t, f] = float(val) if val is not None else 0.0

        # Compute EMA along the time axis (row-wise).
        ema = matrix[0].copy()
        for t in range(1, len(matrix)):
            ema = self.alpha * matrix[t] + (1 - self.alpha) * ema

        # Project to feature_dim via a fixed (deterministic) linear map.
        # Using a seeded random projection so the mapping is reproducible.
        rng = np.random.default_rng(seed=42)
        projection = rng.standard_normal((num_fields, self.feature_dim))
        feature_vector = ema @ projection  # shape: (feature_dim,)

        # Normalise to unit length to keep magnitudes stable.
        norm = np.linalg.norm(feature_vector)
        if norm > 0:
            feature_vector = feature_vector / norm

        return feature_vector.astype(np.float32)
