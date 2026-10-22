import { bundle, texts, questionMeta } from './questions.js';

const label = (options, value) => options.find(([key]) => key === value)?.[1] ?? value;
const find = (answers, id) => answers.find((item) => item.id === id);
const answerValue = (answers, id) => find(answers, id)?.value;
// Старые версии сохраняли пропуск текстового вопроса этой строкой, новые — пустой строкой.
const LEGACY_SKIP = 'Не помню подробности';

export function deriveState(answers) {
  const value = (id) => answerValue(answers, id);
  const rawPersona = value('persona') ?? null;
  // Неизвестная персона (например, свободный текст из старой версии) идёт по ветке «Другое».
  const persona = rawPersona && !texts.ru.situations[rawPersona] ? 'other' : rawPersona;
  const situation = value('situation') ?? null;
  const recency = value('recency') ?? null;
  const rawEvent = value('event');
  const event = rawEvent === LEGACY_SKIP ? '' : rawEvent?.trim() ?? '';
  const consequence = value('consequence') ?? null;
  const action = value('action') ?? null;
  const prevention = value('prevention') ?? value('control') ?? null;
  const outcome = value('outcome') ?? null;
  const timeCost = value('timeCost') ?? null;
  const contact = value('contact')?.trim() || null;
  const eventTime = /(?:\b\d+(?:[.,]\d+)?\s*(?:час|минут|дн|hour|hr|minute|min|day))/iu.test(event);
  const mentionedAction = /восстанов|восстанав|перен[её]с|наш[её]л|начал заново|обратил|использовал другой|rebuil|restor|recover|redid|found|started over|asked|switched to/iu.test(event);
  const mentionedPrevention = /сохраня|храню|заметк|git|резервн|бэкап|now (?:i )?(?:keep|save|store|write)|notes|backup/iu.test(event);
  const evidence = event ? [{ source: 'respondent', text: event, questionId: 'event' }] : [];
  const unknownFields = [];
  if (!event && situation !== 'none') unknownFields.push('lastEvent');
  if (!consequence && event) unknownFields.push('consequences');
  if (!prevention && !mentionedPrevention) unknownFields.push('currentSolution');
  if (!outcome && event) unknownFields.push('expectedOutcome');
  return {
    persona, personaText: find(answers, 'persona')?.text ?? (rawPersona !== persona ? rawPersona : null),
    jobType: null, situation, situationText: find(answers, 'situation')?.text ?? null,
    lastEvent: recency, context: null, trigger: null,
    expectedOutcome: outcome, higherLevelJob: null, actualActions: action ? [action] : [],
    consequences: consequence ? [consequence] : [], timeCost: timeCost ?? (eventTime ? 'stated_in_event' : null),
    moneyCost: null, currentSolution: prevention, alternatives: [], satisfaction: null,
    value: null, ahaMoment: null, barriers: [], budgetOwner: null, evidence, contact,
    unknownFields, questionHistory: answers.map(({ id }) => id),
    validationStatus: situation === 'none' ? 'no_reported_problem' : event && recency !== 'no_memory' ? 'reported_event' : 'insufficient_evidence',
    factsInText: { eventTime, mentionedAction, mentionedPrevention },
  };
}

function descriptor(id, question, options, extra = {}) {
  return { id, question, options, ...questionMeta[id], conditions: extra.conditions ?? null,
    next: extra.next ?? null, skipIfKnown: extra.skipIfKnown ?? [], ...extra };
}

function mainQuestion(answers, mode, t) {
  const state = deriveState(answers);
  const has = (id) => answers.some((item) => item.id === id);
  const expressCount = answers.filter(({ id }) => id !== 'deep' && id !== 'contact').length;
  if (mode === 'express' && expressCount >= 10) return null;
  const q = t.prompts;
  const other = ['other', t.extra.other];
  if (!has('persona')) return descriptor('persona', q.persona, t.personas);
  if (!has('situation')) return descriptor('situation', q.situation, [
    ...t.situations[state.persona ?? 'other'], ['none', t.extra.none], other,
  ]);
  if (state.situation === 'none') {
    if (!has('control')) return descriptor('control', q.control, [
      ...t.common.prevention, other, ['no_need', t.extra.noNeed],
    ]);
    return null;
  }
  if (!has('recency')) return descriptor('recency', q.recency, t.common.recency);
  if (state.lastEvent === 'no_memory') return null;
  if (!has('event')) return descriptor('event', q.event, [], { optional: true });
  if (!has('consequence')) return descriptor('consequence', q.consequence, [...t.common.consequence, other]);
  if (state.consequences.includes('time') && !state.factsInText.eventTime && !has('timeCost')) {
    return descriptor('timeCost', q.timeCost, t.common.timeCost, { clarification: true });
  }
  if (!state.factsInText.mentionedAction && !has('action')) return descriptor('action', q.action, [...t.common.action, other]);
  if (!state.factsInText.mentionedPrevention && !has('prevention')) return descriptor('prevention', q.prevention, [...t.common.prevention, other]);
  if (!has('outcome')) return descriptor('outcome', q.outcome, [...t.common.outcome, other]);
  if (mode === 'deep' && !has('deep')) return descriptor('deep', q.deep, [], { optional: true });
  return null;
}

export function nextQuestion(answers, mode = 'express', lang = 'ru') {
  const t = bundle(lang);
  const question = mainQuestion(answers, mode, t);
  if (question) return question;
  // Последний шаг любого маршрута — необязательный контакт для интервью.
  if (!answers.some(({ id }) => id === 'contact')) return descriptor('contact', t.prompts.contact, [], { optional: true });
  return null;
}

export function createReport(answers, sessionId, mode = 'express', lang = 'ru') {
  const t = bundle(lang);
  const state = deriveState(answers);
  const situationOptions = t.situations[state.persona ?? 'other'] ?? t.situations.other;
  const other = ['other', t.extra.other];
  const optionMap = {
    persona: t.personas,
    situation: [...situationOptions, ['none', t.extra.none], other],
    control: [...t.common.prevention, other, ['no_need', t.extra.noNeed]],
    ...t.common,
  };
  const shown = ({ id, value, text }) => {
    const base = label(optionMap[id] ?? [], value);
    return text ? `${base}: ${text}` : base;
  };
  const transcript = answers.map((item) => ({
    questionId: item.id,
    answer: item.value,
    text: item.text ?? null,
    displayAnswer: shown(item),
  }));
  const summaryOf = (id) => {
    const item = find(answers, id);
    return item ? shown(item) : null;
  };
  return {
    schemaVersion: 2, sessionId, mode, lang, createdAt: new Date().toISOString(),
    ...state, factsInText: undefined, transcript,
    summary: {
      situation: summaryOf('situation'),
      event: answerValue(answers, 'event') || null,
      consequence: summaryOf('consequence'),
      currentSolution: summaryOf('prevention') ?? summaryOf('control'),
    },
  };
}
