"""XAIExplanation dataclass matching the design doc schema."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


@dataclass
class ContributingFactor:
    feature_name: str
    contribution_pct: float   # 0–100
    direction: str            # "positive" | "negative"


@dataclass
class XAIExplanation:
    explanation_id: str
    prediction_id: str
    generated_at: str
    contributing_factors: List[ContributingFactor]
    plain_language_summary: str

    @staticmethod
    def create(
        prediction_id: str,
        contributing_factors: List[ContributingFactor],
        plain_language_summary: str,
    ) -> "XAIExplanation":
        return XAIExplanation(
            explanation_id=str(uuid.uuid4()),
            prediction_id=prediction_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            contributing_factors=contributing_factors,
            plain_language_summary=plain_language_summary,
        )

    def to_dict(self) -> dict:
        return {
            "explanation_id": self.explanation_id,
            "prediction_id": self.prediction_id,
            "generated_at": self.generated_at,
            "contributing_factors": [
                {
                    "feature_name": f.feature_name,
                    "contribution_pct": f.contribution_pct,
                    "direction": f.direction,
                }
                for f in self.contributing_factors
            ],
            "plain_language_summary": self.plain_language_summary,
        }
