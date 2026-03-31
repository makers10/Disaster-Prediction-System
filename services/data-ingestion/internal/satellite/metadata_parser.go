package satellite

import (
	"encoding/json"
	"fmt"
)

// ParseMetadata parses a raw JSON satellite metadata payload into an ImageMetadata struct.
// Returns an error if the payload is invalid JSON or missing required fields.
func ParseMetadata(data []byte) (*ImageMetadata, error) {
	// First pass: check required fields exist and are non-null
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("satellite metadata: invalid JSON: %w", err)
	}

	required := []string{"image_id", "region_id", "provider", "captured_at", "received_at", "resolution_m"}
	for _, field := range required {
		val, ok := raw[field]
		if !ok || string(val) == "null" || string(val) == `""` {
			return nil, fmt.Errorf("satellite metadata: missing required field: %s", field)
		}
	}

	var meta ImageMetadata
	if err := json.Unmarshal(data, &meta); err != nil {
		return nil, fmt.Errorf("satellite metadata: decode error: %w", err)
	}

	if meta.ResolutionM <= 0 {
		return nil, fmt.Errorf("satellite metadata: resolution_m must be > 0, got %f", meta.ResolutionM)
	}

	return &meta, nil
}

// FormatMetadata serialises an ImageMetadata struct to JSON bytes.
func FormatMetadata(meta *ImageMetadata) ([]byte, error) {
	data, err := json.Marshal(meta)
	if err != nil {
		return nil, fmt.Errorf("satellite metadata: marshal error: %w", err)
	}
	return data, nil
}
