"""PredictionRecord dataclass matching the design doc schema."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional


DisasterType = Literal["flood", "heatwave", "drought", "landslide", "cyclone"]
RiskLevel = Literal["Low", "Medium", "High"]
ForecastHorizon = Literal[6, 24, 72]


@dataclass
class PredictionRecord:
    prediction_id: str
    region_id: str
    disaster_type: DisasterType
    forecast_horizon_h: ForecastHorizon
    risk_level: RiskLevel
    probability_pct: float          # 0–100
    time_to_impact_h: Optional[float]  # null if risk_level is Low
    severity_index: float           # 0–100
    generated_at: str               # ISO 8601
    model_version: str
    input_data_snapshot_id: str

    @staticmethod
    def create(
        region_id: str,
        disaster_type: DisasterType,
        forecast_horizon_h: ForecastHorizon,
        risk_level: RiskLevel,
        probability_pct: float,
        time_to_impact_h: Optional[float],
        severity_index: float,
        model_version: str,
        input_data_snapshot_id: str,
    ) -> "PredictionRecord":
        return PredictionRecord(
            prediction_id=str(uuid.uuid4()),
            region_id=region_id,
            disaster_type=disaster_type,
            forecast_horizon_h=forecast_horizon_h,
            risk_level=risk_level,
            probability_pct=max(0.0, min(100.0, probability_pct)),
            time_to_impact_h=time_to_impact_h,
            severity_index=max(0.0, min(100.0, severity_index)),
            generated_at=datetime.now(timezone.utc).isoformat(),
            model_version=model_version,
            input_data_snapshot_id=input_data_snapshot_id,
        )

    def to_dict(self) -> dict:
        return {
            "prediction_id": self.prediction_id,
            "region_id": self.region_id,
            "disaster_type": self.disaster_type,
            "forecast_horizon_h": self.forecast_horizon_h,
            "risk_level": self.risk_level,
            "probability_pct": self.probability_pct,
            "time_to_impact_h": self.time_to_impact_h,
            "severity_index": self.severity_index,
            "generated_at": self.generated_at,
            "model_version": self.model_version,
            "input_data_snapshot_id": self.input_data_snapshot_id,
        }

    @staticmethod
    def from_dict(data: dict) -> "PredictionRecord":
        return PredictionRecord(
            prediction_id=data["prediction_id"],
            region_id=data["region_id"],
            disaster_type=data["disaster_type"],
            forecast_horizon_h=data["forecast_horizon_h"],
            risk_level=data["risk_level"],
            probability_pct=data["probability_pct"],
            time_to_impact_h=data.get("time_to_impact_h"),
            severity_index=data["severity_index"],
            generated_at=data["generated_at"],
            model_version=data["model_version"],
            input_data_snapshot_id=data["input_data_snapshot_id"],
        )
