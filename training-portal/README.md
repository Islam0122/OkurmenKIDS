# Okurmen Kids — Training Portal

Публичная платформа подготовки к экзамену (React + TypeScript + Vite).
Без регистрации: студент вводит только имя, проходит тренировочный тест,
получает результат, видит лидерборд, видео и материалы и может перейти к
настоящему экзамену в LMS.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # production → dist/
npm test           # vitest
npm run lint       # oxlint
```

## Что меняет администратор

| Что | Где |
|---|---|
| URL настоящего экзамена, открытие в новой вкладке | `src/config/site.ts` или переменные `VITE_EXAM_URL`, `VITE_EXAM_OPEN_IN_NEW_TAB=true` |
| Тренировочные тесты (вопросы, время, объяснения, `showExplanation`) | `src/data/tests.ts` |
| Полезные видео (YouTube / Vimeo / прямая ссылка на файл) | `src/data/videos.ts` |
| Полезные материалы / ссылки | `src/data/links.ts` |
| Тексты интерфейса (кыргызский; структура под ru/en) | `src/i18n/` |

## Архитектура

```
src/
  config/      site.ts — настройки сайта (examUrl, …)
  data/        tests / videos / links — статичные данные
  types/       Test, Question, Video, UsefulLink, TrainingResult, …
  services/    contentService — источник контента (сейчас static, позже Django API)
               leaderboardService — интерфейс LeaderboardService + LocalLeaderboardService
               trainingService — попытка в процессе и результаты (localStorage)
               studentService, storageService — имя и единая работа с localStorage
  lib/         grading (правила проверки как в LMS), format, video, id
  hooks/       useTraining (движок тренировки), useTimer, useAsync
  components/  Header, Hero, TestCard, QuestionCard, QuestionNavigation, ProgressBar,
               Timer, ResultCard, Leaderboard, VideoCard, UsefulLinkCard, Modal, Button, …
  pages/       Home, TrainingList, Training, Result, Leaderboard, Videos, Materials, Exam, NotFound
```

UI, данные, бизнес-логика и хранение разделены: чтобы подключить Django API,
достаточно заменить реализацию `contentService` и добавить
`ApiLeaderboardService` — компоненты не меняются.

## localStorage

Только `okurmen_student_name`, `okurmen_training_progress`,
`okurmen_training_results`, `okurmen_leaderboard`. Никаких паролей и токенов.
Имя никуда не отправляется.

## Тренировка ≠ экзамен

Тренировка работает полностью во фронтенде и не связана с LMS. Кнопка
«Экзаменге өтүү» только открывает `examUrl` — настоящий экзамен проходит в LMS
(Exam Mode, серверный таймер, журнал нарушений).

Проверка ответов повторяет правила LMS: single/multiple — точное совпадение
набора, text — без учёта регистра и лишних пробелов, code — не проверяется
автоматически (показывается эталонное решение, в процент не входит).
