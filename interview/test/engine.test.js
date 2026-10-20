import test from 'node:test';
import assert from 'node:assert/strict';
import { nextQuestion, deriveState, createReport } from '../src/engine.js';

const a = (id, value) => ({ id, value });

function run(values) {
  const answers = [];
  for (const value of values) {
    const question = nextQuestion(answers);
    assert.ok(question, 'route ended before supplied answers');
    answers.push(a(question.id, value));
  }
  return answers;
}

test('all personas reach a relevant situation question', () => {
  for (const persona of ['solo', 'ai', 'team', 'enterprise', 'other']) {
    const question = nextQuestion([a('persona', persona)]);
    assert.equal(question.id, 'situation');
    assert.ok(question.options.length >= 5);
  }
});

test('control and no-memory branches finish without invented event', () => {
  const control = run(['solo', 'none', 'no_need']);
  assert.equal(nextQuestion(control), null);
  assert.equal(deriveState(control).validationStatus, 'no_reported_problem');
  const noMemory = run(['ai', 'transfer', 'no_memory']);
  assert.equal(nextQuestion(noMemory), null);
  assert.equal(deriveState(noMemory).validationStatus, 'insufficient_evidence');
});

test('facts in text skip repeated action and time questions', () => {
  const answers = run(['solo', 'lost_context', 'week', 'Вчера удалил чат, восстанавливал вручную 4 часа и теперь сохраняю заметки', 'time']);
  assert.equal(nextQuestion(answers).id, 'outcome');
  assert.equal(deriveState(answers).timeCost, 'stated_in_event');
});

test('express route stays within ten questions and one clarification', () => {
  const values = ['enterprise', 'audit', 'month', 'Во время проверки не нашли решение', 'time', 'hours', 'manual', 'git', 'accurate'];
  const answers = run(values);
  assert.equal(nextQuestion(answers), null);
  assert.ok(answers.length <= 10);
  assert.equal(answers.filter(({ id }) => id === 'timeCost').length, 1);
});

test('report keeps verbatim answer and backtracking can replay the route', () => {
  const answers = run(['team', 'outdated', 'quarter', 'В прошлом проекте инструкция устарела', 'error']);
  assert.equal(nextQuestion(answers).id, 'action');
  answers.pop();
  assert.equal(nextQuestion(answers).id, 'consequence');
  const report = createReport(answers, 'test-id');
  assert.equal(report.transcript[3].answer, 'В прошлом проекте инструкция устарела');
  assert.equal(report.validationStatus, 'reported_event');
});

test('eight representative paths have no loops', () => {
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
  for (const values of cases) {
    const answers = run(values);
    assert.equal(nextQuestion(answers), null);
    assert.equal(new Set(answers.map(({ id }) => id)).size, answers.length);
    assert.ok(answers.length <= 10);
  }
});
