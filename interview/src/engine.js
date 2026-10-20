import { personas, situations, common, questionMeta } from './questions.js';

const label = (options, value) => options.find(([key]) => key === value)?.[1] ?? value;
const answerValue = (answers, id) => answers.find((item) => item.id === id)?.value;

export function deriveState(answers) {
  const value = (id) => answerValue(answers, id);
  const persona = value('persona') ?? null;
  const situation = value('situation') ?? null;
  const recency = value('recency') ?? null;
  const event = value('event') === 'Не помню подробности' ? '' : value('event')?.trim() ?? '';
  const consequence = value('consequence') ?? null;
  const action = value('action') ?? null;
  const prevention = value('prevention') ?? value('control') ?? null;
  const outcome = value('outcome') ?? null;
  const timeCost = value('timeCost') ?? null;
  const eventTime = /(?:\b\d+(?:[.,]\d+)?\s*(?:час|минут|дн|hour|minute|day))/iu.test(event);
  const mentionedAction = /восстанов|восстанав|перен[её]с|наш[её]л|начал заново|обратил|использовал другой/iu.test(event);
  const mentionedPrevention = /сохраня|храню|заметк|git|резервн|бэкап/iu.test(event);
  const evidence = event ? [{ source: 'respondent', text: event, questionId: 'event' }] : [];
  const unknownFields = [];
  if (!event && situation !== 'none') unknownFields.push('lastEvent');
  if (!consequence && event) unknownFields.push('consequences');
  if (!prevention && !mentionedPrevention) unknownFields.push('currentSolution');
  if (!outcome && event) unknownFields.push('expectedOutcome');
  return {
    persona, jobType: null, situation, lastEvent: recency, context: null, trigger: null,
    expectedOutcome: outcome, higherLevelJob: null, actualActions: action ? [action] : [],
    consequences: consequence ? [consequence] : [], timeCost: timeCost ?? (eventTime ? 'stated_in_event' : null),
    moneyCost: null, currentSolution: prevention, alternatives: [], satisfaction: null,
    value: null, ahaMoment: null, barriers: [], budgetOwner: null, evidence,
    unknownFields, questionHistory: answers.map(({ id }) => id),
    validationStatus: situation === 'none' ? 'no_reported_problem' : event && recency !== 'no_memory' ? 'reported_event' : 'insufficient_evidence',
    factsInText: { eventTime, mentionedAction, mentionedPrevention },
  };
}

function descriptor(id, question, options, extra = {}) {
  return { id, question, options, ...questionMeta[id], conditions: extra.conditions ?? null,
    next: extra.next ?? null, skipIfKnown: extra.skipIfKnown ?? [], ...extra };
}

export function nextQuestion(answers, mode = 'express') {
  const state = deriveState(answers);
  const has = (id) => answers.some((item) => item.id === id);
  const expressCount = answers.filter(({ id }) => id !== 'deep').length;
  if (mode === 'express' && expressCount >= 10) return null;
  if (!has('persona')) return descriptor('persona', 'Как вы обычно работаете над проектами?', personas);
  if (!has('situation')) return descriptor('situation', 'Какая из этих ситуаций происходила с вами за последнее время?', [
    ...situations[state.persona ?? 'other'], ['none', 'Ничего подобного не происходило'], ['other', 'Другое'],
  ]);
  if (state.situation === 'none') {
    if (!has('control')) return descriptor('control', 'Как вы сейчас сохраняете важный контекст работы?', [
      ...common.prevention, ['other', 'Другое'], ['no_need', 'Пока не возникало такой потребности'],
    ]);
    return null;
  }
  if (!has('recency')) return descriptor('recency', 'Когда последний раз это произошло?', common.recency);
  if (state.lastEvent === 'no_memory') return null;
  if (!has('event')) return descriptor('event', 'Что случилось в тот раз? Опишите коротко конкретный случай.', [], { optional: true });
  if (!has('consequence')) return descriptor('consequence', 'Как это повлияло на вашу работу?', [...common.consequence, ['other', 'Другое']]);
  if (state.consequences.includes('time') && !state.factsInText.eventTime && !has('timeCost')) {
    return descriptor('timeCost', 'Сколько времени примерно ушло дополнительно?', common.timeCost, { clarification: true });
  }
  if (!state.factsInText.mentionedAction && !has('action')) return descriptor('action', 'Что вы тогда сделали?', [...common.action, ['other', 'Другое']]);
  if (!state.factsInText.mentionedPrevention && !has('prevention')) return descriptor('prevention', 'Как вы сейчас стараетесь избежать повторения?', [...common.prevention, ['other', 'Другое']]);
  if (!has('outcome')) return descriptor('outcome', 'Какого результата вы тогда пытались добиться?', [...common.outcome, ['other', 'Другое']]);
  if (mode === 'deep' && !has('deep')) return descriptor('deep', 'Если хотите, расскажите, почему этот результат был важен и какие решения вы пробовали.', [], { optional: true });
  return null;
}

export function createReport(answers, sessionId, mode = 'express') {
  const state = deriveState(answers);
  const situationOptions = situations[state.persona ?? 'other'] ?? situations.other;
  const optionMap = { persona: personas, situation: [...situationOptions, ['none', 'Ничего подобного']], ...common };
  const transcript = answers.map(({ id, value }) => ({
    questionId: id,
    answer: value,
    displayAnswer: label(optionMap[id] ?? [], value),
  }));
  return {
    schemaVersion: 1, sessionId, mode, createdAt: new Date().toISOString(),
    ...state, factsInText: undefined, transcript,
    summary: {
      situation: label(optionMap.situation, state.situation),
      event: answerValue(answers, 'event') ?? null,
      consequence: label(common.consequence, answerValue(answers, 'consequence') ?? null),
      currentSolution: label(common.prevention, answerValue(answers, 'prevention') ?? null),
    },
  };
}
