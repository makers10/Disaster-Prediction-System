"""EnsembleAggregator — combines SSM and Transformer outputs into a prediction.

Disaster-type-specific weights are configurable dicts.  The aggregator maps
the combined feature vector to (risk_level, probability_pct, time_to_impact_h,
severity_index).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

from models.prediction import RiskLevel

# Default weights per disaster type: (ssm_weight, transformer_weight).
# Must sum to 1.0 for each type.
DEFAULT_WEIGHTS: Dict[str, Tuple[float, float]] = {
    "flood":    (0.6, 0.4),
    "heatwave": (0.5, 0.5),
    "drought":  (0.7, 0.3),
    "landslide":(0.6, 0.4),
    "cyclone":  (0.4, 0.6),
}

# Thresholds for risk level classification based on probability.
_RISK_HIGH_THRESHOLD = 65.0
_RISK_MEDIUM_THRESHOLD = 35.0


class EnsembleAggregator:
    """Weighted ensemble of SSM and Transformer feature vectors.

    Args:
        weights: Optional override dict mapping disaster_type →
                 (ssm_weight, transformer_weight).  Weights must sum to 1.
    """

    def __init__(
        self, weights: Optional[Dict[str, Tuple[float, float]]] = None
    ) -> None:
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        # Validate weights.
        for dtype, (w_ssm, w_tf) in self.weights.items():
            if abs(w_ssm + w_tf - 1.0) > 1e-6:
                raise ValueError(
                    f"Weights for '{dtype}' must sum to 1.0, got {w_ssm + w_tf}"
                )

        # Fixed projection from feature_dim → scalar score, seeded for
        # reproducibility.  In production this would be a trained head.
        rng = np.random.default_rng(seed=99)
        self._score_proj = rng.standard_normal(16).astype(np.float32)

    def predict(
        self,
        disaster_type: str,
        ssm_vector: np.ndarray,
        transformer_vector: np.ndarray,
        forecast_horizon_h: int,
    ) -> Tuple[RiskLevel, float, Optional[float], float]:
        """Combine model outputs into a single prediction tuple.

        Args:
            disaster_type: One of flood/heatwave/drought/landslide/cyclone.
            ssm_vector: Feature vector from SSMModel (shape: (feature_dim,)).
            transformer_vector: Context vector from TransformerModel.
            forecast_horizon_h: 6, 24, or 72.

        Returns:
            (risk_level, probability_pct, time_to_impact_h, severity_index)
        """
        w_ssm, w_tf = self.weights.get(disaster_type, (0.5, 0.5))
        combined = w_ssm * ssm_vector + w_tf * transformer_vector  # (D,)

        # Map combined vector to a raw score in [0, 1] via sigmoid.
        raw_score = float(np.dot(combined, self._score_proj))
        probability_pct = 100.0 / (1.0 + np.exp(-raw_score))  # sigmoid → (0,100)

        # Horizon discount: longer horizons have slightly lower probability.
        horizon_discount = {6: 1.0, 24: 0.92, 72: 0.82}.get(forecast_horizon_h, 1.0)
        probability_pct = float(np.clip(probability_pct * horizon_discount, 0.0, 100.0))

        # Classify risk level.
        if probability_pct >= _RISK_HIGH_THRESHOLD:
            risk_level: RiskLevel = "High"
        elif probability_pct >= _RISK_MEDIUM_THRESHOLD:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        # time_to_impact_h: null for Low risk; otherwise scale with horizon.
        if risk_level == "Low":
            time_to_impact_h: Optional[float] = None
        else:
            # Estimate: fraction of horizon proportional to inverse probability.
            fraction = 1.0 - (probability_pct - _RISK_MEDIUM_THRESHOLD) / (
                100.0 - _RISK_MEDIUM_THRESHOLD
            )
            time_to_impact_h = float(
                np.clip(fraction * forecast_horizon_h, 0.0, forecast_horizon_h)
            )

        # Severity index: scaled probability with a small horizon penalty.
        severity_index = float(
            np.clip(probability_pct * 0.9 * horizon_discount, 0.0, 100.0)
        )

        return risk_level, probability_pct, time_to_impact_h, severity_index
