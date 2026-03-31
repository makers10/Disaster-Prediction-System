import { Kafka, Consumer, EachMessagePayload } from 'kafkajs';
import { WebSocket } from 'ws';
import { set as cacheSet } from './cache';
import { PredictionRecord } from '../../../shared/types/index';

const TOPIC = 'prediction.generated';

export function createConsumer(
  brokers: string[],
  groupId: string,
  getClients: () => Set<WebSocket>
): Consumer {
  const kafka = new Kafka({ clientId: 'dashboard-service', brokers });
  const consumer = kafka.consumer({ groupId });

  async function run(): Promise<void> {
    await consumer.connect();
    await consumer.subscribe({ topic: TOPIC, fromBeginning: false });

    await consumer.run({
      eachMessage: async ({ message }: EachMessagePayload) => {
        if (!message.value) return;

        let prediction: PredictionRecord;
        try {
          prediction = JSON.parse(message.value.toString()) as PredictionRecord;
        } catch {
          console.error('Failed to parse prediction.generated message');
          return;
        }

        // Invalidate Redis cache for the affected region
        await cacheSet(`region:${prediction.region_id}`, '', 1);
        await cacheSet('regions:all', '', 1);
        await cacheSet(`regions:${prediction.disaster_type}`, '', 1);

        // Broadcast to all connected WebSocket clients
        const event = JSON.stringify({ type: 'prediction.generated', payload: prediction });
        for (const ws of getClients()) {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(event);
          }
        }
      },
    });
  }

  run().catch((err) => {
    console.error('Dashboard Kafka consumer error:', err);
  });

  return consumer;
}
