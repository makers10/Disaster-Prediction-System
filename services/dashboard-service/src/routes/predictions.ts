import { Router, Request, Response } from 'express';
import { getPool } from '../db';

const router = Router();

// GET /api/predictions — recent predictions with optional filters
// Query params: region_id, disaster_type, from (ISO date), to (ISO date)
router.get('/', async (req: Request, res: Response): Promise<void> => {
  const { region_id, disaster_type, from, to } = req.query as Record<string, string | undefined>;

  const pool = getPool();
  const conditions: string[] = [];
  const params: unknown[] = [];

  if (region_id) {
    params.push(region_id);
    conditions.push(`region_id = $${params.length}`);
  }
  if (disaster_type) {
    params.push(disaster_type);
    conditions.push(`disaster_type = $${params.length}`);
  }
  if (from) {
    params.push(from);
    conditions.push(`generated_at >= $${params.length}`);
  }
  if (to) {
    params.push(to);
    conditions.push(`generated_at <= $${params.length}`);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

  const query = `
    SELECT prediction_id, region_id, disaster_type, forecast_horizon_h,
           risk_level, probability_pct, time_to_impact_h, severity_index,
           generated_at, model_version
    FROM predictions
    ${where}
    ORDER BY generated_at DESC
    LIMIT 500
  `;

  const result = await pool.query(query, params);
  res.json(result.rows);
});

export default router;
