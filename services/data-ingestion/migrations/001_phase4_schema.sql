-- Phase 4 schema additions

-- Region adjacency graph for GNN
CREATE TABLE IF NOT EXISTS region_adjacency (
    region_id    TEXT NOT NULL,
    neighbour_id TEXT NOT NULL,
    edge_weight  FLOAT NOT NULL DEFAULT 1.0,
    PRIMARY KEY (region_id, neighbour_id)
);

-- Road network for evacuation planner
CREATE TABLE IF NOT EXISTS road_nodes (
    node_id TEXT PRIMARY KEY,
    lat     FLOAT NOT NULL,
    lon     FLOAT NOT NULL,
    label   TEXT
);

CREATE TABLE IF NOT EXISTS road_edges (
    edge_id     TEXT PRIMARY KEY,
    from_node   TEXT NOT NULL REFERENCES road_nodes(node_id),
    to_node     TEXT NOT NULL REFERENCES road_nodes(node_id),
    distance_km FLOAT NOT NULL,
    road_id     TEXT NOT NULL,
    is_blocked  BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_road_edges_from ON road_edges(from_node);
CREATE INDEX IF NOT EXISTS idx_road_edges_road_id ON road_edges(road_id);

-- Hazard zones for evacuation route avoidance
CREATE TABLE IF NOT EXISTS hazard_zones (
    zone_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_id   TEXT NOT NULL,
    hazard_type TEXT NOT NULL, -- 'flood_inundation' | 'landslide_high'
    geometry    GEOMETRY(Polygon, 4326)
);
CREATE INDEX IF NOT EXISTS idx_hazard_zones_region ON hazard_zones(region_id);

-- Infrastructure assets for smart infra alerter
CREATE TABLE IF NOT EXISTS infrastructure_assets (
    asset_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_id         TEXT NOT NULL,
    asset_type        TEXT NOT NULL CHECK (asset_type IN ('dam', 'urban_drainage')),
    name              TEXT NOT NULL,
    lat               FLOAT NOT NULL,
    lon               FLOAT NOT NULL,
    operator_user_ids TEXT[] NOT NULL DEFAULT '{}',
    capacity_m3       FLOAT
);
CREATE INDEX IF NOT EXISTS idx_infra_region ON infrastructure_assets(region_id);
