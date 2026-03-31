// Package satellite provides satellite feed ingestion and unavailability tracking.
package satellite

import "time"

// ImageMetadata represents metadata for a received satellite image.
type ImageMetadata struct {
	ImageID    string `json:"image_id"`
	RegionID   string `json:"region_id"`
	Provider   string `json:"provider"`
	CapturedAt string `json:"captured_at"` // ISO 8601
	ReceivedAt string `json:"received_at"` // ISO 8601
	ResolutionM float64 `json:"resolution_m"`
	FeedStatus string `json:"feed_status"` // "ok" | "unavailable"
}

// UnavailabilityEvent is published when a satellite feed has been silent > 2 hours.
type UnavailabilityEvent struct {
	Provider        string    `json:"provider"`
	UnavailableSince time.Time `json:"unavailable_since"`
}

// ConnectorCredentials holds authentication details for a satellite feed provider.
type ConnectorCredentials struct {
	APIKey   string `json:"api_key"`
	Endpoint string `json:"endpoint"`
}
