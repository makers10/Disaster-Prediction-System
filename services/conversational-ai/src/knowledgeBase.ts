import { getPool } from './db';

export interface RegionPrediction {
  region_id: string;
  disaster_type: string;
  risk_level: 'Low' | 'Medium' | 'High';
  probability_pct: number;
  time_to_impact_h: number | null;
  severity_index: number;
  generated_at: string;
}

/**
 * Returns the most recent prediction per disaster type for the given region.
 */
export async function getLatestPredictions(regionId: string): Promise<RegionPrediction[]> {
  const pool = getPool();
  const query = `
    SELECT DISTINCT ON (disaster_type)
      region_id,
      disaster_type,
      risk_level,
      probability_pct,
      time_to_impact_h,
      severity_index,
      generated_at
    FROM predictions
    WHERE region_id = $1
    ORDER BY disaster_type, generated_at DESC
  `;
  const result = await pool.query<RegionPrediction>(query, [regionId]);
  return result.rows;
}

/**
 * Returns all distinct region_ids from the predictions table.
 * Used for region detection in intent classification.
 */
export async function getRegionIds(): Promise<string[]> {
  const pool = getPool();
  const result = await pool.query<{ region_id: string }>(
    'SELECT DISTINCT region_id FROM predictions'
  );
  return result.rows.map((r: { region_id: string }) => r.region_id);
}
