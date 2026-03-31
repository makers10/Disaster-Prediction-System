/**
 * S3-compatible object storage for crowd report images.
 * Falls back to local /tmp storage if S3 is not configured.
 */
import { v4 as uuidv4 } from 'uuid';
import path from 'path';
import fs from 'fs';

const S3_BUCKET = process.env['S3_BUCKET'] ?? '';
const S3_ENDPOINT = process.env['S3_ENDPOINT'] ?? '';
const S3_REGION = process.env['S3_REGION'] ?? 'us-east-1';

let s3Client: unknown = null;

function getS3() {
  if (!s3Client && S3_BUCKET) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const { S3Client } = require('@aws-sdk/client-s3');
      s3Client = new S3Client({
        region: S3_REGION,
        ...(S3_ENDPOINT ? { endpoint: S3_ENDPOINT } : {}),
      });
    } catch {
      s3Client = null;
    }
  }
  return s3Client;
}

export async function uploadImage(buffer: Buffer, originalName: string): Promise<string> {
  const ext = path.extname(originalName) || '.jpg';
  const key = `crowd-reports/${uuidv4()}${ext}`;

  const s3 = getS3();
  if (s3 && S3_BUCKET) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const { PutObjectCommand } = require('@aws-sdk/client-s3');
      await (s3 as { send: (cmd: unknown) => Promise<void> }).send(new PutObjectCommand({
        Bucket: S3_BUCKET,
        Key: key,
        Body: buffer,
        ContentType: 'image/jpeg',
      }));
      return `s3://${S3_BUCKET}/${key}`;
    } catch (err) {
      console.error('S3 upload failed, falling back to local storage:', err);
    }
  }

  // Local fallback
  const localDir = path.join('/tmp', 'crowd-reports');
  fs.mkdirSync(localDir, { recursive: true });
  const localPath = path.join(localDir, path.basename(key));
  fs.writeFileSync(localPath, buffer);
  return `file://${localPath}`;
}
