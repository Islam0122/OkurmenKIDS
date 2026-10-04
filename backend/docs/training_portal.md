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

## Admin flow

1. «Тесты» → create the test, add questions (with «Пояснение к ответу»), publish.
2. «Сессии» → create a session for it → «Настройки»: «Режим: Тренажёр»,
   tick «Публичная тренировка» → «Начать сейчас».
3. «Тренировочный портал» → «Настройки портала» (exam URL, texts),
   «Видео», «Полезные ссылки» → publish. The portal shows them at once.
4. Results: the session's analytics in «Сессии», like any other attempt.
