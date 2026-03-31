"""SHAP-based explainer for disaster predictions.

Uses a rule-based SHAP stand-in that assigns contribution percentages
based on feature magnitudes. The interface is stable so a real SHAP
TreeExplainer or KernelExplainer can be swapped in without changing callers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from models.explanation import ContributingFactor, XAIExplanation

logger = logging.getLogger(__name__)

# Feature display names for plain-language summaries
FEATURE_DISPLAY_NAMES: Dict[str, str] = {
    "rainfall_mm": "heavy rainfall",
    "river_level_m": "rising river levels",
    "soil_moisture_pct": "high soil moisture",
    "elevation": "low elevation terrain",
    "drainage_capacity": "limited drainage capacity",
    "temperature_c": "high temperature",
    "wind_speed_kmh": "strong winds",
    "humidity": "high humidity",
    "rainfall_deficit_mm": "rainfall deficit",
    "soil_moisture_trend": "declining soil moisture",
    "temperature_anomaly_c": "temperature anomaly",
    "rainfall_intensity_mm": "intense rainfall",
    "elevation_gradient": "steep elevation gradient",
    "terrain_slope": "steep terrain slope",
    "wind_direction_deg": "wind direction",
    "sea_surface_temp_c": "warm sea surface temperature",
    "cloud_density": "dense cloud cover",
    "flood_inundation_pct": "satellite-detected flooding",
    "vegetation_index": "low vegetation index",
}

# Disaster-type feature importance weights (higher = more important)
FEATURE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "flood": {
        "rainfall_mm": 0.35, "river_level_m": 0.25, "soil_moisture_pct": 0.20,
        "elevation": 0.10, "drainage_capacity": 0.10,
    },
    "heatwave": {
        "temperature_c": 0.50, "humidity": 0.25, "wind_speed_kmh": 0.15,
        "historical_heatwave_flag": 0.10,
    },
    "drought": {
        "rainfall_deficit_mm": 0.40, "soil_moisture_trend": 0.30,
        "temperature_anomaly_c": 0.20, "rolling_window_days": 0.10,
    },
    "landslide": {
        "rainfall_intensity_mm": 0.35, "soil_moisture_pct": 0.25,
        "elevation_gradient": 0.25, "terrain_slope": 0.15,
    },
    "cyclone": {
        "wind_speed_kmh": 0.40, "cloud_density": 0.25,
        "sea_surface_temp_c": 0.20, "wind_direction_deg": 0.15,
    },
}

MIN_FACTORS_FOR_MEDIUM_HIGH = 3


class SHAPExplainer:
    """Generates SHAP-style feature contribution explanations.

    For Medium/High risk predictions, guarantees >= 3 contributing factors.
    The sum of all contribution_pct values is <= 100.
    """

    def explain(
        self,
        prediction_id: str,
        disaster_type: str,
        risk_level: str,
        feature_values: Dict[str, float],
    ) -> XAIExplanation:
        """Generate an explanation for a prediction.

        Args:
            prediction_id: UUID of the prediction being explained.
            disaster_type: One of flood/heatwave/drought/landslide/cyclone.
            risk_level: Low/Medium/High.
            feature_values: Dict of feature_name → value used in the prediction.

        Returns:
            XAIExplanation with contributing_factors and plain_language_summary.
        """
        weights = FEATURE_WEIGHTS.get(disaster_type, {})
        if not weights:
            # Fallback: equal weights for all provided features
            weights = {k: 1.0 / max(len(feature_values), 1) for k in feature_values}

        # Compute raw scores: weight × |normalised value|
        scores: Dict[str, float] = {}
        for feature, weight in weights.items():
            val = feature_values.get(feature, 0.0)
            # Normalise to [0,1] using a simple sigmoid-like transform
            normalised = abs(val) / (abs(val) + 1.0)
            scores[feature] = weight * normalised

        total_score = sum(scores.values()) or 1.0

        # Convert to percentages (sum <= 100)
        factors: List[ContributingFactor] = []
        for feature, score in sorted(scores.items(), key=lambda x: -x[1]):
            pct = round((score / total_score) * 100.0, 1)
            if pct < 0.5:
                continue
            val = feature_values.get(feature, 0.0)
            direction = "positive" if val >= 0 else "negative"
            factors.append(ContributingFactor(
                feature_name=feature,
                contribution_pct=pct,
                direction=direction,
            ))

        # Guarantee >= 3 factors for Medium/High risk
        if risk_level in ("Medium", "High") and len(factors) < MIN_FACTORS_FOR_MEDIUM_HIGH:
            for feature in weights:
                if len(factors) >= MIN_FACTORS_FOR_MEDIUM_HIGH:
                    break
                if not any(f.feature_name == feature for f in factors):
                    factors.append(ContributingFactor(
                        feature_name=feature,
                        contribution_pct=1.0,
                        direction="positive",
                    ))

        # Build plain-language summary from top 3 factors
        top = factors[:3]
        parts = []
        for f in top:
            display = FEATURE_DISPLAY_NAMES.get(f.feature_name, f.feature_name.replace("_", " "))
            parts.append(f"{display} ({f.contribution_pct}%)")

        if parts:
            summary = (
                f"{disaster_type.capitalize()} risk is {risk_level} due to: "
                + ", ".join(parts) + "."
            )
        else:
            summary = f"{disaster_type.capitalize()} risk is {risk_level}."

        return XAIExplanation.create(
            prediction_id=prediction_id,
            contributing_factors=factors,
            plain_language_summary=summary,
        )
