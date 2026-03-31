/**
 * Alert message templates for supported languages.
 * Placeholders: {disaster_type}, {risk_level}, {time_to_impact_h}
 */

export interface LanguageTemplates {
  high_risk_message: string;
  medium_risk_message: string;
  recommended_action_high: string;
  recommended_action_medium: string;
  time_to_impact: string;
}

export const translations: Record<string, LanguageTemplates> = {
  en: {
    high_risk_message:
      '[HIGH RISK] {disaster_type} alert for your region. Risk level: {risk_level}.',
    medium_risk_message:
      '[MEDIUM RISK] {disaster_type} alert for your region. Risk level: {risk_level}.',
    recommended_action_high:
      'Evacuate immediately and follow official guidance.',
    recommended_action_medium:
      'Stay alert, monitor official channels, and prepare an emergency kit.',
    time_to_impact:
      'Estimated time to impact: {time_to_impact_h}h.',
  },

  es: {
    high_risk_message:
      '[RIESGO ALTO] Alerta de {disaster_type} para su región. Nivel de riesgo: {risk_level}.',
    medium_risk_message:
      '[RIESGO MEDIO] Alerta de {disaster_type} para su región. Nivel de riesgo: {risk_level}.',
    recommended_action_high:
      'Evacúe inmediatamente y siga las instrucciones oficiales.',
    recommended_action_medium:
      'Manténgase alerta, monitoree los canales oficiales y prepare un kit de emergencia.',
    time_to_impact:
      'Tiempo estimado hasta el impacto: {time_to_impact_h}h.',
  },

  fr: {
    high_risk_message:
      '[RISQUE ÉLEVÉ] Alerte {disaster_type} pour votre région. Niveau de risque : {risk_level}.',
    medium_risk_message:
      '[RISQUE MOYEN] Alerte {disaster_type} pour votre région. Niveau de risque : {risk_level}.',
    recommended_action_high:
      'Évacuez immédiatement et suivez les consignes officielles.',
    recommended_action_medium:
      'Restez vigilant, surveillez les canaux officiels et préparez un kit d\'urgence.',
    time_to_impact:
      'Temps estimé avant l\'impact : {time_to_impact_h}h.',
  },

  hi: {
    high_risk_message:
      '[उच्च जोखिम] आपके क्षेत्र के लिए {disaster_type} चेतावनी। जोखिम स्तर: {risk_level}।',
    medium_risk_message:
      '[मध्यम जोखिम] आपके क्षेत्र के लिए {disaster_type} चेतावनी। जोखिम स्तर: {risk_level}।',
    recommended_action_high:
      'तुरंत निकासी करें और आधिकारिक निर्देशों का पालन करें।',
    recommended_action_medium:
      'सतर्क रहें, आधिकारिक चैनलों की निगरानी करें और आपातकालीन किट तैयार रखें।',
    time_to_impact:
      'प्रभाव तक अनुमानित समय: {time_to_impact_h} घंटे।',
  },

  ar: {
    high_risk_message:
      '[خطر مرتفع] تحذير من {disaster_type} لمنطقتك. مستوى الخطر: {risk_level}.',
    medium_risk_message:
      '[خطر متوسط] تحذير من {disaster_type} لمنطقتك. مستوى الخطر: {risk_level}.',
    recommended_action_high:
      'أخلِ المنطقة فوراً واتبع التعليمات الرسمية.',
    recommended_action_medium:
      'ابقَ يقظاً وراقب القنوات الرسمية وجهّز حقيبة الطوارئ.',
    time_to_impact:
      'الوقت المقدر حتى التأثير: {time_to_impact_h} ساعة.',
  },
};
