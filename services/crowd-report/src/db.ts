import { Pool } from 'pg';

let pool: Pool | null = null;

export function initPool(connectionString: string): void {
  pool = new Pool({ connectionString });
}

export function getPool(): Pool {
  if (!pool) throw new Error('PostgreSQL pool not initialized.');
  return pool;
}

export async function closePool(): Promise<void> {
  if (pool) { await pool.end(); pool = null; }
}

/** Find the region_id whose geometry contains the given GPS point. */
export async function findRegionByPoint(lat: number, lon: number): Promise<string | null> {
  const pool = getPool();
  // Uses PostGIS ST_Contains. Falls back to null if PostGIS not available.
  try {
    const result = await pool.query<{ region_id: string }>(
      `SELECT region_id FROM regions
       WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint($1, $2), 4326))
       LIMIT 1`,
      [lon, lat]
    );
    return result.rows[0]?.region_id ?? null;
  } catch {
    // PostGIS not available — return null (caller handles gracefully)
    return null;
  }
}

const _CREATE_REPORTS_TABLE = `
CREATE TABLE IF NOT EXISTS crowd_reports (
  report_id UUID PRIMARY KEY,
  user_id TEXT NOT NULL,
  region_id TEXT,
  disaster_type TEXT NOT NULL,
  image_url TEXT NOT NULL,
  description TEXT,
  reported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  lat FLOAT NOT NULL,
  lon FLOAT NOT NULL,
  validation_status TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_crowd_reports_region ON crowd_reports(region_id);
CREATE INDEX IF NOT EXISTS idx_crowd_reports_reported_at ON crowd_reports(reported_at);
`;

export async function ensureSchema(): Promise<void> {
  const pool = getPool();
  await pool.query(_CREATE_REPORTS_TABLE);
}

export async function insertReport(report: {
  report_id: string;
  user_id: string;
  region_id: string | null;
  disaster_type: string;
  image_url: string;
  description: string | null;
  lat: number;
  lon: number;
}): Promise<void> {
  const pool = getPool();
  await pool.query(
    `INSERT INTO crowd_reports
       (report_id, user_id, region_id, disaster_type, image_url, description, lat, lon)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
    [report.report_id, report.user_id, report.region_id, report.disaster_type,
     report.image_url, report.description, report.lat, report.lon]
  );
}

/** Count reports for a region+disaster_type within the last hour. */
export async function countRecentReports(regionId: string, disasterType: string): Promise<number> {
  const pool = getPool();
  const result = await pool.query<{ count: string }>(
    `SELECT COUNT(*) AS count FROM crowd_reports
     WHERE region_id = $1 AND disaster_type = $2
       AND reported_at >= NOW() - INTERVAL '1 hour'`,
    [regionId, disasterType]
  );
  return parseInt(result.rows[0]?.count ?? '0', 10);
}
