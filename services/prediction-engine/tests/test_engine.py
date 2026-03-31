"""Unit tests for prediction engine components."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

from engine.ssm import SSMModel
from engine.transformer import TransformerModel
from engine.ensemble import EnsembleAggregator
from engine.feature_router import FeatureRouter
from models.prediction import PredictionRecord


# ---------------------------------------------------------------------------
# SSMModel tests
# ---------------------------------------------------------------------------

class TestSSMModel:
    def test_empty_readings_returns_zero_vector(self):
        model = SSMModel()
        result = model.extract_features([])
        assert result.shape == (16,)
        assert np.allclose(result, 0.0)

    def test_single_reading_returns_unit_vector(self):
        model = SSMModel()
        reading = {"rainfall_mm": 10.0, "temperature_c": 25.0}
        result = model.extract_features([reading])
        assert result.shape == (16,)
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-5

    def test_multiple_readings_returns_correct_shape(self):
        model = SSMModel()
        readings = [{"rainfall_mm": float(i), "temperature_c": 20.0} for i in range(10)]
        result = model.extract_features(readings)
        assert result.shape == (16,)

    def test_none_values_treated_as_zero(self):
        model = SSMModel()
        reading = {"rainfall_mm": None, "temperature_c": None}
        result = model.extract_features([reading])
        assert result.shape == (16,)

    def test_invalid_alpha_raises(self):
        with pytest.raises(ValueError):
            SSMModel(alpha=0.0)
        with pytest.raises(ValueError):
            SSMModel(alpha=1.5)

    def test_deterministic_output(self):
        model = SSMModel()
        readings = [{"rainfall_mm": 5.0, "temperature_c": 30.0}]
        r1 = model.extract_features(readings)
        r2 = model.extract_features(readings)
        assert np.allclose(r1, r2)


# ---------------------------------------------------------------------------
# TransformerModel tests
# ---------------------------------------------------------------------------

class TestTransformerModel:
    def test_empty_input_returns_empty(self):
        model = TransformerModel()
        result = model.compute_context({})
        assert result == {}

    def test_single_region_returns_context(self):
        model = TransformerModel()
        vec = np.ones(16, dtype=np.float32)
        result = model.compute_context({"region_A": vec})
        assert "region_A" in result
        assert result["region_A"].shape == (16,)

    def test_multiple_regions_all_get_context(self):
        model = TransformerModel()
        features = {
            "r1": np.random.rand(16).astype(np.float32),
            "r2": np.random.rand(16).astype(np.float32),
            "r3": np.random.rand(16).astype(np.float32),
        }
        result = model.compute_context(features)
        assert set(result.keys()) == {"r1", "r2", "r3"}

    def test_invalid_temperature_raises(self):
        with pytest.raises(ValueError):
            TransformerModel(temperature=0.0)


# ---------------------------------------------------------------------------
# EnsembleAggregator tests
# ---------------------------------------------------------------------------

class TestEnsembleAggregator:
    def _make_vectors(self):
        rng = np.random.default_rng(0)
        return rng.standard_normal(16).astype(np.float32), rng.standard_normal(16).astype(np.float32)

    def test_risk_level_is_valid(self):
        agg = EnsembleAggregator()
        ssm, tf = self._make_vectors()
        for dtype in ["flood", "heatwave"]:
            for horizon in [6, 24, 72]:
                risk, prob, tti, sev = agg.predict(dtype, ssm, tf, horizon)
                assert risk in ("Low", "Medium", "High")

    def test_probability_in_range(self):
        agg = EnsembleAggregator()
        ssm, tf = self._make_vectors()
        _, prob, _, _ = agg.predict("flood", ssm, tf, 24)
        assert 0.0 <= prob <= 100.0

    def test_severity_in_range(self):
        agg = EnsembleAggregator()
        ssm, tf = self._make_vectors()
        _, _, _, sev = agg.predict("flood", ssm, tf, 24)
        assert 0.0 <= sev <= 100.0

    def test_time_to_impact_null_for_low_risk(self):
        """Force a Low risk scenario by using a zero vector."""
        agg = EnsembleAggregator()
        zero = np.zeros(16, dtype=np.float32)
        risk, _, tti, _ = agg.predict("flood", zero, zero, 6)
        if risk == "Low":
            assert tti is None

    def test_time_to_impact_not_null_for_medium_high(self):
        agg = EnsembleAggregator()
        ssm, tf = self._make_vectors()
        risk, _, tti, _ = agg.predict("flood", ssm, tf, 6)
        if risk in ("Medium", "High"):
            assert tti is not None

    def test_invalid_weights_raise(self):
        with pytest.raises(ValueError):
            EnsembleAggregator(weights={"flood": (0.3, 0.3)})

    def test_all_horizons_produce_results(self):
        agg = EnsembleAggregator()
        ssm, tf = self._make_vectors()
        for h in [6, 24, 72]:
            result = agg.predict("heatwave", ssm, tf, h)
            assert len(result) == 4


# ---------------------------------------------------------------------------
# FeatureRouter tests
# ---------------------------------------------------------------------------

class TestFeatureRouter:
    def _make_readings(self):
        return [
            {
                "rainfall_mm": 12.0,
                "temperature_c": 35.0,
                "river_level_m": 2.5,
                "soil_moisture_pct": 70.0,
                "wind_speed_kmh": 15.0,
                "wind_direction_deg": 180.0,
            }
        ]

    def test_flood_fields_present(self):
        router = FeatureRouter(terrain_data={"r1": {"elevation": 50.0, "drainage_capacity": 100.0}})
        routed = router.route("flood", self._make_readings(), "r1")
        assert len(routed) == 1
        row = routed[0]
        assert "rainfall_mm" in row
        assert "river_level_m" in row
        assert "soil_moisture_pct" in row
        assert "elevation" in row
        assert "drainage_capacity" in row

    def test_heatwave_fields_present(self):
        router = FeatureRouter()
        routed = router.route("heatwave", self._make_readings(), "r1")
        assert len(routed) == 1
        row = routed[0]
        assert "temperature_c" in row
        assert "wind_speed_kmh" in row
        assert "humidity" in row
        assert "historical_heatwave_flag" in row

    def test_humidity_derived_from_soil_moisture(self):
        router = FeatureRouter()
        readings = [{"soil_moisture_pct": 60.0}]
        routed = router.route("heatwave", readings, "r1")
        assert routed[0]["humidity"] == 60.0

    def test_missing_terrain_defaults_to_zero(self):
        router = FeatureRouter()
        routed = router.route("flood", self._make_readings(), "unknown_region")
        assert routed[0]["elevation"] == 0.0
        assert routed[0]["drainage_capacity"] == 0.0

    def test_get_required_fields_flood(self):
        router = FeatureRouter()
        fields = router.get_required_fields("flood")
        assert "rainfall_mm" in fields
        assert "elevation" in fields

    def test_get_required_fields_unknown_returns_empty(self):
        router = FeatureRouter()
        assert router.get_required_fields("unknown") == []

    def test_drought_fields_present(self):
        router = FeatureRouter()
        readings = [
            {"rainfall_mm": 5.0, "soil_moisture_pct": 40.0, "temperature_c": 32.0},
            {"rainfall_mm": 3.0, "soil_moisture_pct": 35.0, "temperature_c": 34.0},
        ]
        routed = router.route("drought", readings, "r1")
        assert len(routed) == 2
        for row in routed:
            assert "rainfall_deficit_mm" in row
            assert "soil_moisture_trend" in row
            assert "temperature_anomaly_c" in row
            assert "rolling_window_days" in row

    def test_drought_rolling_window_days_default(self):
        router = FeatureRouter()
        readings = [{"rainfall_mm": 10.0, "soil_moisture_pct": 50.0, "temperature_c": 25.0}]
        routed = router.route("drought", readings, "r1")
        assert routed[0]["rolling_window_days"] == 30.0

    def test_drought_rolling_window_days_configurable(self):
        router = FeatureRouter(rolling_window_days=14)
        readings = [{"rainfall_mm": 10.0, "soil_moisture_pct": 50.0, "temperature_c": 25.0}]
        routed = router.route("drought", readings, "r1")
        assert routed[0]["rolling_window_days"] == 14.0

    def test_drought_rainfall_deficit_below_average(self):
        # rainfall_mm=2 is below rolling avg of 10 → deficit = -2
        router = FeatureRouter()
        readings = [{"rainfall_mm": 10.0}, {"rainfall_mm": 10.0}, {"rainfall_mm": 2.0}]
        routed = router.route("drought", readings, "r1")
        # rolling avg ≈ 7.33; last reading (2.0) is below avg → deficit = -2.0
        assert routed[2]["rainfall_deficit_mm"] < 0.0

    def test_drought_rainfall_deficit_above_average(self):
        # rainfall_mm=20 is above rolling avg → deficit = 0
        router = FeatureRouter()
        readings = [{"rainfall_mm": 5.0}, {"rainfall_mm": 5.0}, {"rainfall_mm": 20.0}]
        routed = router.route("drought", readings, "r1")
        assert routed[2]["rainfall_deficit_mm"] == 0.0

    def test_drought_soil_moisture_trend(self):
        router = FeatureRouter()
        readings = [
            {"rainfall_mm": 5.0, "soil_moisture_pct": 40.0, "temperature_c": 25.0},
            {"rainfall_mm": 5.0, "soil_moisture_pct": 35.0, "temperature_c": 25.0},
        ]
        routed = router.route("drought", readings, "r1")
        assert routed[0]["soil_moisture_trend"] == 0.0   # first reading: no previous
        assert routed[1]["soil_moisture_trend"] == -5.0  # 35 - 40

    def test_drought_temperature_anomaly(self):
        router = FeatureRouter()
        readings = [
            {"rainfall_mm": 5.0, "soil_moisture_pct": 50.0, "temperature_c": 20.0},
            {"rainfall_mm": 5.0, "soil_moisture_pct": 50.0, "temperature_c": 30.0},
        ]
        routed = router.route("drought", readings, "r1")
        # rolling mean = 25; anomalies = -5 and +5
        assert routed[0]["temperature_anomaly_c"] == pytest.approx(-5.0)
        assert routed[1]["temperature_anomaly_c"] == pytest.approx(5.0)

    def test_landslide_fields_present(self):
        router = FeatureRouter(
            terrain_data={"r1": {"elevation_gradient": 0.3, "terrain_slope": 25.0}}
        )
        routed = router.route("landslide", self._make_readings(), "r1")
        assert len(routed) == 1
        row = routed[0]
        assert "rainfall_intensity_mm" in row
        assert "soil_moisture_pct" in row
        assert "elevation_gradient" in row
        assert "terrain_slope" in row

    def test_landslide_rainfall_intensity_equals_rainfall_mm(self):
        router = FeatureRouter()
        readings = [{"rainfall_mm": 18.5, "soil_moisture_pct": 60.0}]
        routed = router.route("landslide", readings, "r1")
        assert routed[0]["rainfall_intensity_mm"] == 18.5

    def test_landslide_terrain_defaults_to_zero(self):
        router = FeatureRouter()
        routed = router.route("landslide", self._make_readings(), "unknown_region")
        assert routed[0]["elevation_gradient"] == 0.0
        assert routed[0]["terrain_slope"] == 0.0

    def test_cyclone_fields_present(self):
        router = FeatureRouter()
        routed = router.route("cyclone", self._make_readings(), "r1")
        assert len(routed) == 1
        row = routed[0]
        assert "wind_speed_kmh" in row
        assert "wind_direction_deg" in row
        assert "sea_surface_temp_c" in row
        assert "cloud_density" in row

    def test_cyclone_sea_surface_temp_defaults_to_zero(self):
        router = FeatureRouter()
        readings = [{"wind_speed_kmh": 120.0, "wind_direction_deg": 90.0}]
        routed = router.route("cyclone", readings, "r1")
        assert routed[0]["sea_surface_temp_c"] == 0.0

    def test_cyclone_cloud_density_defaults_to_zero(self):
        router = FeatureRouter()
        readings = [{"wind_speed_kmh": 120.0, "wind_direction_deg": 90.0}]
        routed = router.route("cyclone", readings, "r1")
        assert routed[0]["cloud_density"] == 0.0

    def test_all_five_disaster_types_have_fields(self):
        from engine.feature_router import DISASTER_FIELDS
        for dtype in ["flood", "heatwave", "drought", "landslide", "cyclone"]:
            assert dtype in DISASTER_FIELDS
            assert len(DISASTER_FIELDS[dtype]) > 0


# ---------------------------------------------------------------------------
# PredictionRecord tests
# ---------------------------------------------------------------------------

class TestPredictionRecord:
    def test_create_sets_uuid(self):
        r = PredictionRecord.create(
            region_id="r1", disaster_type="flood", forecast_horizon_h=6,
            risk_level="High", probability_pct=80.0, time_to_impact_h=3.0,
            severity_index=75.0, model_version="1.0", input_data_snapshot_id="snap1",
        )
        assert len(r.prediction_id) == 36  # UUID format

    def test_probability_clamped(self):
        r = PredictionRecord.create(
            region_id="r1", disaster_type="flood", forecast_horizon_h=6,
            risk_level="High", probability_pct=150.0, time_to_impact_h=1.0,
            severity_index=50.0, model_version="1.0", input_data_snapshot_id="snap1",
        )
        assert r.probability_pct == 100.0

    def test_severity_clamped(self):
        r = PredictionRecord.create(
            region_id="r1", disaster_type="flood", forecast_horizon_h=6,
            risk_level="Low", probability_pct=10.0, time_to_impact_h=None,
            severity_index=-5.0, model_version="1.0", input_data_snapshot_id="snap1",
        )
        assert r.severity_index == 0.0

    def test_round_trip_dict(self):
        r = PredictionRecord.create(
            region_id="r2", disaster_type="heatwave", forecast_horizon_h=24,
            risk_level="Medium", probability_pct=55.0, time_to_impact_h=12.0,
            severity_index=45.0, model_version="1.0", input_data_snapshot_id="snap2",
        )
        d = r.to_dict()
        r2 = PredictionRecord.from_dict(d)
        assert r.prediction_id == r2.prediction_id
        assert r.region_id == r2.region_id
        assert r.disaster_type == r2.disaster_type
        assert r.forecast_horizon_h == r2.forecast_horizon_h
        assert r.risk_level == r2.risk_level
        assert r.probability_pct == r2.probability_pct
        assert r.time_to_impact_h == r2.time_to_impact_h
        assert r.severity_index == r2.severity_index
        assert r.generated_at == r2.generated_at
        assert r.model_version == r2.model_version
        assert r.input_data_snapshot_id == r2.input_data_snapshot_id
