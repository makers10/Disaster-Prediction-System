// Package ingestion provides sensor feed polling and Kafka publishing.
package ingestion

import "time"

// SensorReading represents a raw reading from an IoT sensor feed.
type SensorReading struct {
	SensorID        string   `json:"sensor_id"`
	RegionID        string   `json:"region_id"`
	Timestamp       string   `json:"timestamp"` // ISO 8601
	RainfallMM      *float64 `json:"rainfall_mm"`
	TemperatureC    *float64 `json:"temperature_c"`
	RiverLevelM     *float64 `json:"river_level_m"`
	SoilMoisturePct *float64 `json:"soil_moisture_pct"`
	WindSpeedKmh    *float64 `json:"wind_speed_kmh"`
	WindDirectionDeg *float64 `json:"wind_direction_deg"`
	IsAnomalous     bool     `json:"is_anomalous"`
	StreamStatus    string   `json:"stream_status"` // "ok" | "degraded" | "unavailable"
}

// FeedState tracks the health of a single sensor feed.
type FeedState struct {
	SensorID     string
	LastReceived time.Time
	StreamStatus string
}
