// Package validator consumes raw.sensor.reading, validates and normalises
// readings, and publishes valid non-anomalous readings to validated.sensor.reading.
package validator

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/segmentio/kafka-go"

	"github.com/disaster-prediction/data-ingestion/internal/ingestion"
)

const (
	rawTopic       = "raw.sensor.reading"
	validatedTopic = "validated.sensor.reading"
)

// Validator consumes raw sensor readings, validates them, and publishes valid ones.
type Validator struct {
	reader *kafka.Reader
	writer *kafka.Writer
}

// NewValidator creates a Validator connected to the given Kafka brokers.
func NewValidator(kafkaBrokers, groupID string) *Validator {
	brokers := strings.Split(kafkaBrokers, ",")

	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers:  brokers,
		Topic:    rawTopic,
		GroupID:  groupID,
		MinBytes: 1,
		MaxBytes: 10e6,
		MaxWait:  time.Second,
	})

	writer := &kafka.Writer{
		Addr:     kafka.TCP(brokers...),
		Topic:    validatedTopic,
		Balancer: &kafka.LeastBytes{},
	}

	return &Validator{reader: reader, writer: writer}
}

// Run starts the consume-validate-publish loop; blocks until ctx is cancelled.
func (v *Validator) Run(ctx context.Context) {
	slog.Info("data validator started", "input_topic", rawTopic, "output_topic", validatedTopic)
	defer func() {
		_ = v.reader.Close()
		_ = v.writer.Close()
		slog.Info("data validator stopped")
	}()

	for {
		msg, err := v.reader.ReadMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			slog.Error("failed to read message", "error", err)
			continue
		}

		reading, ok := v.parseAndValidate(msg.Value)
		if !ok {
			continue
		}

		if reading.IsAnomalous {
			slog.Info("excluding anomalous reading from validated output",
				"sensor_id", reading.SensorID,
			)
			continue
		}

		if err := v.publish(ctx, reading); err != nil {
			slog.Error("failed to publish validated reading",
				"sensor_id", reading.SensorID,
				"error", err,
			)
		} else {
			slog.Info("published validated reading", "sensor_id", reading.SensorID)
		}
	}
}

// parseAndValidate deserialises and validates a raw Kafka message payload.
// Returns (reading, true) on success, (nil, false) on any validation failure.
func (v *Validator) parseAndValidate(payload []byte) (*ingestion.SensorReading, bool) {
	// --- Schema validation: required fields ---
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(payload, &raw); err != nil {
		slog.Error("rejected payload: invalid JSON", "error", err)
		return nil, false
	}

	requiredFields := []string{"sensor_id", "region_id", "timestamp", "stream_status"}
	for _, field := range requiredFields {
		val, present := raw[field]
		if !present || string(val) == "null" || string(val) == `""` {
			slog.Error("rejected payload: missing required field", "field", field)
			return nil, false
		}
	}

	var reading ingestion.SensorReading
	if err := json.Unmarshal(payload, &reading); err != nil {
		slog.Error("rejected payload: failed to decode sensor reading", "error", err)
		return nil, false
	}

	// --- Physical plausibility checks ---
	anomalous := false

	if reading.TemperatureC != nil {
		if err := checkRange("temperature_c", *reading.TemperatureC, -90, 60); err != nil {
			slog.Warn(err.Error(), "sensor_id", reading.SensorID, "value", *reading.TemperatureC)
			anomalous = true
		}
	}

	if reading.RainfallMM != nil {
		if err := checkMin("rainfall_mm", *reading.RainfallMM, 0); err != nil {
			slog.Warn(err.Error(), "sensor_id", reading.SensorID, "value", *reading.RainfallMM)
			anomalous = true
		}
	}

	if reading.RiverLevelM != nil {
		if err := checkMin("river_level_m", *reading.RiverLevelM, 0); err != nil {
			slog.Warn(err.Error(), "sensor_id", reading.SensorID, "value", *reading.RiverLevelM)
			anomalous = true
		}
	}

	if reading.SoilMoisturePct != nil {
		if err := checkRange("soil_moisture_pct", *reading.SoilMoisturePct, 0, 100); err != nil {
			slog.Warn(err.Error(), "sensor_id", reading.SensorID, "value", *reading.SoilMoisturePct)
			anomalous = true
		}
	}

	if reading.WindSpeedKmh != nil {
		if err := checkMin("wind_speed_kmh", *reading.WindSpeedKmh, 0); err != nil {
			slog.Warn(err.Error(), "sensor_id", reading.SensorID, "value", *reading.WindSpeedKmh)
			anomalous = true
		}
	}

	if reading.WindDirectionDeg != nil {
		if err := checkRange("wind_direction_deg", *reading.WindDirectionDeg, 0, 360); err != nil {
			slog.Warn(err.Error(), "sensor_id", reading.SensorID, "value", *reading.WindDirectionDeg)
			anomalous = true
		}
	}

	reading.IsAnomalous = anomalous
	return &reading, true
}

// publish serialises a validated SensorReading and writes it to Kafka.
func (v *Validator) publish(ctx context.Context, reading *ingestion.SensorReading) error {
	data, err := json.Marshal(reading)
	if err != nil {
		return fmt.Errorf("marshal reading: %w", err)
	}
	return v.writer.WriteMessages(ctx, kafka.Message{
		Key:   []byte(reading.SensorID),
		Value: data,
	})
}

// checkRange returns an error if value is outside [min, max].
func checkRange(field string, value, min, max float64) error {
	if value < min || value > max {
		return fmt.Errorf("anomalous value for field %s: %.4f not in [%.4f, %.4f]", field, value, min, max)
	}
	return nil
}

// checkMin returns an error if value is below min.
func checkMin(field string, value, min float64) error {
	if value < min {
		return fmt.Errorf("anomalous value for field %s: %.4f is below minimum %.4f", field, value, min)
	}
	return nil
}

// ParseAndValidate is the exported entry point used by tests and other packages.
func ParseAndValidate(payload []byte) (*ingestion.SensorReading, bool, string) {
	v := &Validator{}
	reading, ok := v.parseAndValidate(payload)
	if !ok {
		return nil, false, "validation failed"
	}
	return reading, true, ""
}
