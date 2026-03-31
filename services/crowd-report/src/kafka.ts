import { Kafka, Producer } from 'kafkajs';

let producer: Producer | null = null;

export async function initProducer(brokers: string[]): Promise<void> {
  const kafka = new Kafka({ clientId: 'crowd-report-service', brokers });
  producer = kafka.producer();
  await producer.connect();
}

export async function publishEvent(topic: string, key: string, value: unknown): Promise<void> {
  if (!producer) throw new Error('Kafka producer not initialized.');
  await producer.send({
    topic,
    messages: [{ key, value: JSON.stringify(value) }],
  });
}

export async function closeProducer(): Promise<void> {
  if (producer) { await producer.disconnect(); producer = null; }
}
