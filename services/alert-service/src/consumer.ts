import { Kafka, Consumer, EachMessagePayload } from 'kafkajs';
import { PredictionRecord } from '../../../shared/types/index';
import { getUsersForRegion } from './userStore';
import { dispatch, AlertPublisher } from './dispatcher';

const TOPIC_PREDICTION = 'prediction.generated';

export function createConsumer(
  brokers: string[],
  groupId: string,
  publishAlert: AlertPublisher
): Consumer {
  const kafka = new Kafka({ clientId: 'alert-service', brokers });
  const consumer = kafka.consumer({ groupId });

  async function run(): Promise<void> {
    await consumer.connect();
    await consumer.subscribe({ topic: TOPIC_PREDICTION, fromBeginning: false });

    await consumer.run({
      eachMessage: async ({ message }: EachMessagePayload) => {
        if (!message.value) return;

        let prediction: PredictionRecord;
        try {
          prediction = JSON.parse(message.value.toString()) as PredictionRecord;
        } catch (err) {
          console.error('Failed to parse prediction message:', err);
          return;
        }

        // Only dispatch for Medium or High risk
        if (prediction.risk_level === 'Low') {
          return;
        }

        try {
          const users = await getUsersForRegion(prediction.region_id);
          await dispatch(prediction, users, publishAlert);
        } catch (err) {
          console.error(
            `Error dispatching alerts for prediction ${prediction.prediction_id}:`,
            err
          );
        }
      },
    });
  }

  // Start the consumer loop (non-blocking from caller's perspective)
  run().catch((err) => {
    console.error('Consumer run error:', err);
    process.exit(1);
  });

  return consumer;
}
