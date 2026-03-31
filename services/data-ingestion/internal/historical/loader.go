// Package historical loads historical disaster event records from a CSV/JSON
// source and publishes them to the historical.disaster.event Kafka topic.
package historical

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"strings"
	"time"

	"github.com/segmentio/kafka-go"
	_ "github.com/lib/pq"
)

const historicalTopic = "historical.disaster.event"

// DisasterEvent represents a historical disaster event record.
type DisasterEvent struct {
	EventID      string  `json:"event_id"`
	RegionID     string  `json:"region_id"`
	DisasterType string  `json:"disaster_type"`
	StartDate    string  `json:"start_date"` // ISO 8601 date
	EndDate      string  `json:"end_date"`   // ISO 8601 date
	Severity     float64 `json:"severity"`   // 0–100
	Source       string  `json:"source"`
}

// Loader loads historical disaster events from PostgreSQL and publishes to Kafka.
type Loader struct {
	postgresURL  string
	kafkaBrokers string
	writer       *kafka.Writer
}

// NewLoader creates a Loader.
func NewLoader(postgresURL, kafkaBrokers string) *Loader {
	brokers := strings.Split(kafkaBrokers, ",")
	return &Loader{
		postgresURL:  postgresURL,
		kafkaBrokers: kafkaBrokers,
		writer: &kafka.Writer{
			Addr:     kafka.TCP(brokers...),
			Topic:    historicalTopic,
			Balancer: &kafka.LeastBytes{},
		},
	}
}

// Load reads all historical disaster events from PostgreSQL and publishes them to Kafka.
// It is safe to call multiple times (idempotent — uses ON CONFLICT DO NOTHING on the consumer side).
func (l *Loader) Load(ctx context.Context) error {
	db, err := sql.Open("postgres", l.postgresURL)
	if err != nil {
		return fmt.Errorf("open postgres: %w", err)
	}
	defer db.Close()

	if err := db.PingContext(ctx); err != nil {
		return fmt.Errorf("ping postgres: %w", err)
	}

	rows, err := db.QueryContext(ctx, `
		SELECT event_id, region_id, disaster_type,
		       start_date::text, end_date::text, severity, source
		FROM historical_disaster_events
		ORDER BY start_date ASC
	`)
	if err != nil {
		return fmt.Errorf("query historical_disaster_events: %w", err)
	}
	defer rows.Close()

	var published int
	for rows.Next() {
		var e DisasterEvent
		if err := rows.Scan(
			&e.EventID, &e.RegionID, &e.DisasterType,
			&e.StartDate, &e.EndDate, &e.Severity, &e.Source,
		); err != nil {
			slog.Error("historical loader: scan error", "error", err)
			continue
		}

		data, _ := json.Marshal(e)
		if err := l.writer.WriteMessages(ctx, kafka.Message{
			Key:   []byte(e.EventID),
			Value: data,
		}); err != nil {
			slog.Error("historical loader: publish error", "event_id", e.EventID, "error", err)
			continue
		}
		published++
	}

	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate rows: %w", err)
	}

	slog.Info("historical loader: published events", "count", published)
	_ = l.writer.Close()
	return nil
}

// RunPeriodic loads historical data at startup and then every HISTORICAL_RELOAD_INTERVAL_HOURS.
func (l *Loader) RunPeriodic(ctx context.Context) {
	intervalHours := 24
	if v := os.Getenv("HISTORICAL_RELOAD_INTERVAL_HOURS"); v != "" {
		fmt.Sscanf(v, "%d", &intervalHours)
	}
	interval := time.Duration(intervalHours) * time.Hour

	slog.Info("historical loader started", "reload_interval", interval)

	if err := l.Load(ctx); err != nil {
		slog.Error("historical loader: initial load failed", "error", err)
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			slog.Info("historical loader stopped")
			return
		case <-ticker.C:
			if err := l.Load(ctx); err != nil {
				slog.Error("historical loader: reload failed", "error", err)
			}
		}
	}
}
