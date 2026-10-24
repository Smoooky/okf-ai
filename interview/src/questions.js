// Тексты опроса на двух языках. Ключи вариантов одинаковые, поэтому ответы сравнимы между языками.
const ru = {
  personas: [
    ['solo', 'Самостоятельно разрабатываю продукты или автоматизации'],
    ['ai', 'Создаю AI-агентов и AI-системы'],
    ['team', 'Работаю в небольшой команде'],
    ['enterprise', 'Работаю в большой компании'],
    ['other', 'Другое'],
  ],
  situations: {
    solo: [
      ['lost_context', 'Терял контекст переписки или настройки AI'],
      ['repeat_explanation', 'Приходилось повторно объяснять агенту проект'],
      ['lost_decision', 'Не мог найти ранее принятое решение'],
      ['lost_result', 'Терял результат работы'],
    ],
    ai: [
      ['lost_context', 'Агент терял важный контекст'],
      ['transfer', 'Контекст не переносился между инструментами'],
      ['conflict', 'Разные агенты использовали противоречивую информацию'],
      ['restore_session', 'Приходилось восстанавливать предыдущую сессию'],
    ],
    team: [
      ['outdated', 'Документация оказалась устаревшей'],
      ['search', 'Участники не могли найти нужные знания'],
      ['lost_decision', 'Потерялся контекст решений'],
      ['handoff', 'Возникли сложности при передаче задач'],
    ],
    enterprise: [
      ['outdated', 'Использовали устаревшую информацию'],
      ['audit', 'Возникли проблемы при аудите или проверке'],
      ['wrong_answer', 'AI или сотрудники получали неверные ответы'],
      ['restore_info', 'Пришлось восстанавливать важную информацию'],
    ],
    other: [
      ['lost_context', 'Приходилось восстанавливать контекст работы'],
      ['search', 'Не мог найти нужную информацию'],
      ['outdated', 'Информация оказалась устаревшей'],
    ],
  },
  common: {
    recency: [
      ['week', 'За последние 7 дней'], ['month', 'За последний месяц'],
      ['quarter', 'За последние 3 месяца'], ['older', 'Раньше'],
      ['no_memory', 'Не могу вспомнить конкретный случай'],
    ],
    consequence: [
      ['time', 'Потратил дополнительное время'], ['rework', 'Пришлось переделывать работу'],
      ['error', 'Допустил ошибку'], ['lost_result', 'Потерял результат'],
      ['none', 'Существенных последствий не было'],
    ],
    action: [
      ['manual', 'Восстановил вручную'], ['backup', 'Нашёл сохранённую копию'],
      ['other_tool', 'Использовал другой инструмент'], ['help', 'Обратился за помощью'],
      ['restart', 'Начал заново'], ['nothing', 'Ничего не предпринимал'],
    ],
    prevention: [
      ['notes', 'Храню информацию в файлах или заметках'],
      ['git', 'Использую Git и историю изменений'],
      ['ai_memory', 'Использую память AI-инструмента'],
      ['automation', 'Применяю автоматизацию или резервные копии'],
      ['nothing', 'Ничего специально не делаю'],
    ],
    outcome: [
      ['continue', 'Продолжить работу без повторного восстановления'],
      ['accurate', 'Получить точную и актуальную информацию'],
      ['share', 'Передать контекст другим людям или агентам'],
      ['finish', 'Завершить конкретную задачу или проект'],
    ],
    timeCost: [
      ['minutes', 'Меньше часа'], ['hours', 'От 1 до 4 часов'],
      ['day', 'Больше рабочего дня'], ['unknown', 'Не помню'],
    ],
  },
  extra: {
    none: 'Ничего подобного не происходило',
    other: 'Другое',
    noNeed: 'Пока не возникало такой потребности',
  },
  prompts: {
    persona: 'Как вы обычно работаете над проектами?',
    situation: 'Какая из этих ситуаций происходила с вами за последнее время?',
    control: 'Как вы сейчас сохраняете важный контекст работы?',
    recency: 'Когда последний раз это произошло?',
    event: 'Что случилось в тот раз? Опишите коротко конкретный случай.',
    consequence: 'Как это повлияло на вашу работу?',
    timeCost: 'Сколько времени примерно ушло дополнительно?',
    action: 'Что вы тогда сделали?',
    prevention: 'Как вы сейчас стараетесь избежать повторения?',
    outcome: 'Какого результата вы тогда пытались добиться?',
    deep: 'Если хотите, расскажите, почему этот результат был важен и какие решения вы пробовали.',
    contact: 'Готовы на 20-минутный разговор или хотите получить материал по context engineering? Оставьте Telegram или email.',
  },
  ui: {
    title: 'Как вы сохраняете важный контекст работы?',
    intro: 'Здесь нет правильных ответов. Выбирайте только один вариант — тот, который подходит вам больше всего.',
    privacy: 'Ответы получит команда okf-ai. Контакт оставлять не обязательно.',
    time: 'Не более 3 минут.',
    start: 'Начать', resume: 'Продолжить', next: 'Продолжить', back: 'Назад',
    pick: 'Выберите один вариант ответа',
    shortAnswer: 'Короткий ответ', placeholder: 'Напишите своими словами',
    skipHint: 'Можно пропустить, если не помните подробности.',
    contactHint: 'Можно пропустить.',
    doneTitle: 'Спасибо за ответы', doneText: 'Опрос завершён.',
    download: 'Скачать ответы', restart: 'Начать заново',
    sending: 'Отправляем ответы…',
    sent: 'Ответы отправлены команде.',
    failed: 'Не удалось отправить ответы. Скачайте файл и отправьте его команде.',
    offline: 'Отправка не настроена. Скачайте файл и отправьте его команде.',
  },
};

