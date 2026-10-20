export const personas = [
  ['solo', 'Самостоятельно разрабатываю продукты или автоматизации'],
  ['ai', 'Создаю AI-агентов и AI-системы'],
  ['team', 'Работаю в небольшой команде'],
  ['enterprise', 'Работаю в большой компании'],
  ['other', 'Другое'],
];

export const situations = {
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
};

export const common = {
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
};

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
};
