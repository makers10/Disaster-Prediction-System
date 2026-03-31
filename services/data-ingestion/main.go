package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/joho/godotenv"

	"github.com/disaster-prediction/data-ingestion/internal/govfeed"
	"github.com/disaster-prediction/data-ingestion/internal/historical"
	"github.com/disaster-prediction/data-ingestion/internal/ingestion"
	"github.com/disaster-prediction/data-ingestion/internal/satellite"
	"github.com/disaster-prediction/data-ingestion/internal/terrain"
	"github.com/disaster-prediction/data-ingestion/internal/validator"
	"github.com/disaster-prediction/data-ingestion/internal/weather"
)

func main() {
	// Load .env if present (no-op in production where env vars are injected).
	_ = godotenv.Load()

	slog.Info("starting Data Ingestion Service")

	kafkaBrokers := getEnv("KAFKA_BROKERS", "localhost:9092")
	postgresURL := getEnv("POSTGRES_URL", "postgres://disaster_user:disaster_pass@localhost:5432/disaster_prediction?sslmode=disable")
	validatorGroupID := getEnv("VALIDATOR_GROUP_ID", "data-validator")

	slog.Info("configuration loaded",
		"kafka_brokers", kafkaBrokers,
		"validator_group_id", validatorGroupID,
	)

	// --- Task 2.6: Load terrain and drainage data at startup ---
	terrainCache, err := terrain.LoadCache(postgresURL)
	if err != nil {
		slog.Error("failed to load terrain/drainage data", "error", err)
		// Non-fatal: continue without terrain cache; prediction engine will degrade gracefully.
	} else {
		slog.Info("terrain cache ready",
			"terrain_regions", len(terrainCache.Terrain),
			"drainage_regions", len(terrainCache.Drainage),
		)
	}

	// --- Task 2.1: Sensor ingestion poller ---
	poller, err := ingestion.NewPoller(kafkaBrokers)
	if err != nil {
		slog.Error("failed to create sensor poller", "error", err)
		os.Exit(1)
	}

	// --- Task 2.3: Data validator & normalizer ---
	v := validator.NewValidator(kafkaBrokers, validatorGroupID)

	// --- Task 3.1: Weather API poller ---
	weatherPoller, err := weather.NewWeatherPoller(kafkaBrokers)
	if err != nil {
		slog.Error("failed to create weather poller", "error", err)
		os.Exit(1)
	}

	// --- Task 14.1: Satellite ingestion connector ---
	satConnector, satErr := satellite.NewConnectorFromEnv(kafkaBrokers)
	if satErr != nil {
		slog.Warn("satellite connector not configured — skipping", "reason", satErr)
		satConnector = nil
	}

	// --- Task 17.1: Historical data loader ---
	histLoader := historical.NewLoader(postgresURL, kafkaBrokers)

	// --- Task 22.1: Government data feed connector ---
	govConnector, govErr := govfeed.NewGovFeedConnectorFromEnv(kafkaBrokers)
	if govErr != nil {
		slog.Warn("gov feed connector not configured — skipping", "reason", govErr)
		govConnector = nil
	}

	ctx, cancel := context.WithCancel(context.Background())

	// Run all services as goroutines.
	go poller.Run(ctx)
	go weatherPoller.Run(ctx)
	go v.Run(ctx)
	if satConnector != nil {
		go satConnector.Run(ctx)
	}
	go histLoader.RunPeriodic(ctx)
	if govConnector != nil {
		go govConnector.Run(ctx)
	}

	slog.Info("Data Ingestion Service running — waiting for shutdown signal")

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	slog.Info("shutdown signal received — stopping Data Ingestion Service")
	cancel()
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}
