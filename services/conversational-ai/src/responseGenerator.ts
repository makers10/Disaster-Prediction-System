import { Intent, ClassifiedQuery } from './intentClassifier';
import { RegionPrediction } from './knowledgeBase';

const RISK_ORDER: Record<string, number> = { Low: 0, Medium: 1, High: 2 };

function highestRisk(predictions: RegionPrediction[]): RegionPrediction | null {
  if (predictions.length === 0) return null;
  return predictions.reduce((best, p) =>
    RISK_ORDER[p.risk_level] > RISK_ORDER[best.risk_level] ? p : best
  );
}

function formatTimeToImpact(h: number | null): string {
  if (h === null) return '';
  return ` Expected impact in approximately ${h} hour${h === 1 ? '' : 's'}.`;
}

function precautionMessage(prediction: RegionPrediction): string {
  const { disaster_type, risk_level } = prediction;
  if (risk_level === 'High') {
    switch (disaster_type) {
      case 'flood':
        return 'Flood precautions: Move to higher ground, avoid flood-prone areas, prepare emergency supplies, follow evacuation orders.';
      case 'heatwave':
        return 'Heatwave precautions: Stay indoors during peak hours, drink plenty of water, check on vulnerable neighbours.';
      case 'drought':
        return 'Drought precautions: Conserve water, avoid open burning, monitor water supply levels.';
      case 'landslide':
        return 'Landslide precautions: Avoid steep slopes, monitor for unusual sounds, be ready to evacuate.';
      case 'cyclone':
        return 'Cyclone precautions: Secure loose objects, stay indoors, follow evacuation orders if issued.';
    }
  }
  return 'No immediate action required. Stay informed via official channels and prepare an emergency kit.';
}

/**
 * Generates a plain-language response based on intent, predictions, and the original query.
 */
export function generateResponse(
  intent: Intent,
  predictions: RegionPrediction[],
  classified: ClassifiedQuery
): string {
  if (intent === 'location_clarification') {
    return "I couldn't determine your location from the query. Please specify a region (e.g., 'What is the flood risk in [region-name]?')";
  }

  if (predictions.length === 0) {
    return "I don't have current prediction data for that region.";
  }

  if (intent === 'risk_query') {
    // Filter by disaster_type if specified
    const relevant = classified.disaster_type
      ? predictions.filter((p) => p.disaster_type === classified.disaster_type)
      : predictions;

    if (relevant.length === 0) {
      return `I don't have current prediction data for ${classified.disaster_type ?? 'that disaster type'} in that region.`;
    }

    const regionId = relevant[0].region_id;
    const lines = relevant.map((p) => {
      const tti = p.time_to_impact_h !== null ? formatTimeToImpact(p.time_to_impact_h) : '';
      return `${p.disaster_type} is ${p.risk_level} (${p.probability_pct}% probability).${tti}`;
    });

    return `Current risk for ${regionId}: ${lines.join(' ')}`;
  }

  if (intent === 'safety_recommendation') {
    const top = highestRisk(predictions);
    if (!top) return "I don't have current prediction data for that region.";

    if (top.risk_level === 'High') {
      return `It is NOT safe. There is a ${top.disaster_type} High risk alert (${top.probability_pct}%). Avoid travel and follow official guidance.`;
    }
    if (top.risk_level === 'Medium') {
      return `Exercise caution. There is a ${top.disaster_type} Medium risk (${top.probability_pct}%). Monitor official channels before travelling.`;
    }
    return 'Current risk levels are Low. Travel appears safe, but always check official advisories.';
  }

  if (intent === 'precautionary_actions') {
    const top = highestRisk(predictions);
    if (!top) return "I don't have current prediction data for that region.";
    return precautionMessage(top);
  }

  return "I don't have current prediction data for that region.";
}
