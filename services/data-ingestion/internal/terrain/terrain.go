// Package terrain loads elevation/terrain and urban drainage data from
// PostgreSQL at startup and exposes an in-memory cache for other components.
package terrain

import (
	"database/sql"
	"fmt"
	"log/slog"

	_ "github.com/lib/pq"
)

// TerrainData holds elevation and terrain information for a region.
type TerrainData struct {
	RegionID        string
	ElevationM      float64
	TerrainType     string
	SlopeGradient   float64
	ElevationSource string
}

// DrainageData holds urban drainage capacity and status for a region.
type DrainageData struct {
	RegionID         string
	CapacityM3       float64
	CurrentStatusPct float64 // 0–100: percentage of capacity in use
	IsOperational    bool
}

// Cache is an in-memory store for terrain and drainage data.
type Cache struct {
	Terrain  map[string]TerrainData
	Drainage map[string]DrainageData
}

// LoadCache connects to PostgreSQL and loads terrain and drainage data into memory.
// It returns a populated Cache or an error if loading fails.
func LoadCache(postgresURL string) (*Cache, error) {
	db, err := sql.Open("postgres", postgresURL)
	if err != nil {
		return nil, fmt.Errorf("open postgres: %w", err)
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("ping postgres: %w", err)
	}

	cache := &Cache{
		Terrain:  make(map[string]TerrainData),
		Drainage: make(map[string]DrainageData),
	}

	if err := loadTerrain(db, cache); err != nil {
		return nil, err
	}

	if err := loadDrainage(db, cache); err != nil {
		return nil, err
	}

	slog.Info("terrain and drainage data loaded",
		"terrain_regions", len(cache.Terrain),
		"drainage_regions", len(cache.Drainage),
	)

	return cache, nil
}

// loadTerrain reads all rows from the regions_terrain table.
func loadTerrain(db *sql.DB, cache *Cache) error {
	rows, err := db.Query(`
		SELECT region_id, elevation_m, terrain_type, slope_gradient, elevation_source
		FROM regions_terrain
	`)
	if err != nil {
		return fmt.Errorf("query regions_terrain: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var td TerrainData
		if err := rows.Scan(
			&td.RegionID,
			&td.ElevationM,
			&td.TerrainType,
			&td.SlopeGradient,
			&td.ElevationSource,
		); err != nil {
			return fmt.Errorf("scan terrain row: %w", err)
		}
		cache.Terrain[td.RegionID] = td
	}

	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate terrain rows: %w", err)
	}

	slog.Info("terrain data loaded", "count", len(cache.Terrain))
	return nil
}

// loadDrainage reads drainage_assets rows for urban regions (is_urban = true).
func loadDrainage(db *sql.DB, cache *Cache) error {
	rows, err := db.Query(`
		SELECT region_id, capacity_m3, current_status_pct, is_operational
		FROM drainage_assets
		WHERE is_urban = true
	`)
	if err != nil {
		return fmt.Errorf("query drainage_assets: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var dd DrainageData
		if err := rows.Scan(
			&dd.RegionID,
			&dd.CapacityM3,
			&dd.CurrentStatusPct,
			&dd.IsOperational,
		); err != nil {
			return fmt.Errorf("scan drainage row: %w", err)
		}
		cache.Drainage[dd.RegionID] = dd
	}

	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate drainage rows: %w", err)
	}

	slog.Info("urban drainage data loaded", "count", len(cache.Drainage))
	return nil
}
