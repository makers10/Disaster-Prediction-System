// Shared TypeScript interfaces for the Disaster Prediction System

export interface SensorReading {
  sensor_id: string;
  region_id: string;
  timestamp: string; // ISO 8601
  rainfall_mm: number | null;
  temperature_c: number | null;
  river_level_m: number | null;
  soil_moisture_pct: number | null;
  wind_speed_kmh: number | null;
  wind_direction_deg: number | null;
  is_anomalous: boolean;
  stream_status: 'ok' | 'degraded' | 'unavailable';
}

export interface SatelliteImageMetadata {
  image_id: string;
  region_id: string;
  provider: string;
  captured_at: string; // ISO 8601
  received_at: string; // ISO 8601
  resolution_m: number;
  feed_status: 'ok' | 'unavailable';
}

export interface CNNFeatures {
  image_id: string;
  region_id: string;
  extracted_at: string; // ISO 8601
  flood_inundation_pct: number; // 0–100
  cloud_density: number; // 0–1
  vegetation_index: number; // 0–1 (NDVI proxy)
}

export interface PredictionRecord {
  prediction_id: string; // UUID
  region_id: string;
  disaster_type: 'flood' | 'heatwave' | 'drought' | 'landslide' | 'cyclone';
  forecast_horizon_h: 6 | 24 | 72;
  risk_level: 'Low' | 'Medium' | 'High';
  probability_pct: number; // 0–100
  time_to_impact_h: number | null; // null if risk_level is Low
  severity_index: number; // 0–100
  generated_at: string; // ISO 8601
  model_version: string;
  input_data_snapshot_id: string;
}

export interface XAIExplanation {
  explanation_id: string; // UUID
  prediction_id: string; // FK to PredictionRecord
  generated_at: string; // ISO 8601
  contributing_factors: Array<{
    feature_name: string;
    contribution_pct: number; // 0–100, sum ≤ 100
    direction: 'positive' | 'negative';
  }>;
  plain_language_summary: string;
}

export interface AlertRecord {
  alert_id: string; // UUID
  prediction_id: string; // FK to PredictionRecord
  region_id: string;
  disaster_type: string;
  risk_level: 'Medium' | 'High';
  time_to_impact_h: number;
  recommended_action: string;
  evacuation_route_id: string | null;
  language_code: string; // BCP-47
  channel: 'sms' | 'push' | 'voice';
  dispatched_at: string; // ISO 8601
  delivery_status: 'sent' | 'delivered' | 'failed';
  retry_count: number;
}

export interface UserProfile {
  user_id: string; // UUID
  phone_number: string | null;
  push_token: string | null;
  language_code: string; // BCP-47
  region_ids: string[]; // home + subscribed regions
  is_infrastructure_operator: boolean;
  infrastructure_ids: string[];
  notification_channels: Array<'sms' | 'push' | 'voice'>;
}

export interface CrowdReport {
  report_id: string; // UUID
  user_id: string;
  region_id: string;
  disaster_type: string;
  image_url: string; // object store URL
  description: string | null;
  reported_at: string; // ISO 8601
  location: { lat: number; lon: number };
  validation_status: 'pending' | 'validated' | 'rejected';
}

export interface EvacuationRoute {
  route_id: string; // UUID
  region_id: string;
  prediction_id: string; // triggering prediction
  origin: { lat: number; lon: number; label: string };
  destination: { lat: number; lon: number; label: string };
  waypoints: Array<{ lat: number; lon: number }>;
  distance_km: number;
  estimated_duration_min: number;
  avoids: string[]; // e.g., ["flood_zone_A", "landslide_zone_B"]
  computed_at: string; // ISO 8601
  is_blocked: boolean;
}

export interface HistoricalDisasterEvent {
  event_id: string;
  region_id: string;
  disaster_type: string;
  start_date: string; // ISO 8601 date
  end_date: string; // ISO 8601 date
  severity: number; // 0–100
  source: string;
}

export interface InfrastructureAsset {
  asset_id: string;
  region_id: string;
  asset_type: 'dam' | 'urban_drainage';
  name: string;
  location: { lat: number; lon: number };
  operator_user_ids: string[];
  capacity_m3: number | null;
}
