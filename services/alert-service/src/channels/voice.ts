import twilio from 'twilio';
import { sendSms } from './sms';

const accountSid = process.env.TWILIO_ACCOUNT_SID ?? '';
const authToken = process.env.TWILIO_AUTH_TOKEN ?? '';
const fromNumber = process.env.TWILIO_FROM_NUMBER ?? '';
const twimlAppSid = process.env.TWILIO_TWIML_APP_SID ?? '';

let client: ReturnType<typeof twilio> | null = null;

function getClient(): ReturnType<typeof twilio> {
  if (!client) {
    client = twilio(accountSid, authToken);
  }
  return client;
}

/**
 * Builds a TwiML response that reads the message aloud using the <Say> verb.
 */
function buildTwiml(message: string): string {
  // Escape XML special characters to avoid malformed TwiML
  const escaped = message
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
  return `<?xml version="1.0" encoding="UTF-8"?><Response><Say>${escaped}</Say></Response>`;
}

/**
 * Places an automated voice call to phoneNumber that reads message aloud.
 * Falls back to SMS if the voice call fails.
 * Returns 'sent' on success (voice or SMS fallback), 'failed' if both fail.
 */
export async function sendVoice(
  phoneNumber: string,
  message: string
): Promise<'sent' | 'failed'> {
  try {
    await getClient().calls.create({
      twiml: buildTwiml(message),
      to: phoneNumber,
      from: fromNumber,
      ...(twimlAppSid ? { applicationSid: twimlAppSid } : {}),
    });
    return 'sent';
  } catch (err) {
    console.error(`Voice call failed to ${phoneNumber}:`, err);
    console.warn(`Voice failed for ${phoneNumber}, falling back to SMS`);
    const smsFallback = await sendSms(phoneNumber, message);
    if (smsFallback === 'sent') {
      console.log(`SMS fallback succeeded for ${phoneNumber}`);
      return 'sent';
    }
    console.error(`SMS fallback also failed for ${phoneNumber}`);
    return 'failed';
  }
}
