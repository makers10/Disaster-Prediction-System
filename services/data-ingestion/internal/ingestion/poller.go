package ingestion

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/segmentio/kafka-go"
)

const (
	defaultPollIntervalSeconds = 900 // 15 minutes
	degradedThreshold          = 30 * time.Minute
	unavailableThreshold       = 60 * time.Minute
	rawSensorTopic             = "raw.sensor.reading"
)

// Poller polls HTTP sensor feed endpoints and publishes readings to Kafka.
type Poller struct {
	feedURLs     []string
	pollInterval time.Duration
	writer       *kafka.Writer
	feedStates   map[string]*FeedState
	mu           sync.Mutex
}

// NewPoller creates a new Poller from environment configuration.
func NewPoller(kafkaBrokers string) (*Poller, error) {
	intervalSec := defaultPollIntervalSeconds
	if v := os.Getenv("SENSOR_POLL_INTERVAL_SECONDS"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("invalid SENSOR_POLL_INTERVAL_SECONDS: %w", err)
		}
		intervalSec = n
	}

	rawURLs := os.Getenv("SENSOR_FEED_URLS")
	var feedURLs []string
	for _, u := range strings.Split(rawURLs, ",") {
		u = strings.TrimSpace(u)
		if u != "" {
			feedURLs = append(feedURLs, u)
		}
	}

	writer := &kafka.Writer{
		Addr:     kafka.TCP(strings.Split(kafkaBrokers, ",")...),
		Topic:    rawSensorTopic,
		Balancer: &kafka.LeastBytes{},
	}

	return &Poller{
		feedURLs:     feedURLs,
		pollInterval: time.Duration(intervalSec) * time.Second,
		writer:       writer,
		feedStates:   make(map[string]*FeedState),
	}, nil
}

// Run starts the polling loop; blocks until ctx is cancelled.
func (p *Poller) Run(ctx context.Context) {
	slog.Info("sensor poller started",
		"feed_count", len(p.feedURLs),
		"poll_interval", p.pollInterval,
	)

	ticker := time.NewTicker(p.pollInterval)
	defer ticker.Stop()

	// Poll immediately on startup, then on each tick.
	p.pollAll(ctx)

	for {
		select {
		case <-ctx.Done():
			slog.Info("sensor poller stopping")
			_ = p.writer.Close()
			return
		case <-ticker.C:
			p.pollAll(ctx)
		}
	}
}

// pollAll fetches all configured sensor feeds and publishes readings.
func (p *Poller) pollAll(ctx context.Context) {
	for _, url := range p.feedURLs {
		reading, err := p.fetchReading(ctx, url)
		if err != nil {
			slog.Error("failed to fetch sensor feed", "url", url, "error", err)
			p.updateFeedState(url, "")
			continue
		}

		reading.StreamStatus = p.updateFeedState(reading.SensorID, reading.SensorID)

		if err := p.publish(ctx, reading); err != nil {
			slog.Error("failed to publish sensor reading", "sensor_id", reading.SensorID, "error", err)
		} else {
			slog.Info("published sensor reading",
				"sensor_id", reading.SensorID,
				"stream_status", reading.StreamStatus,
			)
		}
	}
}

// fetchReading performs an HTTP GET to the feed URL and decodes the JSON response.
func (p *Poller) fetchReading(ctx context.Context, url string) (*SensorReading, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http get: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status %d from %s", resp.StatusCode, url)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	var reading SensorReading
	if err := json.Unmarshal(body, &reading); err != nil {
		return nil, fmt.Errorf("decode json: %w", err)
	}

	if reading.Timestamp == "" {
		reading.Timestamp = time.Now().UTC().Format(time.RFC3339)
	}

	return &reading, nil
}

// updateFeedState updates the last-received time for a sensor and returns the
// appropriate stream_status based on elapsed time since last receipt.
// sensorID is the logical sensor identifier; feedKey is used as the map key
// (falls back to the feed URL when sensorID is unknown).
func (p *Poller) updateFeedState(feedKey, sensorID string) string {
	p.mu.Lock()
	defer p.mu.Unlock()

	now := time.Now()
	state, exists := p.feedStates[feedKey]
	if !exists {
		state = &FeedState{SensorID: sensorID, LastReceived: now, StreamStatus: "ok"}
		p.feedStates[feedKey] = state
		return "ok"
	}

	if sensorID != "" {
		// Successful receipt — reset timer.
		state.LastReceived = now
		state.StreamStatus = "ok"
		return "ok"
	}

	// No successful receipt — check gap.
	gap := now.Sub(state.LastReceived)
	switch {
	case gap >= unavailableThreshold:
		if state.StreamStatus != "unavailable" {
			slog.Warn("sensor feed unavailable", "feed_key", feedKey, "gap", gap)
		}
		state.StreamStatus = "unavailable"
	case gap >= degradedThreshold:
		if state.StreamStatus == "ok" {
			slog.Warn("sensor feed degraded", "feed_key", feedKey, "gap", gap)
		}
		state.StreamStatus = "degraded"
	}
	return state.StreamStatus
}

// publish serialises a SensorReading and writes it to the Kafka topic.
func (p *Poller) publish(ctx context.Context, reading *SensorReading) error {
	data, err := json.Marshal(reading)
	if err != nil {
		return fmt.Errorf("marshal reading: %w", err)
	}

	return p.writer.WriteMessages(ctx, kafka.Message{
		Key:   []byte(reading.SensorID),
		Value: data,
	})
}

// FeedStates returns a snapshot of all tracked feed states (used by tests).
func (p *Poller) FeedStates() map[string]*FeedState {
	p.mu.Lock()
	defer p.mu.Unlock()
	snapshot := make(map[string]*FeedState, len(p.feedStates))
	for k, v := range p.feedStates {
		cp := *v
		snapshot[k] = &cp
	}
	return snapshot
}
