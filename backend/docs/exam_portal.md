# Exam Mode & the exam portal

Экзамен проходит в экзаменационном портале — том же React-экране, что и
тренажёры (`training-portal`: `TestScreen`, `ResultView`), с правилами
Exam Mode на сервере (`apps/testing/services/exam_portal.py`). Отдельного
кабинета студента нет: студент приходит по ссылке сессии.

## Flow

```
/exam/?key=XXXX                     testing.public_views.join_view
  → ключ сессии проверяется на сервере (find_session, лимит неверных ключей по IP)
  → студент: выбор из списка группы (ростер) или имя (сессия без ростера)
  → _start_in_shared_ui → exam_portal.start_exam (join: статус сессии,
    ростер, лимит попыток; активная попытка продолжается, не дублируется)
  → redirect {PortalSettings.portal_url}/exam/<attempt>#t=<token>
  → React: токен из #t= → sessionStorage вкладки, хэш убирается
  → useExam → useAttemptRunner → TestScreen (EXAM_MODE)
  → submit → /exam/<attempt>/result → ResultView (последний экран)
```

* Обновление `/exam/?key` в том же браузере возвращает ту же попытку.
  Другой браузер (или то же имя на другом устройстве) получает «уже начат»
  и токена не получает.
* `/exam/a/<attempt>/` (старая ссылка) для попытки Exam Mode отправляет
  браузер, начавший её, обратно в портал.
* Без адреса портала (`PortalSettings.portal_url` пуст) остаётся старая
  серверная форма `/exam/a/<attempt>/` — запасной вариант. Она же служит
  для LMS-handoff сотрудников (`?t=`).

`PortalSettings.portal_url` — корень портала (без `/exam`): путь
`/exam/<id>` сервер добавляет сам.

## API

`/api/v1/training/exam-attempts/<id>/…`, заголовок `X-Attempt-Token`
(`apps/training/exam_api.py`):

| Метод | Назначение |
|---|---|
| `GET` | состояние: вопросы, сохранённые ответы, `current_question_id`, оставшееся время (сервер) |
| `PATCH` | `{current_question_id, seq}` — текущий вопрос (страница шлёт с задержкой) |
| `PUT answers/<qid>/` | автосохранение ответа (+ `seq`) |
| `POST events/` | вкладки / fullscreen / копирование…; лимит `Test.max_tab_switches` завершает попытку |
| `POST submit/` | `{timed_out}` → результат (идемпотентно) |
| `GET result/` | результат по правилам `show_result` |

Эндпоинта «начать экзамен» в API нет — попытку создаёт только `/exam/?key`.

## Модели

`Test`: `require_fullscreen`, `max_tab_switches`, `auto_submit` (+ время,
попытки, проходной балл, показ результата/разбора, перемешивание).
`StudentAttempt`: `exam_mode`, `expires_at`, `draft_answers`,
`draft_saved_at`, `current_question_id`, `position_seq`,
`tab_switch_count`, `violation_count`, `finish_reason`.
`ExamAttemptEvent`: журнал событий попытки.

Миграция `testing/0014_remove_student_cabinet` удалила таблицу кодов входа
кабинета (`StudentPortalAccess`); студенты, попытки и результаты не
затронуты.

## Админка

* Тест → «Настройки» → «Exam Mode»: fullscreen, лимит вкладок, автоотправка.
* «Сессии» → «Мониторинг экзаменов» и карточка попытки с журналом событий.
* Тренажёр → «Портал»: адрес портала; «Настоящий экзамен»: куда ведёт
  кнопка «Экзаменге өтүү» (страница `/exam/`).

### Integrity

| Case | Protection |
|---|---|
| Token | `TimestampSigner("exam.attempt")` over `attempt:student:session` (student empty in a name-only session), 24 h; every request re-checks it against the stored row. Bad / expired / altered / foreign token → 403 `forbidden` before the attempt is looked up (no id enumeration). |
| Finished / expired attempt | result readable; PUT / PATCH / events → 409 `closed`; submit returns the stored result (idempotent). |
| Two autosaves of one question out of order, two tabs | the page sends `seq` (its clock); `save_drafts` keeps the newer one per question (stored in the draft) under `select_for_update`. |
| Two position moves out of order | `save_position`: one conditional `UPDATE … WHERE position_seq < seq`. |
| Double submit | `close_attempt` locks the row; the second call sees it closed. |
| Autosave committed during submit | `submit_exam` passes only the posted answers; `close_attempt` merges the drafts as stored under its lock. |
| Deadline | the server's (`ensure_current`, 5 s grace); the page's `timed_out` counts only within 15 s of it. |
| Attempts | no exam start endpoint in the API; `start_exam` → `join` resumes the active attempt and applies the limit. |

### Test modes (frontend)

`TestScreen` reads a `TestModeConfig` (`components/TestScreen/modes.ts`:
`TRAINING_MODE`, `EXAM_MODE`) — header (back button / badge), timer
thresholds, answer checking, counts, unanswered warning, restart, texts.
A new kind of test is a new config; the lifecycle stays in
`useAttemptRunner`, the endpoints in the adapters (`useTraining`, `useExam`).
