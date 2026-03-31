import dotenv from 'dotenv';
dotenv.config();

import express from 'express';
import cors from 'cors';
import path from 'path';
import { initPool, closePool } from './db';
import chatRouter from './router';

const PORT = parseInt(process.env['PORT'] ?? '3001', 10);
const POSTGRES_URL =
  process.env['POSTGRES_URL'] ??
  'postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction';

async function main(): Promise<void> {
  console.log('Starting Conversational AI Service...');

  initPool(POSTGRES_URL);

  const app = express();
  app.use(cors());
  app.use(express.json());

  // Serve chat UI
  app.use(express.static(path.join(__dirname, '..', 'public')));

  // API routes
  app.use('/api', chatRouter);

  // Fallback to chat UI
  app.get('*', (_req, res) => {
    res.sendFile(path.join(__dirname, '..', 'public', 'chat.html'));
  });

  const server = app.listen(PORT, () => {
    console.log(`Conversational AI Service listening on port ${PORT}`);
  });

  async function shutdown(): Promise<void> {
    console.log('Shutting down Conversational AI Service...');
    server.close();
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
