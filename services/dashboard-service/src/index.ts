import dotenv from 'dotenv';
dotenv.config();

import { initPool, closePool } from './db';
import { initRedis, close as closeRedis } from './cache';
import { createServer } from './server';
import { createConsumer } from './consumer';

const PORT = parseInt(process.env['PORT'] ?? '3000', 10);
const KAFKA_BROKERS = (process.env['KAFKA_BROKERS'] ?? 'localhost:9092').split(',');
const POSTGRES_URL =
  process.env['POSTGRES_URL'] ??
  'postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction';
const REDIS_URL = process.env['REDIS_URL'] ?? 'redis://localhost:6379';

async function main(): Promise<void> {
  console.log('Starting Dashboard Service...');

  initPool(POSTGRES_URL);
  initRedis(REDIS_URL);

  const { httpServer, wsClients, start } = createServer();

  const consumer = createConsumer(KAFKA_BROKERS, 'dashboard-service-group', () => wsClients);

  start(PORT);

  async function shutdown(): Promise<void> {
    console.log('Shutting down Dashboard Service...');
    await consumer.disconnect();
    await closeRedis();
    await closePool();
    httpServer.close(() => process.exit(0));
  }

  process.on('SIGINT', () => void shutdown());
  process.on('SIGTERM', () => void shutdown());
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
