/**
 * Alert Service — dispatches SMS, push, and voice notifications
 * for disaster risk predictions.
 */

import dotenv from 'dotenv';
dotenv.config();

import { Kafka, Producer } from 'kafkajs';
import { AlertRecord } from '../../../shared/types/index';
import { initPool, closePool } from './userStore';
import { createConsumer } from './consumer';

const KAFKA_BROKERS = (process.env.KAFKA_BROKERS ?? 'localhost:9092').split(',');
const POSTGRES_URL =
  process.env.POSTGRES_URL ??
  'postgresql://disaster_user:disaster_pass@localhost:5432/disaster_prediction';
const KAFKA_GROUP_ID = process.env.KAFKA_GROUP_ID ?? 'alert-service';
const TOPIC_ALERT_DISPATCHED = 'alert.dispatched';

async function main(): Promise<void> {
  console.log('Starting Alert Service...');

  // Initialize PostgreSQL connection pool
  initPool(POSTGRES_URL);

  // Initialize Kafka producer for alert.dispatched
  const kafka = new Kafka({ clientId: 'alert-service-producer', brokers: KAFKA_BROKERS });
  const producer: Producer = kafka.producer();
  await producer.connect();
  console.log('Kafka producer connected.');

  // Publisher function passed to dispatcher
  async function publishAlert(record: AlertRecord): Promise<void> {
    await producer.send({
      topic: TOPIC_ALERT_DISPATCHED,
      messages: [
        {
          key: record.alert_id,
          value: JSON.stringify(record),
        },
      ],
    });
  }

  // Start Kafka consumer
  const consumer = createConsumer(KAFKA_BROKERS, KAFKA_GROUP_ID, publishAlert);
  console.log(`Kafka consumer started, listening on prediction.generated`);

  async function shutdown(): Promise<void> {
    console.log('Shutting down Alert Service...');
    await consumer.disconnect();
    await producer.disconnect();
    await closePool();
    process.exit(0);
  }

  process.on('SIGINT', () => { shutdown().catch(console.error); });
  process.on('SIGTERM', () => { shutdown().catch(console.error); });

  // Keep process alive
  await new Promise(() => {});
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
