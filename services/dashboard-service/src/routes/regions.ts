import { Router, Request, Response } from 'express';
import { getPool } from '../db';
import { get as cacheGet, set as cacheSet } from '../cache';

const router = Router();

const RISK_COLOR: Record<string, string> = {
  High: 'Red',
  Medium: 'Yellow',
  Low: 'Green',
};

// GET /api/regions — all regions with highest risk level, color, last prediction timestamp
// Optional query param: disaster_type
router.get('/', async (req: Request, res: Response): Promise<void> => {
  const disasterType = req.query['disaster_type'] as string | undefined;
  const cacheKey = `regions:${disasterType ?? 'all'}`;

  const cached = await cacheGet(cacheKey);
  if (cached) {
    res.json(JSON.parse(cached));
    return;
  }

  const pool = getPool();

  // Get the most recent prediction per region (optionally filtered by disaster_type),
  // then pick the highest risk level per region.
  const riskOrder = `CASE risk_level WHEN 'High' THEN 3 WHEN 'Medium' THEN 2 ELSE 1 END`;

  const params: unknown[] = [];
  let disasterFilter = '';
  if (disasterType) {
    params.push(disasterType);
    disasterFilter = `AND p.disaster_type = $${params.length}`;
  }

  const query = `
    WITH latest AS (
      SELECT DISTINCT ON (region_id, disaster_type)
        region_id, disaster_type, risk_level, generated_at
      FROM predictions
      ${disasterType ? `WHERE disaster_type = $1` : ''}
      ORDER BY region_id, disaster_type, generated_at DESC
    ),
    ranked AS (
      SELECT region_id, risk_level, generated_at,
        ROW_NUMBER() OVER (
          PARTITION BY region_id
          ORDER BY ${riskOrder} DESC, generated_at DESC
        ) AS rn
      FROM latest
    )
    SELECT region_id, risk_level, generated_at AS last_prediction_at
    FROM ranked
    WHERE rn = 1
    ORDER BY region_id
  `;

  const result = await pool.query(query, params);

  const regions = result.rows.map((row) => ({
    region_id: row.region_id,
    risk_level: row.risk_level,
    color: RISK_COLOR[row.risk_level] ?? 'Green',
    last_prediction_at: row.last_prediction_at,
  }));

  await cacheSet(cacheKey, JSON.stringify(regions), 60);
  res.json(regions);
});

// GET /api/regions/:regionId — region detail per disaster type
router.get('/:regionId', async (req: Request, res: Response): Promise<void> => {
  const { regionId } = req.params;
  const cacheKey = `region:${regionId}`;

  const cached = await cacheGet(cacheKey);
  if (cached) {
    res.json(JSON.parse(cached));
    return;
  }

  const pool = getPool();

  const query = `
    SELECT DISTINCT ON (disaster_type)
      disaster_type, risk_level, probability_pct, time_to_impact_h,
      severity_index, generated_at
    FROM predictions
    WHERE region_id = $1
    ORDER BY disaster_type, generated_at DESC
  `;

  const result = await pool.query(query, [regionId]);

  if (result.rows.length === 0) {
    res.status(404).json({ error: 'Region not found' });
    return;
  }

  const detail = {
    region_id: regionId,
    disaster_types: result.rows.map((row) => ({
      disaster_type: row.disaster_type,
      risk_level: row.risk_level,
      probability_pct: row.probability_pct,
      time_to_impact_h: row.time_to_impact_h,
      severity_index: row.severity_index,
      generated_at: row.generated_at,
    })),
  };

  await cacheSet(cacheKey, JSON.stringify(detail), 60);
  res.json(detail);
});

export default router;
