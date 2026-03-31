import { Pool } from 'pg';
import { UserProfile } from '../../../shared/types/index';

let pool: Pool | null = null;

export function initPool(connectionString: string): void {
  pool = new Pool({ connectionString });
}

function getPool(): Pool {
  if (!pool) {
    throw new Error('PostgreSQL pool not initialized. Call initPool() first.');
  }
  return pool;
}

/**
 * Returns all users whose region_ids array contains the given regionId.
 * Supports both home region and any additionally subscribed regions.
 */
export async function getUsersForRegion(regionId: string): Promise<UserProfile[]> {
  const result = await getPool().query<UserProfile>(
    `SELECT
       user_id,
       phone_number,
       push_token,
       language_code,
       region_ids,
       is_infrastructure_operator,
       infrastructure_ids,
       notification_channels
     FROM users
     WHERE $1 = ANY(region_ids)`,
    [regionId]
  );
  return result.rows;
}

export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}
