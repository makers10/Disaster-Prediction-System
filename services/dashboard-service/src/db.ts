import { Pool } from 'pg';

let pool: Pool | null = null;

export function initPool(connectionString: string): void {
  pool = new Pool({ connectionString });
}

export function getPool(): Pool {
  if (!pool) {
    throw new Error('PostgreSQL pool not initialized. Call initPool() first.');
  }
  return pool;
}

export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}
