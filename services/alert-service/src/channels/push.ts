import admin from 'firebase-admin';

let initialized = false;

function getApp(): admin.app.App {
  if (!initialized) {
    admin.initializeApp({
      credential: admin.credential.cert({
        projectId: process.env.FIREBASE_PROJECT_ID,
        clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
        privateKey: (process.env.FIREBASE_PRIVATE_KEY ?? '').replace(/\\n/g, '\n'),
      }),
    });
    initialized = true;
  }
  return admin.app();
}

export async function sendPush(
  pushToken: string,
  title: string,
  body: string
): Promise<'sent' | 'failed'> {
  try {
    await getApp().messaging().send({
      token: pushToken,
      notification: { title, body },
    });
    return 'sent';
  } catch (err) {
    console.error(`Push send failed to token ${pushToken}:`, err);
    return 'failed';
  }
}
