CREATE TABLE IF NOT EXISTS actual_outcomes (
  outcome_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prediction_id UUID NOT NULL,
  region_id TEXT NOT NULL,
  disaster_type TEXT NOT NULL,
  actual_occurred BOOLEAN NOT NULL,
  actual_severity FLOAT,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_actual_outcomes_prediction_id ON actual_outcomes(prediction_id);
CREATE INDEX IF NOT EXISTS idx_actual_outcomes_region_disaster ON actual_outcomes(region_id, disaster_type);