const en = {
  personas: [
    ['solo', 'I build products or automations on my own'],
    ['ai', 'I build AI agents and AI systems'],
    ['team', 'I work in a small team'],
    ['enterprise', 'I work at a large company'],
    ['other', 'Other'],
  ],
  situations: {
    solo: [
      ['lost_context', 'I lost a chat context or my AI setup'],
      ['repeat_explanation', 'I had to explain the project to an agent again'],
      ['lost_decision', 'I could not find a decision made earlier'],
      ['lost_result', 'I lost a piece of finished work'],
    ],
    ai: [
      ['lost_context', 'An agent lost important context'],
      ['transfer', 'Context did not carry over between tools'],
      ['conflict', 'Different agents used conflicting information'],
      ['restore_session', 'I had to rebuild a previous session'],
    ],
    team: [
      ['outdated', 'The documentation turned out to be outdated'],
      ['search', 'People could not find the knowledge they needed'],
      ['lost_decision', 'The reasoning behind decisions got lost'],
      ['handoff', 'Handing over work was difficult'],
    ],
    enterprise: [
      ['outdated', 'Someone relied on outdated information'],
      ['audit', 'An audit or review ran into problems'],
      ['wrong_answer', 'AI or colleagues got wrong answers'],
      ['restore_info', 'Important information had to be recovered'],
    ],
    other: [
      ['lost_context', 'I had to rebuild the context of my work'],
      ['search', 'I could not find the information I needed'],
      ['outdated', 'The information turned out to be outdated'],
    ],
  },
  common: {
    recency: [
      ['week', 'In the last 7 days'], ['month', 'In the last month'],
      ['quarter', 'In the last 3 months'], ['older', 'Earlier'],
      ['no_memory', 'I cannot recall a specific case'],
    ],
    consequence: [
      ['time', 'I spent extra time'], ['rework', 'I had to redo work'],
      ['error', 'I made a mistake'], ['lost_result', 'I lost the result'],
      ['none', 'No real consequences'],
    ],
    action: [
      ['manual', 'Rebuilt it by hand'], ['backup', 'Found a saved copy'],
      ['other_tool', 'Used another tool'], ['help', 'Asked someone for help'],
      ['restart', 'Started over'], ['nothing', 'Did nothing'],
    ],
    prevention: [
      ['notes', 'I keep information in files or notes'],
      ['git', 'I use Git and change history'],
      ['ai_memory', 'I use the AI tool’s memory'],
      ['automation', 'I use automation or backups'],
      ['nothing', 'Nothing in particular'],
    ],
    outcome: [
      ['continue', 'Keep working without rebuilding context again'],
      ['accurate', 'Get accurate, up-to-date information'],
      ['share', 'Pass the context to other people or agents'],
      ['finish', 'Finish a specific task or project'],
    ],
    timeCost: [
      ['minutes', 'Less than an hour'], ['hours', '1 to 4 hours'],
      ['day', 'More than a working day'], ['unknown', 'I don’t remember'],
    ],
  },
  extra: {
    none: 'Nothing like this happened',
    other: 'Other',
    noNeed: 'I haven’t needed to yet',
  },
  prompts: {
    persona: 'How do you usually work on projects?',
    situation: 'Which of these has happened to you recently?',
    control: 'How do you keep important work context today?',
    recency: 'When did it last happen?',
    event: 'What happened that time? Briefly describe the specific case.',
    consequence: 'How did it affect your work?',
    timeCost: 'Roughly how much extra time did it take?',
    action: 'What did you do then?',
    prevention: 'How do you try to avoid it happening again?',
    outcome: 'What result were you trying to get back then?',
    deep: 'If you like, tell us why that result mattered and what you tried.',
    contact: 'Up for a 20-minute chat, or want our context-engineering notes? Leave a Telegram handle or email.',
  },
  ui: {
    title: 'How do you keep important work context?',
    intro: 'There are no right answers. Pick the one option that fits you best.',
    privacy: 'Your answers go to the okf-ai team. Leaving a contact is optional.',
    time: 'About 3 minutes.',
    start: 'Start', resume: 'Continue', next: 'Continue', back: 'Back',
    pick: 'Pick one answer',
    shortAnswer: 'Short answer', placeholder: 'In your own words',
    skipHint: 'You can skip this if you don’t remember the details.',
    contactHint: 'You can skip this.',
    doneTitle: 'Thank you', doneText: 'The survey is complete.',
    download: 'Download answers', restart: 'Start over',
    sending: 'Sending your answers…',
    sent: 'Your answers were sent to the team.',
    failed: 'We could not send your answers. Please download the file and send it to the team.',
    offline: 'Sending is not set up. Please download the file and send it to the team.',
  },
};

