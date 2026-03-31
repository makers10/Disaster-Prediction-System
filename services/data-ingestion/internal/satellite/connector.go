package satellite

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

const (
	unavailabilityThreshold = 2 * time.Hour
	rawSatelliteTopic       = "raw.satellite.image"
	unavailabilityTopic     = "satellite.feed.unavailable"
)

// Connector polls a satellite feed HTTP endpoint and publishes image metadata to Kafka.
// It tracks last-received time and publishes an unavailability event if the gap exceeds 2 hours.
// Credentials can be hot-reloaded without restart via UpdateCredentials.
type Connector struct {
	provider     string
	endpoint     string
	apiKey       string
	mu           sync.RWMutex
	lastReceived time.Time
	writer       *kafka.Writer
	unavailWriter *kafka.Writer
	httpClient   *http.Client
}

// NewConnectorFromEnv creates a Connector from environment variables.
// SATELLITE_FEED_PROVIDER, SATELLITE_FEED_ENDPOINT, SATELLITE_FEED_API_KEY
func NewConnectorFromEnv(kafkaBrokers string) (*Connector, error) {
	provider := os.Getenv("SATELLITE_FEED_PROVIDER")
	endpoint := os.Getenv("SATELLITE_FEED_ENDPOINT")
	apiKey := os.Getenv("SATELLITE_FEED_API_KEY")

	if endpoint == "" {
		return nil, fmt.Errorf("SATELLITE_FEED_ENDPOINT is required")
	}
	if provider == "" {
		provider = "default"
	}

	brokers := strings.Split(kafkaBrokers, ",")

	return &Connector{
		provider: provider,
		endpoint: endpoint,
		apiKey:   apiKey,
		writer: &kafka.Writer{
			Addr:     kafka.TCP(brokers...),
			Topic:    rawSatelliteTopic,
			Balancer: &kafka.LeastBytes{},
		},
		unavailWriter: &kafka.Writer{
			Addr:     kafka.TCP(brokers...),
			Topic:    unavailabilityTopic,
			Balancer: &kafka.LeastBytes{},
		},
		httpClient: &http.Client{Timeout: 30 * time.Second},
	}, nil
}

// UpdateCredentials hot-reloads the API key and endpoint without restarting.
func (c *Connector) UpdateCredentials(creds ConnectorCredentials) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.apiKey = creds.APIKey
	c.endpoint = creds.Endpoint
	slog.Info("satellite connector credentials updated", "provider", c.provider)
}

// Run starts the polling loop; blocks until ctx is cancelled.
// Polls every SATELLITE_POLL_INTERVAL_SECONDS (default 300 = 5 minutes).
func (c *Connector) Run(ctx context.Context) {
	intervalSec := 300
	if v := os.Getenv("SATELLITE_POLL_INTERVAL_SECONDS"); v != "" {
		fmt.Sscanf(v, "%d", &intervalSec)
	}
	interval := time.Duration(intervalSec) * time.Second

	slog.Info("satellite connector started", "provider", c.provider, "interval", interval)

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	// Check unavailability every minute regardless of poll interval.
	unavailTicker := time.NewTicker(time.Minute)
	defer unavailTicker.Stop()

	c.poll(ctx)

	for {
		select {
		case <-ctx.Done():
			_ = c.writer.Close()
			_ = c.unavailWriter.Close()
			slog.Info("satellite connector stopped")
			return
		case <-ticker.C:
			c.poll(ctx)
		case <-unavailTicker.C:
			c.checkUnavailability(ctx)
		}
	}
}

func (c *Connector) poll(ctx context.Context) {
	c.mu.RLock()
	endpoint := c.endpoint
	apiKey := c.apiKey
	c.mu.RUnlock()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		slog.Error("satellite: failed to create request", "error", err)
		return
	}
	if apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		slog.Error("satellite: HTTP request failed", "provider", c.provider, "error", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		slog.Error("satellite: unexpected status", "provider", c.provider, "status", resp.StatusCode)
		return
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		slog.Error("satellite: failed to read response body", "error", err)
		return
	}

	var meta ImageMetadata
	if err := json.Unmarshal(body, &meta); err != nil {
		slog.Error("satellite: failed to decode metadata", "error", err)
		return
	}

	now := time.Now().UTC()
	if meta.ReceivedAt == "" {
		meta.ReceivedAt = now.Format(time.RFC3339)
	}
	meta.Provider = c.provider
	meta.FeedStatus = "ok"

	c.mu.Lock()
	c.lastReceived = now
	c.mu.Unlock()

	data, _ := json.Marshal(meta)
	if err := c.writer.WriteMessages(ctx, kafka.Message{
		Key:   []byte(meta.RegionID),
		Value: data,
	}); err != nil {
		slog.Error("satellite: failed to publish metadata", "error", err)
		return
	}
	slog.Info("satellite: published image metadata", "image_id", meta.ImageID, "region_id", meta.RegionID)
}

func (c *Connector) checkUnavailability(ctx context.Context) {
	c.mu.RLock()
	last := c.lastReceived
	c.mu.RUnlock()

	if last.IsZero() {
		return
	}

	gap := time.Since(last)
	if gap >= unavailabilityThreshold {
		event := UnavailabilityEvent{
			Provider:        c.provider,
			UnavailableSince: last,
		}
		data, _ := json.Marshal(event)
		if err := c.unavailWriter.WriteMessages(ctx, kafka.Message{
			Key:   []byte(c.provider),
			Value: data,
		}); err != nil {
			slog.Error("satellite: failed to publish unavailability event", "error", err)
			return
		}
		slog.Warn("satellite feed unavailable", "provider", c.provider, "gap", gap)
	}
}
