import { nextQuestion, createReport } from './engine.js';

const app = document.querySelector('#app');
const storageKey = 'okf-interview-demo-v1';
let answers = [];
let screen = 'start';
let mode = 'express';
let sessionId = crypto.randomUUID();
let selected = '';

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

function renderStart() {
  app.innerHTML = `<section class="shell hero" aria-labelledby="start-title">
    <div class="hero-content">
      <h1 id="start-title" class="question-text">Как вы сохраняете важный контекст работы?</h1>
      <p>Здесь нет правильных ответов. Выбирайте только один вариант — тот, который подходит вам больше всего.</p>
      <p class="time-note">Не более 3 минут.</p>
      <button class="primary" id="start">${answers.length ? 'Продолжить' : 'Начать'}</button>
    </div>
  </section>`;
  document.querySelector('#start').onclick = () => { screen = 'interview'; save(); render(); };
}

function questionTitle(question) {
  const text = escapeHtml(question.question);
  return question.id === 'event'
    ? text.replace('Опишите коротко конкретный случай.', '<br>Опишите коротко конкретный случай.')
    : text;
}

function renderInterview() {
  const question = nextQuestion(answers, mode);
  if (!question) { screen = 'done'; save(); render(); return; }
  selected = '';
  const options = question.options.map(([value, title]) => `<button type="button" role="radio" aria-checked="false" class="option" data-value="${escapeHtml(value)}"><span class="option-dot"></span><span>${escapeHtml(title)}</span></button>`).join('');
  app.innerHTML = `<section class="shell interview ${question.answerType === 'text' ? 'text-question' : ''}" aria-labelledby="question-title">
    <h1 id="question-title" class="question-text">${questionTitle(question)}</h1>
    <div class="options" role="radiogroup" aria-label="Выберите один вариант ответа">${options}</div>
    <div class="input-wrap ${question.answerType === 'text' ? '' : 'hidden'}" id="input-wrap">
      <label for="free-text">Короткий ответ</label><textarea id="free-text" rows="3" maxlength="600" placeholder="Напишите своими словами"></textarea>
      <p class="hint">Можно пропустить, если не помните подробности.</p>
    </div>
    <div class="controls"><button class="secondary" id="back">Назад</button><button class="primary" id="next" disabled>Продолжить</button></div>
  </section>`;
  const input = document.querySelector('#free-text');
  const next = document.querySelector('#next');
  function update() {
    const text = input.value.trim();
    next.disabled = question.answerType === 'text' ? !text && !question.optional : !selected;
  }
  document.querySelectorAll('.option').forEach((button) => button.onclick = () => {
    selected = button.dataset.value;
    document.querySelectorAll('.option').forEach((item) => {
      item.classList.toggle('selected', item === button);
      item.setAttribute('aria-checked', String(item === button));
    });
    const needsText = selected === 'other';
    document.querySelector('#input-wrap').classList.toggle('hidden', !needsText);
    document.querySelector('.interview').classList.toggle('has-other', needsText);
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
  app.innerHTML = `<section class="shell done" aria-labelledby="done-title">
    <div class="done-content">
      <h1 id="done-title">Спасибо за ответы</h1>
      <p>Опрос завершён.</p>
      <div class="actions"><button class="primary" id="export">Скачать ответы</button>
        <button class="secondary" id="restart">Начать заново</button></div>
    </div>
  </section>`;
  document.querySelector('#export').onclick = () => downloadReport(report);
  document.querySelector('#restart').onclick = () => { answers = []; screen = 'start'; mode = 'express'; sessionId = crypto.randomUUID(); save(); render(); };
}

document.addEventListener('selectstart', (event) => {
  if (!event.target.closest?.('textarea, input')) event.preventDefault();
});
document.addEventListener('copy', (event) => {
  if (!document.activeElement?.matches?.('textarea, input')) event.preventDefault();
});
document.addEventListener('contextmenu', (event) => {
  if (!event.target.closest?.('textarea, input')) event.preventDefault();
});
document.addEventListener('dragstart', (event) => {
  if (!event.target.closest?.('textarea, input')) event.preventDefault();
});

function render() {
  if (screen === 'start') renderStart();
  else if (screen === 'done') renderDone();
  else renderInterview();
}

render();
