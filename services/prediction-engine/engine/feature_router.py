"""FeatureRouter — routes sensor readings to the correct feature set per disaster type.

Feature sets per disaster type (Phase 2: all 5 types):
  flood:     rainfall_mm, river_level_m, soil_moisture_pct, elevation (terrain),
             drainage_capacity
  heatwave:  temperature_c, wind_speed_kmh, humidity (proxy: soil_moisture_pct),
             historical_heatwave_flag
  drought:   rainfall_deficit_mm, soil_moisture_trend, temperature_anomaly_c,
             rolling_window_days
  landslide: rainfall_intensity_mm, soil_moisture_pct, elevation_gradient,
             terrain_slope
  cyclone:   wind_speed_kmh, wind_direction_deg, sea_surface_temp_c, cloud_density
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Default rolling window for drought calculations (days).
DEFAULT_ROLLING_WINDOW_DAYS = 30

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

DROUGHT_FIELDS = [
    "rainfall_deficit_mm",    # cumulative rainfall deficit (negative of rainfall_mm if below rolling avg, else 0)
    "soil_moisture_trend",    # difference between current and previous soil_moisture_pct
    "temperature_anomaly_c",  # difference between current temperature_c and rolling mean
    "rolling_window_days",    # configurable, default 30
]

LANDSLIDE_FIELDS = [
    "rainfall_intensity_mm",  # same as rainfall_mm but named for clarity
    "soil_moisture_pct",      # direct
    "elevation_gradient",     # from terrain data
    "terrain_slope",          # from terrain data
]

CYCLONE_FIELDS = [
    "wind_speed_kmh",       # direct
    "wind_direction_deg",   # direct
    "sea_surface_temp_c",   # optional — default 0.0 if not available
    "cloud_density",        # default 0.0 in Phase 2 (filled by CNN in Phase 3)
]

DISASTER_FIELDS: Dict[str, List[str]] = {
    "flood": FLOOD_FIELDS,
    "heatwave": HEATWAVE_FIELDS,
    "drought": DROUGHT_FIELDS,
    "landslide": LANDSLIDE_FIELDS,
    "cyclone": CYCLONE_FIELDS,
}


class FeatureRouter:
    """Routes and enriches sensor readings for a specific disaster type.

    Args:
        terrain_data: Optional dict mapping region_id →
                      {elevation, drainage_capacity, elevation_gradient, terrain_slope}.
        rolling_window_days: Window size for drought rolling calculations (default 30).
    """

    def __init__(
        self,
        terrain_data: Optional[Dict[str, Dict[str, Any]]] = None,
        rolling_window_days: int = DEFAULT_ROLLING_WINDOW_DAYS,
    ) -> None:
        self.terrain_data: Dict[str, Dict[str, Any]] = terrain_data or {}
        self.rolling_window_days = rolling_window_days

    def route(
        self,
        disaster_type: str,
        readings: List[Dict[str, Any]],
        region_id: str,
        historical_flags: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return a list of feature dicts filtered to the disaster type's fields.

        Args:
            disaster_type: One of flood/heatwave/drought/landslide/cyclone.
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

        # Pre-compute rolling stats for drought derivations.
        if disaster_type == "drought" and readings:
            rainfall_values = [
                float(r.get("rainfall_mm") or 0.0) for r in readings
            ]
            temp_values = [
                float(r.get("temperature_c") or 0.0) for r in readings
            ]
            rainfall_rolling_avg = sum(rainfall_values) / len(rainfall_values)
            temp_rolling_mean = sum(temp_values) / len(temp_values)
        else:
            rainfall_rolling_avg = 0.0
            temp_rolling_mean = 0.0

        routed: List[Dict[str, Any]] = []
        for idx, reading in enumerate(readings):
            enriched: Dict[str, Any] = {}
            for field in fields:
                # --- flood fields ---
                if field == "elevation":
                    enriched[field] = terrain.get("elevation", 0.0)
                elif field == "drainage_capacity":
                    enriched[field] = terrain.get("drainage_capacity", 0.0)
                # --- heatwave fields ---
                elif field == "humidity":
                    sm = reading.get("soil_moisture_pct")
                    enriched[field] = float(sm) if sm is not None else 0.0
                elif field == "historical_heatwave_flag":
                    enriched[field] = float(flags.get("historical_heatwave_flag", 0))
                # --- drought fields ---
                elif field == "rainfall_deficit_mm":
                    rainfall = float(reading.get("rainfall_mm") or 0.0)
                    deficit = -rainfall if rainfall < rainfall_rolling_avg else 0.0
                    enriched[field] = deficit
                elif field == "soil_moisture_trend":
                    if idx > 0:
                        prev_sm = float(readings[idx - 1].get("soil_moisture_pct") or 0.0)
                        curr_sm = float(reading.get("soil_moisture_pct") or 0.0)
                        enriched[field] = curr_sm - prev_sm
                    else:
                        enriched[field] = 0.0
                elif field == "temperature_anomaly_c":
                    temp = float(reading.get("temperature_c") or 0.0)
                    enriched[field] = temp - temp_rolling_mean
                elif field == "rolling_window_days":
                    enriched[field] = float(self.rolling_window_days)
                # --- landslide fields ---
                elif field == "rainfall_intensity_mm":
                    val = reading.get("rainfall_mm")
                    enriched[field] = float(val) if val is not None else 0.0
                elif field == "elevation_gradient":
                    enriched[field] = terrain.get("elevation_gradient", 0.0)
                elif field == "terrain_slope":
                    enriched[field] = terrain.get("terrain_slope", 0.0)
                # --- cyclone fields ---
                elif field == "sea_surface_temp_c":
                    val = reading.get("sea_surface_temp_c")
                    enriched[field] = float(val) if val is not None else 0.0
                elif field == "cloud_density":
                    # Phase 2: default 0.0; Phase 3 will fill from CNN features.
                    val = reading.get("cloud_density")
                    enriched[field] = float(val) if val is not None else 0.0
                else:
                    val = reading.get(field)
                    enriched[field] = float(val) if val is not None else 0.0
            routed.append(enriched)

        return routed

    def get_required_fields(self, disaster_type: str) -> List[str]:
        """Return the list of required feature fields for a disaster type."""
        return list(DISASTER_FIELDS.get(disaster_type, []))
