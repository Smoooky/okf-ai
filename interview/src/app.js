import { nextQuestion, createReport } from './engine.js';

const app = document.querySelector('#app');
const storageKey = 'okf-interview-demo-v1';
let answers = [];
let screen = 'start';
let mode = 'express';
let sessionId = crypto.randomUUID();
let selected = '';
let otherText = '';

try {
  const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
  if (saved && Array.isArray(saved.answers)) {
    ({ answers, screen, mode, sessionId } = saved);
  }
} catch { /* Damaged demo data starts a fresh session. */ }

function save() {
  localStorage.setItem(storageKey, JSON.stringify({ answers, screen, mode, sessionId }));
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function header() {
  return '<header class="header"><div class="brand"><span class="brand-mark">◈</span> OKF <span class="brand-light">/ Interview Lab</span></div><span class="badge">Демо</span></header>';
}

function renderStart() {
  app.innerHTML = `${header()}<section class="shell hero">
    <div class="eyebrow">КОРОТКОЕ ИССЛЕДОВАНИЕ</div>
    <h1>Как вы сохраняете важный контекст работы?</h1>
    <p class="lead">Расскажите о недавнем опыте работы с информацией, решениями и AI-инструментами. Здесь нет правильных ответов.</p>
    <div class="info"><span>◷ 3–5 минут</span><span>◇ Вопросы зависят от ваших ответов</span></div>
    <button class="primary" id="start">${answers.length ? 'Продолжить интервью' : 'Начать интервью'} <span>→</span></button>
    <p class="privacy">Демо-режим: ответы сохраняются только в этом браузере. Их можно выгрузить в JSON после завершения. Не вводите личные или конфиденциальные сведения.</p>
  </section>`;
  document.querySelector('#start').onclick = () => { screen = 'interview'; save(); render(); };
}

function renderInterview() {
  const question = nextQuestion(answers, mode);
  if (!question) { screen = 'done'; save(); render(); return; }
  selected = '';
  otherText = '';
  const index = answers.length + 1;
  const progress = Math.min(90, Math.round((index / 8) * 100));
  const options = question.options.map(([value, title]) => `<button type="button" class="option" data-value="${escapeHtml(value)}"><span class="option-dot"></span><span>${escapeHtml(title)}</span></button>`).join('');
  app.innerHTML = `${header()}<section class="shell interview">
    <div class="topline"><span>Вопрос ${index} · обычно 6–8 вопросов</span><button class="quiet" id="finish">Закончить раньше</button></div>
    <div class="progress"><span style="width:${progress}%"></span></div>
    <div class="eyebrow">${escapeHtml(question.researchGoal)}</div>
    <h1>${escapeHtml(question.question)}</h1>
    <div class="options">${options}</div>
    <div class="input-wrap ${question.answerType === 'text' ? '' : 'hidden'}" id="input-wrap">
      <label for="free-text">Короткий ответ</label><textarea id="free-text" rows="4" maxlength="600" placeholder="Напишите своими словами"></textarea>
      <p class="hint">Можно пропустить, если не помните подробности.</p>
    </div>
    <div class="controls"><button class="secondary" id="back">← Назад</button><button class="primary" id="next" disabled>Продолжить →</button></div>
  </section>`;
  const input = document.querySelector('#free-text');
  const next = document.querySelector('#next');
  function update() {
    const text = input.value.trim();
    next.disabled = question.answerType === 'text' ? !text && !question.optional : !selected;
  }
  document.querySelectorAll('.option').forEach((button) => button.onclick = () => {
    selected = button.dataset.value;
    document.querySelectorAll('.option').forEach((item) => item.classList.toggle('selected', item === button));
    const needsText = selected === 'other';
    document.querySelector('#input-wrap').classList.toggle('hidden', !needsText);
    if (needsText) input.focus();
    update();
  });
  input.oninput = update;
  next.onclick = () => {
    const raw = input.value.trim();
    const value = question.answerType === 'text' ? raw || 'Не помню подробности' : selected === 'other' ? (raw || 'Другое') : selected;
    answers.push({ id: question.id, value });
    save(); render();
  };
  document.querySelector('#back').onclick = () => {
    if (answers.length) answers.pop(); else screen = 'start';
    save(); render();
  };
  document.querySelector('#finish').onclick = () => { screen = 'done'; save(); render(); };
  update();
}

function downloadReport(report) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `okf-interview-${report.sessionId.slice(0, 8)}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function renderDone() {
  const report = createReport(answers, sessionId, mode);
  const status = report.validationStatus === 'no_reported_problem' ? 'Не обнаружена описанная ситуация' :
    report.validationStatus === 'reported_event' ? 'Описан конкретный случай' : 'Недостаточно данных';
  const rows = report.transcript.map((item) => `<li><strong>${escapeHtml(item.questionId)}</strong><span>${escapeHtml(item.displayAnswer)}</span></li>`).join('');
  app.innerHTML = `${header()}<section class="shell done">
    <div class="success">✓</div><div class="eyebrow">ИНТЕРВЬЮ ЗАВЕРШЕНО</div>
    <h1>Спасибо за участие</h1><p class="lead">Ваши ответы остались только в этом браузере. Для передачи исследователю выгрузите файл JSON.</p>
    <div class="report"><div class="report-heading"><h2>Карточка интервью</h2><span class="status">${status}</span></div>
      <dl><dt>Ситуация</dt><dd>${escapeHtml(report.summary.situation)}</dd>
      <dt>Реальный случай</dt><dd>${escapeHtml(report.summary.event || 'Не описан')}</dd>
      <dt>Последствие</dt><dd>${escapeHtml(report.summary.consequence || 'Не указано')}</dd>
      <dt>Текущее решение</dt><dd>${escapeHtml(report.summary.currentSolution || 'Не указано')}</dd></dl>
      <details><summary>Все ответы</summary><ol>${rows}</ol></details>
    </div>
    <div class="actions"><button class="primary" id="export">Скачать JSON ↓</button>
      ${mode === 'express' && report.validationStatus === 'reported_event' ? '<button class="secondary" id="deep">Продолжить глубже</button>' : ''}
      <button class="quiet" id="restart">Начать новый тест</button></div>
    <p class="privacy">Это демонстрация исследовательского сценария. Статус карточки не означает подтверждение продуктовой гипотезы.</p>
  </section>`;
  document.querySelector('#export').onclick = () => downloadReport(report);
  document.querySelector('#restart').onclick = () => { answers = []; screen = 'start'; mode = 'express'; sessionId = crypto.randomUUID(); save(); render(); };
  const deep = document.querySelector('#deep');
  if (deep) deep.onclick = () => { mode = 'deep'; screen = 'interview'; save(); render(); };
}

function render() {
  if (screen === 'start') renderStart();
  else if (screen === 'done') renderDone();
  else renderInterview();
}

render();
