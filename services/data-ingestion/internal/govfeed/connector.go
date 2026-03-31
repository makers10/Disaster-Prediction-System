// Package govfeed implements the ExternalConnector interface for government
// and disaster management authority data feeds.
package govfeed

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/segmentio/kafka-go"
)

const govDataTopic = "raw.gov.data"

// GovDataRecord represents a record from a government disaster management feed.
type GovDataRecord struct {
	RecordID     string          `json:"record_id"`
	RegionID     string          `json:"region_id"`
	DataType     string          `json:"data_type"` // e.g. "disaster_alert", "weather_warning"
	Payload      json.RawMessage `json:"payload"`
	FetchedAt    string          `json:"fetched_at"` // ISO 8601
	Source       string          `json:"source"`
}

// ConnectorCredentials holds authentication details for a gov data feed.
type ConnectorCredentials struct {
	APIKey   string `json:"api_key"`
	Endpoint string `json:"endpoint"`
}

// GovFeedConnector polls a government data feed endpoint and publishes records to Kafka.
// Credentials can be hot-reloaded without restart via UpdateCredentials.
type GovFeedConnector struct {
	name         string
	endpoint     string
	apiKey       string
	mu           sync.RWMutex
	writer       *kafka.Writer
	httpClient   *http.Client
	pollInterval time.Duration
}

// NewGovFeedConnectorFromEnv creates a connector from environment variables.
// GOV_FEED_NAME, GOV_FEED_ENDPOINT, GOV_FEED_API_KEY, GOV_FEED_POLL_INTERVAL_SECONDS
func NewGovFeedConnectorFromEnv(kafkaBrokers string) (*GovFeedConnector, error) {
	endpoint := os.Getenv("GOV_FEED_ENDPOINT")
	if endpoint == "" {
		return nil, fmt.Errorf("GOV_FEED_ENDPOINT is required")
	}

	name := os.Getenv("GOV_FEED_NAME")
	if name == "" {
		name = "gov-feed"
	}

	apiKey := os.Getenv("GOV_FEED_API_KEY")

	intervalSec := 3600
	if v := os.Getenv("GOV_FEED_POLL_INTERVAL_SECONDS"); v != "" {
		fmt.Sscanf(v, "%d", &intervalSec)
	}

	brokers := strings.Split(kafkaBrokers, ",")

	return &GovFeedConnector{
		name:     name,
		endpoint: endpoint,
		apiKey:   apiKey,
		writer: &kafka.Writer{
			Addr:     kafka.TCP(brokers...),
			Topic:    govDataTopic,
			Balancer: &kafka.LeastBytes{},
		},
		httpClient:   &http.Client{Timeout: 30 * time.Second},
		pollInterval: time.Duration(intervalSec) * time.Second,
	}, nil
}

// UpdateCredentials hot-reloads the API key and endpoint without restarting.
func (c *GovFeedConnector) UpdateCredentials(creds ConnectorCredentials) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.apiKey = creds.APIKey
	c.endpoint = creds.Endpoint
	slog.Info("gov feed connector credentials updated", "name", c.name)
}

// Run starts the polling loop; blocks until ctx is cancelled.
func (c *GovFeedConnector) Run(ctx context.Context) {
	slog.Info("gov feed connector started", "name", c.name, "interval", c.pollInterval)

	ticker := time.NewTicker(c.pollInterval)
	defer ticker.Stop()

	c.poll(ctx)

	for {
		select {
		case <-ctx.Done():
			_ = c.writer.Close()
			slog.Info("gov feed connector stopped", "name", c.name)
			return
		case <-ticker.C:
			c.poll(ctx)
		}
	}
}

func (c *GovFeedConnector) poll(ctx context.Context) {
	c.mu.RLock()
	endpoint := c.endpoint
	apiKey := c.apiKey
	c.mu.RUnlock()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		slog.Error("gov feed: failed to create request", "name", c.name, "error", err)
		return
	}
	if apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		slog.Error("gov feed: HTTP request failed", "name", c.name, "error", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		slog.Error("gov feed: unexpected status", "name", c.name, "status", resp.StatusCode)
		return
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		slog.Error("gov feed: failed to read body", "name", c.name, "error", err)
		return
	}

	// Try to parse as array of records, fall back to single record
	var records []GovDataRecord
	if err := json.Unmarshal(body, &records); err != nil {
		// Try single record
		var single GovDataRecord
		if err2 := json.Unmarshal(body, &single); err2 != nil {
			slog.Error("gov feed: failed to parse response", "name", c.name, "error", err)
			return
		}
		records = []GovDataRecord{single}
	}

	now := time.Now().UTC().Format(time.RFC3339)
	published := 0
	for i := range records {
		if records[i].FetchedAt == "" {
			records[i].FetchedAt = now
		}
		if records[i].Source == "" {
			records[i].Source = c.name
		}

		data, _ := json.Marshal(records[i])
		if err := c.writer.WriteMessages(ctx, kafka.Message{
			Key:   []byte(records[i].RecordID),
			Value: data,
		}); err != nil {
			slog.Error("gov feed: publish failed", "name", c.name, "error", err)
			continue
		}
		published++
	}

	slog.Info("gov feed: published records", "name", c.name, "count", published)
}
