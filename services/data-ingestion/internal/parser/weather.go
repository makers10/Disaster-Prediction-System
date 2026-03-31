package parser

import (
	"encoding/json"
	"fmt"

	"github.com/disaster-prediction/data-ingestion/internal/weather"
)

// ParseWeatherForecast unmarshals JSON bytes into a WeatherForecast.
// Returns an error if the data is not valid JSON or cannot be decoded.
func ParseWeatherForecast(data []byte) (*weather.WeatherForecast, error) {
	var f weather.WeatherForecast
	if err := json.Unmarshal(data, &f); err != nil {
		return nil, fmt.Errorf("parse weather forecast: %w", err)
	}
	return &f, nil
}

// FormatWeatherForecast marshals a WeatherForecast to JSON bytes.
// Returns an error if the struct cannot be serialised.
func FormatWeatherForecast(f *weather.WeatherForecast) ([]byte, error) {
	data, err := json.Marshal(f)
	if err != nil {
		return nil, fmt.Errorf("format weather forecast: %w", err)
	}
	return data, nil
}
