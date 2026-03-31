CREATE TABLE IF NOT EXISTS historical_disaster_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  region_id TEXT NOT NULL,
  disaster_type TEXT NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  severity FLOAT NOT NULL CHECK (severity >= 0 AND severity <= 100),
  source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_historical_events_region ON historical_disaster_events(region_id);
CREATE INDEX IF NOT EXISTS idx_historical_events_type ON historical_disaster_events(disaster_type);
