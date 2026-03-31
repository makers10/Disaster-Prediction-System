// Package weather provides Weather API polling and forecast types.
package weather

// WeatherForecast represents a raw weather forecast fetched from an external Weather API.
type WeatherForecast struct {
	RegionID             string  `json:"region_id"`
	FetchedAt            string  `json:"fetched_at"`             // ISO 8601
	PrecipitationProbPct float64 `json:"precipitation_prob_pct"` // 0–100
	TemperatureForecastC float64 `json:"temperature_forecast_c"`
	WindForecastKmh      float64 `json:"wind_forecast_kmh"`
	ForecastHorizonH     int     `json:"forecast_horizon_h"`
	Source               string  `json:"source"`
}
