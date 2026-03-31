export type Intent =
  | 'risk_query'
  | 'safety_recommendation'
  | 'precautionary_actions'
  | 'location_clarification';

export interface ClassifiedQuery {
  intent: Intent;
  region_id: string | null;
  disaster_type: string | null;
}

const DISASTER_TYPES = ['flood', 'heatwave', 'drought', 'landslide', 'cyclone'];

/**
 * Classifies a natural language query into an intent, and extracts
 * region_id and disaster_type if present.
 */
export function classifyQuery(query: string, knownRegions: string[]): ClassifiedQuery {
  const lower = query.toLowerCase();

  // Determine intent
  let intent: Intent;
  if (/safe|travel|go to/.test(lower)) {
    intent = 'safety_recommendation';
  } else if (/precaution|prepare|what should|what to do/.test(lower)) {
    intent = 'precautionary_actions';
  } else {
    // Default to risk_query (also matches flood/heatwave/drought/etc. keywords)
    intent = 'risk_query';
  }

  // Extract region_id: check if any known region appears in the query (case-insensitive)
  const region_id =
    knownRegions.find((r) => lower.includes(r.toLowerCase())) ?? null;

  // Extract disaster_type: check if any of the 5 disaster type words appear
  const disaster_type = DISASTER_TYPES.find((d) => lower.includes(d)) ?? null;

  return { intent, region_id, disaster_type };
}
