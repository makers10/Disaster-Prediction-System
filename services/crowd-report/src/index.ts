/**
 * Crowd Report Service — accepts image uploads and disaster type tags
 * from registered users, associates reports with regions via GPS coordinates.
 */

import dotenv from 'dotenv';
dotenv.config();

const PORT = parseInt(process.env.PORT ?? '3002', 10);
const KAFKA_BROKERS = process.env.KAFKA_BROKERS ?? 'localhost:9092';
const POSTGRES_URL = process.env.POSTGRES_URL ?? 'postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction';
const S3_BUCKET = process.env.S3_BUCKET ?? 'crowd-reports';

async function main(): Promise<void> {
  console.log('Starting Crowd Report Service...');
  console.log(`Port: ${PORT}`);
  console.log(`Kafka brokers: ${KAFKA_BROKERS}`);
  console.log(`PostgreSQL URL: ${POSTGRES_URL}`);
  console.log(`S3 bucket: ${S3_BUCKET}`);

  // TODO: Initialize Express app with multer for image uploads
  // TODO: Initialize PostgreSQL client with PostGIS for point-in-polygon queries
  // TODO: Initialize KafkaJS producer
  // TODO: Initialize S3 client for image storage
  // TODO: Implement POST /api/reports — accept image + disaster_type + description + GPS
  // TODO: Associate report with region_id via PostGIS point-in-polygon
  // TODO: Publish crowd.report.submitted event to Kafka
  // TODO: Monitor sliding 1-hour window; publish crowd.report.threshold.exceeded when count >= 3

  process.on('SIGINT', () => {
    console.log('Shutting down Crowd Report Service...');
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    console.log('Shutting down Crowd Report Service...');
    process.exit(0);
  });

  await new Promise(() => {});
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
