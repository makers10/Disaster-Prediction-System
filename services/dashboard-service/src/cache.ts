import Redis from 'ioredis';

let client: Redis | null = null;

export function initRedis(url: string): void {
  client = new Redis(url);
}

export async function get(key: string): Promise<string | null> {
  if (!client) throw new Error('Redis not initialized. Call initRedis() first.');
  return client.get(key);
}

export async function set(key: string, value: string, ttlSeconds: number): Promise<void> {
  if (!client) throw new Error('Redis not initialized. Call initRedis() first.');
  await client.set(key, value, 'EX', ttlSeconds);
}

export async function close(): Promise<void> {
  if (client) {
    await client.quit();
    client = null;
  }
}
