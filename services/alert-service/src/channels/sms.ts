import twilio from 'twilio';

const accountSid = process.env.TWILIO_ACCOUNT_SID ?? '';
const authToken = process.env.TWILIO_AUTH_TOKEN ?? '';
const fromNumber = process.env.TWILIO_FROM_NUMBER ?? '';

let client: ReturnType<typeof twilio> | null = null;

function getClient(): ReturnType<typeof twilio> {
  if (!client) {
    client = twilio(accountSid, authToken);
  }
  return client;
}

export async function sendSms(
  phoneNumber: string,
  message: string
): Promise<'sent' | 'failed'> {
  try {
    await getClient().messages.create({
      body: message,
      from: fromNumber,
      to: phoneNumber,
    });
    return 'sent';
  } catch (err) {
    console.error(`SMS send failed to ${phoneNumber}:`, err);
    return 'failed';
  }
}
