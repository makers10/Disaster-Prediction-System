import { Router, Request, Response } from 'express';
import { getPool } from '../db';

const router = Router();

// Build common WHERE clause from query params
function buildFilters(
  params: Record<string, string | undefined>,
  dateField: string
): { conditions: string[]; values: unknown[] } {
  const { region_id, disaster_type, from, to } = params;
  const conditions: string[] = [];
  const values: unknown[] = [];

  if (region_id) {
    values.push(region_id);
    conditions.push(`region_id = $${values.length}`);
  }
  if (disaster_type) {
    values.push(disaster_type);
    conditions.push(`disaster_type = $${values.length}`);
  }
  if (from) {
    values.push(from);
    conditions.push(`${dateField} >= $${values.length}`);
  }
  if (to) {
    values.push(to);
    conditions.push(`${dateField} <= $${values.length}`);
  }

  return { conditions, values };
}

// GET /api/history/events
router.get('/events', async (req: Request, res: Response): Promise<void> => {
  const pool = getPool();
  const { conditions, values } = buildFilters(
    req.query as Record<string, string | undefined>,
    'start_date'
  );
  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

  const query = `
    SELECT event_id, region_id, disaster_type, start_date, end_date, severity, source
    FROM historical_disaster_events
    ${where}
    ORDER BY start_date DESC
    LIMIT 500
  `;

  const result = await pool.query(query, values);
  res.json(result.rows);
});

// GET /api/history/comparison
router.get('/comparison', async (req: Request, res: Response): Promise<void> => {
  const pool = getPool();
  const { region_id, disaster_type, from, to } = req.query as Record<string, string | undefined>;
  const conditions: string[] = [];
  const values: unknown[] = [];

  if (region_id) {
    values.push(region_id);
    conditions.push(`p.region_id = $${values.length}`);
  }
  if (disaster_type) {
    values.push(disaster_type);
    conditions.push(`p.disaster_type = $${values.length}`);
  }
  if (from) {
    values.push(from);
    conditions.push(`p.generated_at >= $${values.length}`);
  }
  if (to) {
    values.push(to);
    conditions.push(`p.generated_at <= $${values.length}`);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

  const query = `
    SELECT
      p.prediction_id,
      p.region_id,
      p.disaster_type,
      p.forecast_horizon_h,
      p.risk_level AS predicted_risk_level,
      p.probability_pct AS predicted_probability_pct,
      ao.actual_occurred,
      ao.actual_severity,
      p.generated_at
    FROM predictions p
    JOIN actual_outcomes ao ON ao.prediction_id = p.prediction_id
    ${where}
    ORDER BY p.generated_at DESC
    LIMIT 500
  `;

  const result = await pool.query(query, values);
  res.json(result.rows);
});

// GET /api/history/accuracy
router.get('/accuracy', async (req: Request, res: Response): Promise<void> => {
  const pool = getPool();
  const { region_id, disaster_type, from, to } = req.query as Record<string, string | undefined>;
  const conditions: string[] = [];
  const values: unknown[] = [];

  if (region_id) {
    values.push(region_id);
    conditions.push(`p.region_id = $${values.length}`);
  }
  if (disaster_type) {
    values.push(disaster_type);
    conditions.push(`p.disaster_type = $${values.length}`);
  }
  if (from) {
    values.push(from);
    conditions.push(`p.generated_at >= $${values.length}`);
  }
  if (to) {
    values.push(to);
    conditions.push(`p.generated_at <= $${values.length}`);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

  // A prediction is "positive" if risk_level is Medium or High
  // An "actual positive" is when actual_occurred = true
  const query = `
    SELECT
      p.disaster_type,
      COUNT(*) FILTER (
        WHERE p.risk_level IN ('Medium','High') AND ao.actual_occurred = true
      ) AS true_positives,
      COUNT(*) FILTER (
        WHERE p.risk_level IN ('Medium','High') AND ao.actual_occurred = false
      ) AS false_positives,
      COUNT(*) FILTER (
        WHERE p.risk_level NOT IN ('Medium','High') AND ao.actual_occurred = true
      ) AS false_negatives,
      COUNT(*) FILTER (
        WHERE p.risk_level NOT IN ('Medium','High') AND ao.actual_occurred = false
      ) AS true_negatives,
      COUNT(*) AS total_predictions,
      MIN(p.generated_at) AS from_date,
      MAX(p.generated_at) AS to_date
    FROM predictions p
    JOIN actual_outcomes ao ON ao.prediction_id = p.prediction_id
    ${where}
    GROUP BY p.disaster_type
    ORDER BY p.disaster_type
  `;

  const result = await pool.query(query, values);

  const rows = result.rows.map((row) => {
    const tp = Number(row.true_positives);
    const fp = Number(row.false_positives);
    const fn = Number(row.false_negatives);
    const tn = Number(row.true_negatives);

    const precision = tp + fp > 0 ? tp / (tp + fp) : null;
    const recall = tp + fn > 0 ? tp / (tp + fn) : null;
    const false_alarm_rate = fp + tn > 0 ? fp / (fp + tn) : null;

    return {
      disaster_type: row.disaster_type,
      precision,
      recall,
      false_alarm_rate,
      total_predictions: Number(row.total_predictions),
      from: row.from_date,
      to: row.to_date,
    };
  });

  res.json(rows);
});

// GET /api/history/patterns
router.get('/patterns', async (req: Request, res: Response): Promise<void> => {
  const { region_id, disaster_type } = req.query as Record<string, string | undefined>;

  if (!region_id) {
    res.status(400).json({ error: 'region_id is required' });
    return;
  }

  const pool = getPool();

  // Check if >= 2 years of data exist for this region
  const rangeParams: unknown[] = [region_id];
  let rangeFilter = `WHERE region_id = $1`;
  if (disaster_type) {
    rangeParams.push(disaster_type);
    rangeFilter += ` AND disaster_type = $2`;
  }

  const rangeQuery = `
    SELECT
      MIN(start_date) AS earliest,
      MAX(start_date) AS latest
    FROM historical_disaster_events
    ${rangeFilter}
  `;

  const rangeResult = await pool.query(rangeQuery, rangeParams);
  const { earliest, latest } = rangeResult.rows[0] ?? {};

  if (!earliest || !latest) {
    res.json({ has_sufficient_data: false, patterns: [] });
    return;
  }

  const diffMs = new Date(latest).getTime() - new Date(earliest).getTime();
  const diffYears = diffMs / (1000 * 60 * 60 * 24 * 365.25);

  if (diffYears < 2) {
    res.json({ has_sufficient_data: false, patterns: [] });
    return;
  }

  // Group by month and disaster_type
  const patternParams: unknown[] = [region_id];
  let patternFilter = `WHERE region_id = $1`;
  if (disaster_type) {
    patternParams.push(disaster_type);
    patternFilter += ` AND disaster_type = $2`;
  }

  const patternQuery = `
    SELECT
      EXTRACT(MONTH FROM start_date)::int AS month,
      disaster_type,
      COUNT(*)::int AS count
    FROM historical_disaster_events
    ${patternFilter}
    GROUP BY month, disaster_type
    ORDER BY disaster_type, month
  `;

  const patternResult = await pool.query(patternQuery, patternParams);

  res.json({
    has_sufficient_data: true,
    patterns: patternResult.rows.map((r) => ({
      month: r.month,
      count: r.count,
      disaster_type: r.disaster_type,
    })),
  });
});

export default router;
