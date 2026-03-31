// Package parser provides pure parse/format functions for ingestion payloads.
package parser

import (
	"encoding/json"
	"fmt"

	"github.com/disaster-prediction/data-ingestion/internal/ingestion"
)

// ParseSensorReading unmarshals JSON bytes into a SensorReading.
// Returns an error if the data is not valid JSON or cannot be decoded.
func ParseSensorReading(data []byte) (*ingestion.SensorReading, error) {
	var r ingestion.SensorReading
	if err := json.Unmarshal(data, &r); err != nil {
		return nil, fmt.Errorf("parse sensor reading: %w", err)
	}
	return &r, nil
}

// FormatSensorReading marshals a SensorReading to JSON bytes.
// Returns an error if the struct cannot be serialised.
func FormatSensorReading(r *ingestion.SensorReading) ([]byte, error) {
	data, err := json.Marshal(r)
	if err != nil {
		return nil, fmt.Errorf("format sensor reading: %w", err)
	}
	return data, nil
}
