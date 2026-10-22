import test from 'node:test';
import assert from 'node:assert/strict';
import { nextQuestion, deriveState, createReport } from '../src/engine.js';
import { texts } from '../src/questions.js';

const a = (id, value, text) => (text ? { id, value, text } : { id, value });

function run(values, lang = 'ru') {
  const answers = [];
  for (const value of values) {
    const question = nextQuestion(answers, 'express', lang);
    assert.ok(question, 'route ended before supplied answers');
    answers.push(typeof value === 'object' ? { id: question.id, ...value } : a(question.id, value));
  }
  return answers;
}

// Любой маршрут заканчивается необязательным контактом, после него вопросов нет.
function finish(answers, contact = '', lang = 'ru') {
  const question = nextQuestion(answers, 'express', lang);
  assert.equal(question?.id, 'contact');
  const done = [...answers, a('contact', contact)];
  assert.equal(nextQuestion(done, 'express', lang), null);
  return done;
}

test('all personas reach a relevant situation question in both languages', () => {
  for (const lang of ['ru', 'en']) {
    for (const persona of ['solo', 'ai', 'team', 'enterprise', 'other']) {
      const question = nextQuestion([a('persona', persona)], 'express', lang);
      assert.equal(question.id, 'situation');
      assert.ok(question.options.length >= 5);
    }
  }
});

test('"Other" persona with free text does not break the survey', () => {
  const answers = [a('persona', 'other', 'Фрилансер')];
  const question = nextQuestion(answers);
  assert.equal(question.id, 'situation');
  assert.deepEqual(question.options.slice(0, 3).map(([key]) => key), texts.ru.situations.other.map(([key]) => key));
  const report = createReport(answers, 'id');
  assert.equal(report.persona, 'other');
  assert.equal(report.personaText, 'Фрилансер');
  assert.equal(report.transcript[0].displayAnswer, 'Другое: Фрилансер');
});

test('free-text persona saved by the old version is treated as "Other"', () => {
  for (const legacy of ['Другое', 'Фрилансер']) {
    const question = nextQuestion([a('persona', legacy)]);
    assert.equal(question.id, 'situation');
    assert.equal(deriveState([a('persona', legacy)]).persona, 'other');
  }
});

test('control and no-memory branches finish with the contact step, without invented event', () => {
  const control = finish(run(['solo', 'none', 'no_need']));
  assert.equal(deriveState(control).validationStatus, 'no_reported_problem');
  const noMemory = finish(run(['ai', 'transfer', 'no_memory']));
  assert.equal(deriveState(noMemory).validationStatus, 'insufficient_evidence');
});

test('facts in text skip repeated action and time questions', () => {
  const answers = run(['solo', 'lost_context', 'week', 'Вчера удалил чат, восстанавливал вручную 4 часа и теперь сохраняю заметки', 'time']);
  assert.equal(nextQuestion(answers).id, 'outcome');
  assert.equal(deriveState(answers).timeCost, 'stated_in_event');
});

test('English free text is understood the same way', () => {
  const answers = run(['solo', 'lost_context', 'week', 'Lost the chat yesterday, rebuilt it by hand in 4 hours, now I keep notes', 'time'], 'en');
  assert.equal(nextQuestion(answers, 'express', 'en').id, 'outcome');
  assert.equal(deriveState(answers).timeCost, 'stated_in_event');
});

test('express route stays within ten questions and one clarification', () => {
  const values = ['enterprise', 'audit', 'month', 'Во время проверки не нашли решение', 'time', 'hours', 'manual', 'git', 'accurate'];
  const answers = finish(run(values));
  assert.ok(answers.filter(({ id }) => id !== 'contact').length <= 10);
  assert.equal(answers.filter(({ id }) => id === 'timeCost').length, 1);
});

test('report keeps verbatim answer, contact, and backtracking can replay the route', () => {
  const answers = run(['team', 'outdated', 'quarter', 'В прошлом проекте инструкция устарела', 'error']);
  assert.equal(nextQuestion(answers).id, 'action');
  answers.pop();
  assert.equal(nextQuestion(answers).id, 'consequence');
  const report = createReport(answers, 'test-id');
  assert.equal(report.transcript[3].answer, 'В прошлом проекте инструкция устарела');
  assert.equal(report.validationStatus, 'reported_event');
  const withContact = createReport([...answers, a('contact', ' @emil ')], 'test-id', 'express', 'en');
  assert.equal(withContact.contact, '@emil');
  assert.equal(withContact.lang, 'en');
});

test('skipped text answers are empty in the report', () => {
  const answers = run(['solo', 'lost_context', 'week', '']);
  assert.equal(deriveState(answers).validationStatus, 'insufficient_evidence');
  assert.equal(createReport(answers, 'id').summary.event, null);
});

test('"Other" with text on a later question keeps the key and the text', () => {
  const answers = run(['team', { value: 'other', text: 'Онбординг новичка' }]);
  assert.equal(deriveState(answers).situation, 'other');
  assert.equal(deriveState(answers).situationText, 'Онбординг новичка');
  assert.equal(nextQuestion(answers).id, 'recency');
});

test('eight representative paths have no loops in both languages', () => {
  const cases = [
    ['solo', 'lost_context', 'week', 'Потерял настройки', 'rework', 'manual', 'notes', 'continue'],
    ['ai', 'transfer', 'month', 'Сменил агента и перенёс контекст вручную', 'time', 'minutes', 'notes', 'share'],
    ['team', 'outdated', 'quarter', 'Инструкция была старой', 'error', 'help', 'git', 'accurate'],
    ['enterprise', 'audit', 'week', 'На аудите не нашли данные', 'time', 'day', 'manual', 'automation', 'finish'],
    ['solo', 'none', 'no_need'],
    ['ai', 'conflict', 'older', 'Было что-то не то', 'none', 'nothing', 'nothing', 'accurate'],
    ['team', 'handoff', 'week', 'Передал задачу, восстановил контекст и потратил 2 часа на объяснение, теперь храню заметки', 'time', 'share'],
    ['enterprise', 'wrong_answer', 'no_memory'],
  ];
  for (const lang of ['ru', 'en']) {
    for (const values of cases) {
      const answers = finish(run(values, lang), '', lang);
      assert.equal(new Set(answers.map(({ id }) => id)).size, answers.length);
      assert.ok(answers.length <= 11);
    }
  }
});

test('both languages offer the same option keys', () => {
  const keys = (options) => options.map(([key]) => key);
  assert.deepEqual(keys(texts.en.personas), keys(texts.ru.personas));
  for (const persona of Object.keys(texts.ru.situations)) {
    assert.deepEqual(keys(texts.en.situations[persona]), keys(texts.ru.situations[persona]));
  }
  for (const group of Object.keys(texts.ru.common)) {
    assert.deepEqual(keys(texts.en.common[group]), keys(texts.ru.common[group]));
  }
  assert.deepEqual(Object.keys(texts.en.prompts), Object.keys(texts.ru.prompts));
  assert.deepEqual(Object.keys(texts.en.ui), Object.keys(texts.ru.ui));
});
