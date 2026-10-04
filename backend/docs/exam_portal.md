# Student Exam Portal & Exam Mode

Раздел для студентов: список экзаменов, подготовка, Exam Mode с таймером и
ограничениями, результат. Построен на существующем модуле `apps.testing`
(Test / Question / TestSession / StudentAttempt / Answer) — отдельной
системы вопросов нет.

## 1. Что уже было в проекте (анализ)

| Сущность | Где | Роль в портале |
|---|---|---|
| `Test` | `apps/testing/models.py` | «Экзамен» как набор вопросов и его настройки (время, проходной балл, попытки, перемешивание, показ результата/ответов) |
| `Question`, `QuestionOption` | там же | вопросы single / multiple / text / code |
| `TestSession` (type=`exam`) | там же | запуск теста для группы: расписание, статус, дедлайн. **`exam_id` в URL = id сессии** |
| `StudentAttempt`, `Answer` | там же | попытка и ответы; оценка — `services/grading.py` |
| `SessionParticipant` | там же | ростер сессии + live-мониторинг для преподавателя |
| `academy.Student`, `Group`, `Course` | `apps/academy` | студент, группа, программа |
| `/exam/` | `public_views.py` | старый вход студента по ключу сессии (без логина) — **не меняется** |

Аутентификация: JWT (`/api/v1/`) только для сотрудников (Admin / Teacher /
Team Lead), Django-сессия — для админки. **У студентов аккаунтов нет** —
сторона студента всегда работала через Django-сессию (`/exam/` помнит id
попыток в сессии браузера).

## 2. Архитектура

* **Вход студента** — персональный код доступа (`StudentPortalAccess`,
  выдаёт администратор). Код → `student_id` в Django-сессии (`cycle_key()`
  при входе). Роль «студент» в `users.User` и JWT **не добавляется**: это
  не трогает права Admin/Teacher/Team Lead и не требует паролей для детей.
  Неверные коды ограничены по IP (как ключи на `/exam/`).
* **Страницы** — server-rendered Django (как `/exam/`): работают на слабых
  устройствах, без сборки фронтенда. JS только усиливает Exam Mode.
* **Backend — источник истины**: дедлайн хранится в попытке
  (`expires_at`), каждое действие (автосохранение, событие, отправка,
  открытие страницы) сначала проверяет владельца, статус и дедлайн;
  просроченная попытка завершается на сервере с сохранёнными ответами.
* **Автосохранение** — черновики ответов в `StudentAttempt.draft_answers`
  (JSON). В `Answer` ответы попадают только при завершении, через ту же
  оценку (`check_answer`), что и раньше — аналитика, «На проверке» и
  мониторинг не видят полуготовых ответов.
* **Exam Mode во фронтенде** — ограничения (copy/paste/cut, контекстное
  меню, выделение, горячие клавиши, вкладки, fullscreen, beforeunload)
  включаются только на странице активной попытки и снимаются при отправке.
  Это защита от случайных/простых действий, не от целенаправленного
  обхода: DevTools, второе устройство и т. п. браузер запретить не может.
  Поэтому все нарушения пишутся в журнал, а решения (лимит переключений
  вкладок, завершение) принимает сервер.

## 3. Модели (миграция `testing/0008_exam_portal`)

Все поля аддитивные, с default — старые данные и `/exam/` не меняются.

**`Test`** (+ настройки Exam Mode):

| Поле | Тип | По умолчанию |
|---|---|---|
| `require_fullscreen` | bool | `False` |
| `max_tab_switches` | int, null | `3` (пусто — без лимита) |
| `auto_submit` | bool | `True` |

Остальные настройки из ТЗ уже есть: duration = `time_limit_minutes`,
`passing_score`, `max_attempts`, allow_review = `show_correct_answers`,
show_results = `show_result`, randomize_questions = `shuffle_questions`,
randomize_answers = `shuffle_options`.

**`StudentAttempt`** (+):
`exam_mode`, `expires_at`, `draft_answers`, `draft_saved_at`,
`tab_switch_count`, `violation_count`, `finish_reason`
(`submitted` / `time_expired` / `violations` / `session_closed`).

**`StudentPortalAccess`** (новая): `student` (1:1), `code` (уникальный),
`is_active`, `created_at`, `last_login_at`.

**`ExamAttemptEvent`** (новая): `attempt`, `event_type`, `timestamp`,
`metadata` (только номер вопроса/короткая деталь), `user_agent`,
`ip_address` (отключается `EXAM_EVENTS_STORE_IP = False`).
Типы: `EXAM_STARTED, ANSWER_SAVED, TAB_SWITCH, FULLSCREEN_EXIT,
COPY_ATTEMPT, PASTE_ATTEMPT, CUT_ATTEMPT, CONTEXT_MENU_ATTEMPT,
DEVTOOLS_ATTEMPT, PAGE_LEAVE, EXAM_SUBMITTED, TIME_EXPIRED, EXAM_TERMINATED`.

## 4. URL

Страницы (`apps/testing/student_urls.py`, смонтировано на `/student/`):