export const texts = { ru, en };
export const languages = Object.keys(texts);

export function bundle(lang) {
  return texts[lang] ?? texts.ru;
}

export const questionMeta = {
  persona: { researchGoal: 'Контекст работы', answerType: 'single', priority: 100, fieldMappings: ['persona'] },
  situation: { researchGoal: 'Навигационная гипотеза', answerType: 'single', priority: 90, fieldMappings: ['situation'] },
  recency: { researchGoal: 'Конкретный прошлый случай', answerType: 'single', priority: 80, fieldMappings: ['lastEvent'] },
  event: { researchGoal: 'Факты о событии', answerType: 'text', priority: 70, fieldMappings: ['evidence', 'context'] },
  consequence: { researchGoal: 'Последствия', answerType: 'single', priority: 60, fieldMappings: ['consequences'] },
  timeCost: { researchGoal: 'Затраченное время', answerType: 'single', priority: 55, fieldMappings: ['timeCost'] },
  action: { researchGoal: 'Реальные действия', answerType: 'single', priority: 50, fieldMappings: ['actualActions'] },
  prevention: { researchGoal: 'Текущее решение', answerType: 'single', priority: 40, fieldMappings: ['currentSolution'] },
  outcome: { researchGoal: 'Ожидаемый результат', answerType: 'single', priority: 30, fieldMappings: ['expectedOutcome'] },
  control: { researchGoal: 'Контрольная группа', answerType: 'single', priority: 20, fieldMappings: ['currentSolution'] },
  deep: { researchGoal: 'Расширенное исследование', answerType: 'text', priority: 10, fieldMappings: ['evidence'] },
  contact: { researchGoal: 'Контакт для интервью', answerType: 'text', priority: 5, fieldMappings: ['contact'] },
};
