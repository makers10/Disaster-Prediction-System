import { v4 as uuidv4 } from 'uuid';
import { PredictionRecord, UserProfile, AlertRecord } from '../../../shared/types/index';
import { sendSms } from './channels/sms';
import { sendPush } from './channels/push';

// SLA thresholds in milliseconds
const HIGH_RISK_SLA_MS = 5 * 60 * 1000;   // 5 minutes
const MEDIUM_RISK_SLA_MS = 15 * 60 * 1000; // 15 minutes

const SMS_MAX_RETRIES = 3;
const SMS_RETRY_DELAY_MS = 1000;

export type AlertPublisher = (record: AlertRecord) => Promise<void>;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Renders a human-readable alert message for the given prediction.
 */
function renderMessage(prediction: PredictionRecord): string {
  const action = recommendedAction(prediction);
  return (
    `[${prediction.risk_level.toUpperCase()} RISK] ${prediction.disaster_type} alert for your region. ` +
    `Risk level: ${prediction.risk_level}. ` +
    (prediction.time_to_impact_h != null
      ? `Estimated time to impact: ${prediction.time_to_impact_h}h. `
      : '') +
    `Recommended action: ${action}`
  );
}

function recommendedAction(prediction: PredictionRecord): string {
  if (prediction.risk_level === 'High') {
    return 'Evacuate immediately and follow official guidance.';
  }
  return 'Stay alert, monitor official channels, and prepare an emergency kit.';
}

/**
 * Sends an SMS with up to SMS_MAX_RETRIES retries on failure.
 * Returns the delivery status and actual retry count used.
 */
async function sendSmsWithRetry(
  phoneNumber: string,
  message: string,
  userId: string,
  alertId: string
): Promise<{ status: 'sent' | 'failed'; retryCount: number }> {
  let retryCount = 0;
  let status: 'sent' | 'failed' = 'failed';

  for (let attempt = 0; attempt <= SMS_MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      await sleep(SMS_RETRY_DELAY_MS);
      retryCount = attempt;
    }
    status = await sendSms(phoneNumber, message);
    if (status === 'sent') {
      return { status, retryCount };
    }
  }

  console.error(
    `SMS final failure after ${SMS_MAX_RETRIES} retries — user_id: ${userId}, alert_id: ${alertId}`
  );
  return { status: 'failed', retryCount };
}

/**
 * Checks whether the dispatch is within the SLA window for the given risk level.
 * Logs a warning if the SLA has been breached.
 */
function checkSla(prediction: PredictionRecord, alertId: string): void {
  const generatedAt = new Date(prediction.generated_at).getTime();
  const now = Date.now();
  const elapsed = now - generatedAt;
  const sla = prediction.risk_level === 'High' ? HIGH_RISK_SLA_MS : MEDIUM_RISK_SLA_MS;

  if (elapsed > sla) {
    console.warn(
      `SLA BREACH — alert_id: ${alertId}, prediction_id: ${prediction.prediction_id}, ` +
      `risk_level: ${prediction.risk_level}, elapsed: ${Math.round(elapsed / 1000)}s, ` +
      `sla: ${sla / 1000}s`
    );
  }
}

/**
 * Dispatches alerts for a prediction to all qualifying users.
 * Task 6.6: filters users to only those whose region_ids includes the prediction's region_id.
 */
export async function dispatch(
  prediction: PredictionRecord,
  users: UserProfile[],
  publishAlert: AlertPublisher
): Promise<void> {
  // 6.6 — filter users by region
  const eligibleUsers = users.filter((u) =>
    u.region_ids.includes(prediction.region_id)
  );

  const message = renderMessage(prediction);
  const title = `${prediction.risk_level} Risk: ${prediction.disaster_type}`;

  for (const user of eligibleUsers) {
    for (const channel of user.notification_channels) {
      if (channel === 'voice') {
        // Voice not implemented in Phase 1 — skip
        continue;
      }

      const alertId = uuidv4();
      checkSla(prediction, alertId);

      let deliveryStatus: 'sent' | 'failed' = 'failed';
      let retryCount = 0;

      if (channel === 'sms') {
        if (!user.phone_number) {
          console.warn(`User ${user.user_id} has no phone_number; skipping SMS.`);
          continue;
        }
        const result = await sendSmsWithRetry(
          user.phone_number,
          message,
          user.user_id,
          alertId
        );
        deliveryStatus = result.status;
        retryCount = result.retryCount;
      } else if (channel === 'push') {
        if (!user.push_token) {
          console.warn(`User ${user.user_id} has no push_token; skipping push.`);
          continue;
        }
        deliveryStatus = await sendPush(user.push_token, title, message);
      }

      const alertRecord: AlertRecord = {
        alert_id: alertId,
        prediction_id: prediction.prediction_id,
        region_id: prediction.region_id,
        disaster_type: prediction.disaster_type,
        risk_level: prediction.risk_level as 'Medium' | 'High',
        time_to_impact_h: prediction.time_to_impact_h ?? 0,
        recommended_action: recommendedAction(prediction),
        evacuation_route_id: null,
        language_code: user.language_code,
        channel,
        dispatched_at: new Date().toISOString(),
        delivery_status: deliveryStatus,
        retry_count: retryCount,
      };

      await publishAlert(alertRecord);
    }
  }
}