| URL | Страница |
|---|---|
| `/student/login/`, `/student/logout/` | вход по коду / выход |
| `/student/` | Student Dashboard (кабинет) |
| `/student/exams/` | экзамены + summary cards |
| `/student/exams/<exam_id>/prepare/` | подготовка, правила, чекбокс, «Начать экзамен» (POST) |
| `/student/exams/<exam_id>/attempt/<attempt_id>/` | Exam Mode |
| `/student/exams/<exam_id>/attempt/<attempt_id>/submit/` | завершение (POST) |
| `/student/exams/<exam_id>/result/<attempt_id>/` | результат |
| `/student/exams/<exam_id>/review/<attempt_id>/` | разбор (если разрешён) |

JSON API (Django-сессия + CSRF):

| Метод и URL | Назначение |
|---|---|
| `GET  /student/api/exam-attempts/<id>/state/` | оставшееся время (сервер), статус, счётчики |
| `PATCH /student/api/exam-attempts/<id>/answers/` | автосохранение черновиков (+ heartbeat мониторинга) |
| `POST /student/api/exam-attempts/<id>/events/` | событие нарушения; ответ — счётчики и `terminated` |

Каждый запрос: студент из сессии → попытка принадлежит ему и этой
сессии → статус `active` → дедлайн не прошёл → валидация вопросов/вариантов
и размеров. Иначе 403/404/409.

## 5. Файлы

Новые:
`apps/testing/services/exam_portal.py`, `student_auth.py`,
`student_views.py`, `student_api.py`, `student_urls.py`,
`templates/testing/student/*.html`,
`static/testing/css/student_portal.css`,
`static/testing/js/exam_mode.js`, `static/testing/js/student_portal.js`,
`templates/admin/testing/sessions/monitoring.html`,
`migrations/0008_exam_portal.py`, `tests/test_exam_portal.py`.

Изменённые:
`models.py` (поля + 2 модели), `services/attempts.py` (общая функция
оценки, дедлайн из `expires_at`), `public_views.py` (попытку Exam Mode
нельзя открыть в старом `/exam/`), `forms.py` + `tests/settings.html`
(настройки Exam Mode), `admin.py` (мониторинг попыток, коды доступа),
`analytics_admin_views.py` + `sessions/attempt.html` (журнал событий),
`teacher_api.py` + фронтенд `ExamDetailPage` (нарушения у преподавателя),
`config/urls.py`, `config/settings/base.py` (пункты меню).

## 6. Админка

* Тест → «Настройки» → блок «Exam Mode»: fullscreen, лимит вкладок,
  автоотправка (+ существующие время, попытки, проходной балл, показ
  результата/разбора, перемешивание).
* «Сессии» → «Мониторинг экзаменов»: студент, экзамен, начало, конец,
  статус, балл, вкладки, нарушения, время. Открытие попытки показывает
  ответы и **журнал событий**.
* «Академия» → «Доступ студентов»: коды входа (создание, перевыпуск,
  отключение, массовая выдача по группе).

## 7. Миграция и выкатка

1. `python manage.py migrate testing` — только `ADD COLUMN` с default и
   две новые таблицы; блокировок данных нет, откат — `migrate testing 0007`.
2. Админ выдаёт коды: «Доступ студентов» → действие «Выдать коды группе»
   (или по одному).
3. Студенты входят на `/student/login/`. Старый вход по ключу `/exam/`
   продолжает работать для обычных сессий.

## Shared test UI (Training = Exam)

Training and Exam are one testing system. The exam runs on the same React
test screen as the trainers (`training-portal`: `TestScreen`, `QuestionCard`,
`ProgressBar`, `Timer`, `QuestionNavigation`, `ResultView`), with Exam
Mode's rules on the backend (`services/exam_portal.py`):

1. Student portal → «Начать экзамен» → `start_exam` (an active attempt is
   resumed, never duplicated; attempt limit applies).
2. `attempt_view` redirects to `{PortalSettings.portal_url}/exam/<id>#t=<token>`
   (`apps.training.exam_api.portal_exam_url`). Without a portal address the
   old student-portal page stays as the fallback.
3. The React page keeps the token for the tab (sessionStorage), removes it
   from the address bar and talks to `/api/v1/training/exam-attempts/<id>/…`
   (same shapes as the training API): state, autosave per answer, events,
   submit (`timed_out`), result.
4. A reload restores the same attempt: saved answers, the first unanswered
   question, the timer from the server's remaining time (re-synced on every
   save). `ensure_current` closes an overdue attempt on the server;
   auto-submit at 00:00 sends `timed_out`.
5. Tab switches follow `Test.max_tab_switches` (warning «n / max», the
   attempt ends past it); fullscreen follows `Test.require_fullscreen`.

Exam-only differences on the screen: «Экзамен» badge instead of «Артка», no
answer checking, «answered / left» counts, timer amber under 10 min and red
under 5, «Экзаменди аяктоо» confirmation with the unanswered count, the
result page with «Кабинетке кайтуу» and no retake / leaderboard.

Roles: only the student gets a token (from the student portal). A Team
Lead / Trainer cannot take a test (403); an Admin may check a test on the
legacy student page.
