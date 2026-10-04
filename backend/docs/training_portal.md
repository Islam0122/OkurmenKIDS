# Public Training Portal API (`apps.training`)

Backend for the public React portal (`training-portal/`). No login: a
student enters only a name. Built on the testing module — no duplicate
test/question models.

## What is reused

| Portal concept | Backend |
|---|---|
| Training test | `TestSession` with `session_type=training`, `is_public=True`, status «Идёт», test «Активен» |
| Questions, options, images, types | `Test` / `Question` / `QuestionOption` (single, multiple, text, code) |
| Explanation | `Question.metadata["explanation"]` (already written by the questions import; now also in the question editor) |
| Attempt by name | `StudentAttempt` with `student_name` only (no LMS Student / User) |
| Saved answers | `StudentAttempt.draft_answers` (Exam Mode format), graded into `Answer` on submit |
| Grading, score | `services.grading.check_answer` / `grade_and_finish` / `attempt_score` |
| Time limit | `Test.time_limit_minutes` / session override → `StudentAttempt.expires_at`, enforced on every request |
| Instant feedback | allowed when `Test.show_correct_answers` |
| Result visibility | `Test.show_result` |

`academy/help/` is a static staff help page (no models), so videos, links
and portal settings got their own small models here.

## New models

* `PortalSettings` (singleton) — `hero_title`, `hero_subtitle`,
  `start_button_label`, `exam_button_label`, `exam_url`, `exam_open_in_new_tab`.
* `TrainingVideo` — `title, description, video_url, thumbnail_url, category, duration, order, published`.
* `TrainingLink` — `title, description, url, category, icon, order, published`.
* `TestSession.is_public` (testing migration 0009).

## Endpoints (`/api/v1/training/`, `AllowAny`, no auth classes)

| Method | Path | |
|---|---|---|
| GET | `portal/` | hero texts, exam link |
| GET | `tests/` · `tests/<id>/` | public training tests (`questions_count`, `duration`, …) |
| POST | `attempts/` | `{test_id, student_name}` → `{attempt_id, token, started_at, expires_at, …}` |
| GET | `attempts/<id>/` | questions (no correct answers), saved answers, feedback of checked ones — needs `X-Attempt-Token` |
| PUT | `attempts/<id>/answers/<question_id>/` | `{options, text}` — needs token |
| POST | `attempts/<id>/answers/<question_id>/check/` | locks the answer, returns status + correct answer + explanation — needs token |
| POST | `attempts/<id>/submit/` | grades on the backend, returns the result — needs token |
| GET | `attempts/<id>/result/` | result (+ review if the test shows correct answers) |
| GET | `leaderboard/?test=<id>&limit=` | best finished result per name: `rank, student_name, score, duration_seconds, …` |
| GET | `videos/` · `links/` | published only, by `order` |
| POST | `attempts/<id>/events/` | `{event_type, metadata}` — client security event (see below), needs token; 409 `terminated` when the limit ends the attempt |

## Security

* Only published content: public + running + training sessions of active
  tests; `published=True` videos/links. Draft tests → 404.
* Writes need the attempt's token (`django.core.signing`, bound to the id).
* Name: 2–50 chars, letters/digits/space/`.`/`-`/`'`, normalised.
* Answers validated against the attempt's own questions and options; sizes capped.
* Checked answers are locked; submitted/expired attempts refuse changes (409).
* Deadline and grading on the server; the page timer is display only.
* Per-IP throttles: `training_read`, `training_start`, `training_write`.
* CORS: `TRAINING_PORTAL_ORIGINS` (comma-separated) + header `x-attempt-token`.
* Leaderboard exposes only name, score, time, date and test.

## Exam lock mode (portal `ExamLayout`)

The attempt page runs in `ExamLayout` (no site header/footer). Security comes
from the test settings and is returned as `security` in the test/attempt payload:
`require_fullscreen`, `track_tab_switches`, `max_tab_switches`, `block_copy_paste`.

* Start → real Fullscreen API (`requestFullscreen`) inside the click.
* `visibilitychange` → `TAB_SWITCH` / `TAB_RETURN` + modal «Сиз тесттен чыгып кеттиңиз».
* `fullscreenchange` → `FULLSCREEN_EXIT` / `FULLSCREEN_ENTER`; when fullscreen
  is required a blocking overlay stays until the student returns to fullscreen.
