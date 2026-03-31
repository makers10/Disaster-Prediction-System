import { Router, Request, Response } from 'express';
import { getLatestPredictions, getRegionIds } from './knowledgeBase';
import { classifyQuery } from './intentClassifier';
import { generateResponse } from './responseGenerator';

const router = Router();

/**
 * POST /api/chat
 * Body: { query: string, region_id?: string }
 */
router.post('/chat', async (req: Request, res: Response): Promise<void> => {
  const { query, region_id: bodyRegionId } = req.body as {
    query?: string;
    region_id?: string;
  };

  if (!query || typeof query !== 'string' || query.trim() === '') {
    res.status(400).json({ error: 'query is required and must be a non-empty string' });
    return;
  }

  try {
    // Fetch known regions for intent classification (with 4.5s timeout)
    const knownRegions = await Promise.race([
      getRegionIds(),
      new Promise<string[]>((_, reject) =>
        setTimeout(() => reject(new Error('DB timeout')), 4500)
      ),
    ]);

    // Classify intent and extract region/disaster type
    const classified = classifyQuery(query, knownRegions);

    // Override region_id from body if provided
    const resolvedRegionId = bodyRegionId ?? classified.region_id;

    // If no region could be determined, return location clarification
    if (!resolvedRegionId) {
      const response = generateResponse('location_clarification', [], {
        intent: 'location_clarification',
        region_id: null,
        disaster_type: classified.disaster_type,
      });
      res.json({ response, intent: 'location_clarification', region_id: null, predictions: [] });
      return;
    }

    // Fetch predictions for the resolved region (with 4.5s timeout)
    const predictions = await Promise.race([
      getLatestPredictions(resolvedRegionId),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('DB timeout')), 4500)
      ),
    ]);

    const response = generateResponse(classified.intent, predictions, {
      ...classified,
      region_id: resolvedRegionId,
    });

    res.json({
      response,
      intent: classified.intent,
      region_id: resolvedRegionId,
      predictions,
    });
  } catch (err) {
    console.error('Chat error:', err);
    res.status(500).json({ error: 'Internal server error. Please try again.' });
  }
});

export default router;
