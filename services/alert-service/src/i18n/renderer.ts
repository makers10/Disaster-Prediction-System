import { PredictionRecord } from '../../../../shared/types/index';
import { translations, LanguageTemplates } from './translations';

const DEFAULT_LANGUAGE = process.env.DEFAULT_LANGUAGE ?? 'en';

function resolveLang(languageCode: string | null | undefined): LanguageTemplates {
  const code = languageCode?.trim() || DEFAULT_LANGUAGE;
  // Try exact match, then base language (e.g. "en-GB" → "en"), then fallback to 'en'
  return (
    translations[code] ??
    translations[code.split('-')[0]] ??
    translations['en']
  );
}

function replacePlaceholders(
  template: string,
  vars: Record<string, string>
): string {
  return template.replace(/\{(\w+)\}/g, (_, key) => vars[key] ?? '');
}

/**
 * Renders a localised alert message for the given prediction.
 * Falls back to the operator default language (DEFAULT_LANGUAGE env var, default 'en')
 * if the requested language code is not found in the translations map.
 */
export function renderAlertMessage(
  prediction: PredictionRecord,
  languageCode: string | null | undefined
): { title: string; body: string; recommendedAction: string } {
  const lang = resolveLang(languageCode);

  const vars: Record<string, string> = {
    disaster_type: prediction.disaster_type,
    risk_level: prediction.risk_level,
    time_to_impact_h: prediction.time_to_impact_h?.toString() ?? '',
  };

  const bodyTemplate =
    prediction.risk_level === 'High' ? lang.high_risk_message : lang.medium_risk_message;

  let body = replacePlaceholders(bodyTemplate, vars);

  if (prediction.time_to_impact_h != null) {
    body += ' ' + replacePlaceholders(lang.time_to_impact, vars);
  }

  const recommendedAction =
    prediction.risk_level === 'High'
      ? lang.recommended_action_high
      : lang.recommended_action_medium;

  const title = `${prediction.risk_level} Risk: ${prediction.disaster_type}`;

  return { title, body, recommendedAction };
}