* Copy/cut/paste/drop/context menu blocked inside the layout only →
  `COPY_ATTEMPT`, `CUT_ATTEMPT`, `PASTE_ATTEMPT`, `CONTEXT_MENU_ATTEMPT`.
  Typing in answer fields is not affected. `beforeunload` warns, `pagehide` → `PAGE_LEAVE`.
* All listeners are removed when the layout unmounts.
* The backend counts violations and ends the attempt (`EXAM_TERMINATED`) when
  `max_tab_switches` is exceeded. The server also logs `TRAINING_STARTED`,
  `ANSWER_SAVED`, `TIME_EXPIRED`, `TRAINING_SUBMITTED`.

A browser cannot physically stop a student from opening another tab or
device: the system prevents what the browser allows, detects, logs and
notifies — it does not promise more.

## Access model

A trainer is a public product, not an LMS feature of a particular student.

```
Trainer → Published? → no: hidden (404, not in the list)
                     → yes: anyone → name → attempt → result → leaderboard
```

* No login, registration, JWT, Student, group, teacher or team-lead
  assignment is needed to train. Only «Опубликован» trainers are listed.
* An attempt is a `StudentAttempt` with `student_name` only
  (`student = user = NULL`); no `User`/`Student` is ever created.
* Stored for a participant: name, answers, score, times, security events.
  No email, phone, password; events of public attempts keep **no IP address
  and no user agent** (IP is used only in memory for rate limiting).
* The public list never returns draft/archived trainers, groups, teachers,
  session keys or internal status.
* `allow_retry = False` → a name that already finished gets 409
  `retry_disabled`; the portal hides «Кайра тапшыруу».
* `require_fullscreen` is per trainer: off → an ordinary page, on →
  fullscreen is requested after «Баштоо» and the lock overlay applies.
* «Экзаменге өтүү» only opens the real exam URL from the backend; the real
  exam (authorised student → LMS → Exam Mode) is a separate system.

## Admin flow — «Тренажёры»

`Trainer` is a proxy of `TestSession` (training type); its questions are the
ordinary `Test`/`Question` rows — nothing is duplicated.

1. «Тренировочный портал» → «Тренажёры» → «Добавить»: title, description,
   subject, program, cover, question count, time, explanation/retry/shuffle,
   security (fullscreen, tab tracking, max exits, copy/paste), real exam URL.
2. «Вопросы» opens the existing question editor of the test.
3. Field «Статус» in the form (or list actions): Черновик / Опубликован /
   Архив. «Опубликован» needs questions and makes the trainer visible to
   every visitor at once; an archived trainer cannot be republished.
   «Ответственный тренер» is optional (monitoring only).
4. «Открыть тренажёр» → `{PortalSettings.portal_url}/training/{id}` — set
   «Портал» in «Настройки портала».
5. «Попытки тренажёров» — read-only list; results also in session analytics.
6. «Настройки портала» (exam URL, texts), «Видео», «Полезные ссылки».

## Monitoring API (`/api/v1/monitoring/`, JWT, Teacher / Team Lead / Admin)

Scope is enforced on the backend: a Teacher sees attempts of their own groups,
plus public trainers of the subjects they teach (`Teacher.subjects` or their
group programs) and the trainers they are responsible for; Team Lead and Admin
see the whole academy. Portal visitors have no access (401). Staff
self-attempts are excluded.
Read-only (GET). The LMS page «Мониторинг» polls every 15 s (no WebSocket yet).

| Path | |
|---|---|
| `overview/` | active exams/trainers/students, completed, passed/failed, terminated, violations, average score |
| `attempts/` | live attempts table, filters: `group, teacher, subject, session, mode, status (in_progress/completed/expired/terminated), date_from, date_to, violations=1, q`; paginated (25) |
| `attempts/<id>/` | details: event timeline, violation counts, questions |
| `teachers/` | teacher performance (Team Lead / Admin only, 403 for teachers) |
| `groups/` · `groups/<id>/` | group analytics, failed students |
| `trainers/` · `trainers/<id>/` | per trainer/exam stats + difficult questions |
| `questions/?session=` | difficult questions |
| `filters/` | options for the filter selects visible to the user |

Overdue attempts are closed lazily when monitoring reads them.
