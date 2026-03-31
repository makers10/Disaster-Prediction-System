/**
 * Crowd Report Service — accepts image uploads and disaster type tags
 * from registered users, associates reports with regions via GPS coordinates.
 */

import dotenv from 'dotenv';
dotenv.config();

import express, { Request, Response } from 'express';
import cors from 'cors';
import multer from 'multer';
import { v4 as uuidv4 } from 'uuid';
import { initPool, closePool, ensureSchema, findRegionByPoint, insertReport, countRecentReports } from './db';
import { uploadImage } from './storage';
import { initProducer, publishEvent, closeProducer } from './kafka';

const PORT = parseInt(process.env['PORT'] ?? '3002', 10);
const KAFKA_BROKERS = (process.env['KAFKA_BROKERS'] ?? 'localhost:9092').split(',');
const POSTGRES_URL = process.env['POSTGRES_URL'] ?? 'postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction';
const THRESHOLD = 3; // crowd reports per region/type per hour to trigger alert

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 10 * 1024 * 1024 } });

const app = express();
app.use(cors());
app.use(express.json());

/**
 * POST /api/reports
 * Multipart form: image (file), disaster_type (string), description (string, optional),
 *                 lat (number), lon (number), user_id (string)
 */
app.post('/api/reports', upload.single('image'), async (req: Request, res: Response): Promise<void> => {
  try {
    const { disaster_type, description, lat, lon, user_id } = req.body as Record<string, string>;

    if (!disaster_type || !lat || !lon || !user_id) {
      res.status(400).json({ error: 'disaster_type, lat, lon, user_id are required' });
      return;
    }

    const latNum = parseFloat(lat);
    const lonNum = parseFloat(lon);
    if (isNaN(latNum) || isNaN(lonNum)) {
      res.status(400).json({ error: 'lat and lon must be valid numbers' });
      return;
    }

    // Upload image
    let imageUrl = 'no-image';
    if (req.file) {
      imageUrl = await uploadImage(req.file.buffer, req.file.originalname);
    }

    // Associate with region via PostGIS point-in-polygon
    const regionId = await findRegionByPoint(latNum, lonNum);

    const reportId = uuidv4();
    await insertReport({
      report_id: reportId,
      user_id,
      region_id: regionId,
      disaster_type,
      image_url: imageUrl,
      description: description ?? null,
      lat: latNum,
      lon: lonNum,
    });

    // Publish crowd.report.submitted
    const reportPayload = {
      report_id: reportId,
      user_id,
      region_id: regionId,
      disaster_type,
      image_url: imageUrl,
      description: description ?? null,
      reported_at: new Date().toISOString(),
      location: { lat: latNum, lon: lonNum },
      validation_status: 'pending',
    };
    await publishEvent('crowd.report.submitted', reportId, reportPayload);

    // Check threshold: >= 3 reports of same type in same region within 1 hour
    if (regionId) {
      const count = await countRecentReports(regionId, disaster_type);
      if (count >= THRESHOLD) {
        await publishEvent('crowd.report.threshold.exceeded', `${regionId}:${disaster_type}`, {
          region_id: regionId,
          disaster_type,
          report_count: count,
        });
        console.log(`Threshold exceeded: region=${regionId} type=${disaster_type} count=${count}`);
      }
    }

    res.status(201).json({ report_id: reportId, region_id: regionId, image_url: imageUrl });
  } catch (err) {
    console.error('Error submitting crowd report:', err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

/** GET /api/reports — list recent reports (for dashboard map markers) */
app.get('/api/reports', async (_req: Request, res: Response): Promise<void> => {
  try {
    const { getPool } = await import('./db');
    const result = await getPool().query(
      `SELECT report_id, user_id, region_id, disaster_type, image_url,
              description, reported_at, lat, lon, validation_status
       FROM crowd_reports
       ORDER BY reported_at DESC LIMIT 200`
    );
    res.json(result.rows);
  } catch (err) {
    console.error('Error fetching reports:', err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

async function main(): Promise<void> {
  console.log('Starting Crowd Report Service...');

  initPool(POSTGRES_URL);
  await ensureSchema();
  await initProducer(KAFKA_BROKERS);

  const server = app.listen(PORT, () => {
    console.log(`Crowd Report Service listening on port ${PORT}`);
  });

  async function shutdown(): Promise<void> {
    console.log('Shutting down Crowd Report Service...');
    server.close();
    await closeProducer();
    await closePool();
    process.exit(0);
  }

  process.on('SIGINT', () => void shutdown());
  process.on('SIGTERM', () => void shutdown());
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
