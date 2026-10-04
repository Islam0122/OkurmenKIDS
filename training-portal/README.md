# Okurmen Kids — Training Portal

Публичный портал подготовки к экзамену (React + TypeScript + Vite).
Все данные — тесты, вопросы, проверка ответов, результаты, лидерборд,
видео, полезные ссылки, тексты главной и ссылка на экзамен — приходят
из Django backend (`/api/v1/training/`). Во фронтенде нет ни одного теста,
вопроса, видео или результата.

```bash
cp .env.example .env.local   # VITE_API_URL=https://okurmenkids.up.railway.app
npm install
npm run dev                  # http://localhost:5173
npm run build                # production → dist/
npm test                     # vitest
npm run lint                 # oxlint
```

`VITE_API_URL` обязателен: без него портал показывает ошибку настройки.
На Vercel: Root Directory — `training-portal`, переменная `VITE_API_URL`.
На backend (Railway) добавьте адрес портала в `TRAINING_PORTAL_ORIGINS`
(CORS), например `https://train.okurmen.kg`.

## Архитектура

```
src/
  api/         client.ts (fetch, VITE_API_URL, ошибки) + tests, attempts, videos,
               materials, leaderboard, portal — по одному файлу на ресурс
  types/       ровно то, что возвращает backend (portal, test, question, attempt, …)
  context/     PortalContext — настройки портала (тексты, exam_url)
  hooks/       useTraining (попытка через API: автосохранение, проверка, отправка),
               useTimer, useAsync, useFullscreen, useExamGuard
  layouts/     MainLayout (шапка/подвал сайта), ExamLayout (режим теста без навигации)
  services/    storageService — только временное UI-состояние (см. ниже)
  components/  Header, Hero, TestCard, QuestionCard, QuestionNavigation, ProgressBar,
               Timer, SaveIndicator, ResultCard, Leaderboard, VideoCard, UsefulLinkCard,
               Modal, Button/ExamButton, ErrorState, …
  pages/       Home, TrainingList, Training, Result, Leaderboard, Videos, Materials, Exam
```

Компоненты не вызывают `fetch` — только функции из `src/api/`.

Список тренажёров разбит на разделы по `category` из API (это «Предмет»
тренажёра в Django Admin). Категории не захардкожены: разделы и фильтр —
ровно те категории, что пришли с backend, в его порядке; без категории —
раздел «Башка» в конце.

## Режим экзамена (ExamLayout)

`/training/:testId` открывается в `ExamLayout` без шапки и подвала. Настройки
безопасности приходят с backend (`security` теста): после «Баштоо» вызывается
настоящий Fullscreen API; уход со вкладки, выход из полноэкранного режима,
копирование/вставка/контекстное меню отправляются на
`POST /api/v1/training/attempts/<id>/events/` и видны тренеру в «Мониторинге».
Если полноэкранный режим обязателен, тест закрыт оверлеем, пока ученик не
вернётся в него. Браузер не позволяет физически запретить другую вкладку —
портал предотвращает то, что можно, фиксирует и сообщает. Слушатели
снимаются при выходе из `ExamLayout`.

## localStorage

Только `okurmen_student_name` (подставить имя в форму) и
`okurmen_active_attempts` (`{testId: {attemptId, token}}` — продолжить
тренировку после перезагрузки). Тесты, ответы, результаты и лидерборд не
хранятся — источник истины backend.

## Тренировка ≠ экзамен

Кнопка «Экзаменге өтүү» открывает `exam_url` тренажёра или, если его нет, из настроек портала (Django
Admin → «Тренировочный портал» → «Настройки портала»); без ссылки кнопка
скрыта. Настоящий экзамен проходит в LMS (Exam Mode).
