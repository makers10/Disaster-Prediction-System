package weather

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
	"time"

	"github.com/segmentio/kafka-go"
)

const (
	defaultWeatherPollIntervalSeconds = 3600 // 1 hour
	rawWeatherTopic                   = "raw.weather.forecast"
	maxRetries                        = 3
)

// retryDelays defines the exponential backoff delays for each retry attempt.
var retryDelays = [maxRetries]time.Duration{1 * time.Second, 2 * time.Second, 4 * time.Second}

// WeatherPoller polls configured Weather API URLs and publishes forecasts to Kafka.
type WeatherPoller struct {
	feedURLs     []string
	pollInterval time.Duration
	writer       *kafka.Writer
	httpClient   *http.Client
}

// NewWeatherPoller creates a new WeatherPoller from environment configuration.
func NewWeatherPoller(kafkaBrokers string) (*WeatherPoller, error) {
	intervalSec := defaultWeatherPollIntervalSeconds
	if v := os.Getenv("WEATHER_POLL_INTERVAL_SECONDS"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("invalid WEATHER_POLL_INTERVAL_SECONDS: %w", err)
		}
		intervalSec = n
	}

	rawURLs := os.Getenv("WEATHER_API_URLS")
	var feedURLs []string
	for _, u := range strings.Split(rawURLs, ",") {
		u = strings.TrimSpace(u)
		if u != "" {
			feedURLs = append(feedURLs, u)
		}
	}

	writer := &kafka.Writer{
		Addr:     kafka.TCP(strings.Split(kafkaBrokers, ",")...),
		Topic:    rawWeatherTopic,
		Balancer: &kafka.LeastBytes{},
	}

	return &WeatherPoller{
		feedURLs:     feedURLs,
		pollInterval: time.Duration(intervalSec) * time.Second,
		writer:       writer,
		httpClient:   &http.Client{Timeout: 30 * time.Second},
	}, nil
}

// Run starts the polling loop; blocks until ctx is cancelled.
func (p *WeatherPoller) Run(ctx context.Context) {
	slog.Info("weather poller started",
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
			slog.Info("weather poller stopping")
			_ = p.writer.Close()
			return
		case <-ticker.C:
			p.pollAll(ctx)
		}
	}
}

// pollAll fetches all configured weather feed URLs and publishes forecasts.
func (p *WeatherPoller) pollAll(ctx context.Context) {
	for _, url := range p.feedURLs {
		forecast, err := p.fetchWithRetry(ctx, url)
		if err != nil {
			slog.Error("weather feed unavailable after retries — skipping until next poll cycle",
				"url", url, "error", err)
			continue
		}

		if err := p.publish(ctx, forecast); err != nil {
			slog.Error("failed to publish weather forecast", "url", url, "error", err)
		} else {
			slog.Info("published weather forecast",
				"region_id", forecast.RegionID,
				"source", forecast.Source,
			)
		}
	}
}

// fetchWithRetry attempts to fetch a weather forecast from url, retrying up to
// maxRetries times with exponential backoff on HTTP error responses.
func (p *WeatherPoller) fetchWithRetry(ctx context.Context, url string) (*WeatherForecast, error) {
	var lastErr error
	for attempt := 0; attempt < maxRetries; attempt++ {
		if attempt > 0 {
			delay := retryDelays[attempt-1]
			slog.Warn("retrying weather API request",
				"url", url,
				"attempt", attempt+1,
				"backoff", delay,
			)
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(delay):
			}
		}

		forecast, err := p.fetchForecast(ctx, url)
		if err == nil {
			return forecast, nil
		}
		lastErr = err
		slog.Warn("weather API request failed", "url", url, "attempt", attempt+1, "error", err)
	}
	return nil, fmt.Errorf("all %d attempts failed for %s: %w", maxRetries, url, lastErr)
}

// fetchForecast performs a single HTTP GET and decodes the JSON response.
func (p *WeatherPoller) fetchForecast(ctx context.Context, url string) (*WeatherForecast, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	resp, err := p.httpClient.Do(req)
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

	var forecast WeatherForecast
	if err := json.Unmarshal(body, &forecast); err != nil {
		return nil, fmt.Errorf("decode json: %w", err)
	}

	if forecast.FetchedAt == "" {
		forecast.FetchedAt = time.Now().UTC().Format(time.RFC3339)
	}

	return &forecast, nil
}

// publish serialises a WeatherForecast and writes it to the Kafka topic.
func (p *WeatherPoller) publish(ctx context.Context, forecast *WeatherForecast) error {
	data, err := json.Marshal(forecast)
	if err != nil {
		return fmt.Errorf("marshal forecast: %w", err)
	}

	return p.writer.WriteMessages(ctx, kafka.Message{
		Key:   []byte(forecast.RegionID),
		Value: data,
	})
}
