import { nextQuestion, createReport } from './engine.js';
import { bundle, languages } from './questions.js';
import { SUBMIT_URL } from './config.js';

const app = document.querySelector('#app');
const storageKey = 'okf-interview-demo-v2';
const params = new URLSearchParams(location.search);
const submitUrl = params.get('submit') || SUBMIT_URL;

function initialLang() {
  const fromUrl = params.get('lang');
  if (languages.includes(fromUrl)) return fromUrl;
  return (navigator.language || '').toLowerCase().startsWith('ru') ? 'ru' : 'en';
}

function freshState() {
  return { answers: [], screen: 'start', mode: 'express', sessionId: crypto.randomUUID(), lang: initialLang(), sent: false };
}

let state = freshState();
let selected = '';

try {
  const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
  if (saved && Array.isArray(saved.answers)) state = { ...state, ...saved };
  if (languages.includes(params.get('lang'))) state.lang = params.get('lang');
} catch { /* Damaged demo data starts a fresh session. */ }

function save() {
  try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch { /* Private mode: keep going without storage. */ }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function langSwitch() {
  return `<div class="lang" role="group" aria-label="Language">${languages.map((code) => `<button type="button" class="lang-btn${code === state.lang ? ' active' : ''}" data-lang="${code}" aria-pressed="${code === state.lang}">${code.toUpperCase()}</button>`).join('')}</div>`;
}

function renderStart() {
  const t = bundle(state.lang).ui;
  app.innerHTML = `<section class="shell hero" aria-labelledby="start-title">
    ${langSwitch()}
    <div class="hero-content">
      <h1 id="start-title" class="question-text">${escapeHtml(t.title)}</h1>
      <p>${escapeHtml(t.intro)}</p>
      <p class="privacy">${escapeHtml(t.privacy)}</p>
      <p class="time-note">${escapeHtml(t.time)}</p>
      <button class="primary" id="start">${escapeHtml(state.answers.length ? t.resume : t.start)}</button>
    </div>
  </section>`;
  document.querySelectorAll('.lang-btn').forEach((button) => button.onclick = () => {
    state.lang = button.dataset.lang; save(); render();
  });
  document.querySelector('#start').onclick = () => { state.screen = 'interview'; save(); render(); };
}

function questionTitle(question) {
  const text = escapeHtml(question.question);
  return question.id === 'event' ? text.replace(/([.?!]) /, '$1<br>') : text;
}

function renderInterview() {
  const t = bundle(state.lang).ui;
  const question = nextQuestion(state.answers, state.mode, state.lang);
  if (!question) { state.screen = 'done'; save(); render(); return; }
  selected = '';
  const isText = question.answerType === 'text';
  const options = question.options.map(([value, title]) => `<button type="button" role="radio" aria-checked="false" class="option" data-value="${escapeHtml(value)}"><span class="option-dot"></span><span>${escapeHtml(title)}</span></button>`).join('');
  app.innerHTML = `<section class="shell interview ${isText ? 'text-question' : ''}" aria-labelledby="question-title">
    <h1 id="question-title" class="question-text">${questionTitle(question)}</h1>
    <div class="options" role="radiogroup" aria-label="${escapeHtml(t.pick)}">${options}</div>
    <div class="input-wrap ${isText ? '' : 'hidden'}" id="input-wrap">
      <label for="free-text">${escapeHtml(t.shortAnswer)}</label><textarea id="free-text" rows="3" maxlength="600" placeholder="${escapeHtml(t.placeholder)}"></textarea>
      <p class="hint">${escapeHtml(question.id === 'contact' ? t.contactHint : t.skipHint)}</p>
    </div>
    <div class="controls"><button class="secondary" id="back">${escapeHtml(t.back)}</button><button class="primary" id="next" disabled>${escapeHtml(t.next)}</button></div>
  </section>`;
  const input = document.querySelector('#free-text');
  const next = document.querySelector('#next');
  function update() {
    next.disabled = isText ? !input.value.trim() && !question.optional : !selected;
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
    // Ключ варианта всегда сохраняется как есть; свободный текст «Другое» — отдельным полем.
    const answer = isText ? { id: question.id, value: raw }
      : selected === 'other' ? { id: question.id, value: 'other', ...(raw ? { text: raw } : {}) }
        : { id: question.id, value: selected };
    state.answers.push(answer);
    save(); render();
  };
  document.querySelector('#back').onclick = () => {
    if (state.answers.length) state.answers.pop(); else state.screen = 'start';
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

async function sendReport(report) {
  if (!submitUrl) return 'offline';
  // text/plain не вызывает preflight. Google Apps Script отвечает с CORS-заголовками, поэтому статус виден;
  // если сервер их не отдаёт, повторяем без CORS и верим, что запрос дошёл.
  const request = { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify(report) };
  try {
    const response = await fetch(submitUrl, request);
    return response.ok ? 'sent' : 'failed';
  } catch {
    try {
      await fetch(submitUrl, { ...request, mode: 'no-cors' });
      return 'sent';
    } catch {
      return 'failed';
    }
  }
}

function renderDone() {
  const t = bundle(state.lang).ui;
  const report = createReport(state.answers, state.sessionId, state.mode, state.lang);
  app.innerHTML = `<section class="shell done" aria-labelledby="done-title">
    <div class="done-content">
      <h1 id="done-title">${escapeHtml(t.doneTitle)}</h1>
      <p>${escapeHtml(t.doneText)}</p>
      <p class="status" id="status" role="status">${escapeHtml(state.sent ? t.sent : submitUrl ? t.sending : t.offline)}</p>
      <div class="actions"><button class="primary" id="export">${escapeHtml(t.download)}</button>
        <button class="secondary" id="restart">${escapeHtml(t.restart)}</button></div>
    </div>
  </section>`;
  document.querySelector('#export').onclick = () => downloadReport(report);
  document.querySelector('#restart').onclick = () => { const { lang } = state; state = { ...freshState(), lang }; save(); render(); };
  if (!state.sent && submitUrl) {
    sendReport(report).then((result) => {
      if (result === 'sent') { state.sent = true; save(); }
      const status = document.querySelector('#status');
      if (status) status.textContent = t[result];
    });
  }
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
  document.documentElement.lang = state.lang;
  document.title = state.lang === 'ru' ? 'Исследование рабочих ситуаций — OKF' : 'Work context survey — OKF';
  try {
    if (state.screen === 'start') renderStart();
    else if (state.screen === 'done') renderDone();
    else renderInterview();
  } catch (error) {
    // Повреждённый или несовместимый сохранённый прогресс не должен оставлять пустой экран.
    console.error(error);
    const { lang } = state;
    state = { ...freshState(), lang };
    save();
    renderStart();
  }
}

render();
