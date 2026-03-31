"""FeatureRouter — routes sensor readings to the correct feature set per disaster type.

Feature sets per disaster type (Phase 1: flood + heatwave):
  flood:    rainfall_mm, river_level_m, soil_moisture_pct, elevation (terrain),
            drainage_capacity
  heatwave: temperature_c, wind_speed_kmh, humidity (proxy: soil_moisture_pct),
            historical_heatwave_flag
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# Sensor fields used per disaster type.
FLOOD_FIELDS = [
    "rainfall_mm",
    "river_level_m",
    "soil_moisture_pct",
    "elevation",          # from terrain data
    "drainage_capacity",  # from urban drainage data
]

HEATWAVE_FIELDS = [
    "temperature_c",
    "wind_speed_kmh",
    "humidity",                  # derived from soil_moisture_pct as proxy
    "historical_heatwave_flag",  # 0 or 1
]

DISASTER_FIELDS: Dict[str, List[str]] = {
    "flood": FLOOD_FIELDS,
    "heatwave": HEATWAVE_FIELDS,
}


class FeatureRouter:
    """Routes and enriches sensor readings for a specific disaster type.

    Args:
        terrain_data: Optional dict mapping region_id → {elevation, drainage_capacity}.
    """

    def __init__(
        self,
        terrain_data: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.terrain_data: Dict[str, Dict[str, Any]] = terrain_data or {}

    def route(
        self,
        disaster_type: str,
        readings: List[Dict[str, Any]],
        region_id: str,
        historical_flags: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return a list of feature dicts filtered to the disaster type's fields.

        Args:
            disaster_type: e.g. "flood" or "heatwave".
            readings: Raw sensor reading dicts for the region.
            region_id: Used to look up terrain/drainage data.
            historical_flags: Optional dict with historical signal values
                              (e.g. {"historical_heatwave_flag": 1}).

        Returns:
            List of dicts containing only the relevant feature fields.
        """
        fields = DISASTER_FIELDS.get(disaster_type, [])
        terrain = self.terrain_data.get(region_id, {})
        flags = historical_flags or {}

        routed: List[Dict[str, Any]] = []
        for reading in readings:
            enriched: Dict[str, Any] = {}
            for field in fields:
                if field == "elevation":
                    enriched[field] = terrain.get("elevation", 0.0)
                elif field == "drainage_capacity":
                    enriched[field] = terrain.get("drainage_capacity", 0.0)
                elif field == "humidity":
                    # Proxy: humidity ≈ soil_moisture_pct / 100 * 100 (keep as pct)
                    sm = reading.get("soil_moisture_pct")
                    enriched[field] = float(sm) if sm is not None else 0.0
                elif field == "historical_heatwave_flag":
                    enriched[field] = float(flags.get("historical_heatwave_flag", 0))
                else:
                    val = reading.get(field)
                    enriched[field] = float(val) if val is not None else 0.0
            routed.append(enriched)

        return routed

    def get_required_fields(self, disaster_type: str) -> List[str]:
        """Return the list of required feature fields for a disaster type."""
        return list(DISASTER_FIELDS.get(disaster_type, []))
