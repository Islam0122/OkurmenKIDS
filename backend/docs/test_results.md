# Test Results

A result **is** a finished `StudentAttempt` of an LMS student (`student` set,
`user` empty) — there is no separate result table. Anonymous public-trainer
attempts (name only) are not student results.

## Historical snapshot (testing migration 0011)

`StudentAttempt.group / teacher / subject / test_title` are filled when the
attempt is created (`services/result_snapshot.py`):

* group — the session's group, else the student's group at that moment;
* teacher — the session's teacher, else the group's active teacher of the
  test's subject, else the group's only active teacher;
* subject, test title — from the test.

A student moving group, a replaced teacher or a renamed / re-subjected test
does not rewrite old results. Existing rows were back-filled from their
current session / student.

## Where results are used

| Place | Source |
|---|---|
| LMS student page, group «Тестирование», trainer page, dashboard, exam page, Analytics → «Тесты» | `/api/v1/monitoring/results/…` |
| KPI page «Тесты», KPI metrics `test_score`, `test_pass_rate` | `KPIEngine` + `analytics/assessments.py` (reported alongside, **not** in the total KPI) |
| Admin «Результаты тестов», test → «Статистика» → «Посмотреть результаты» | proxy `TestResult` |
| Student portal «Акыркы жыйынтыктар», `/student/results/` | `services.results.student_results` |
| Training portal leaderboard `?sort=average|tests` | `training.services.leaderboard_by_name` |

## API (`/api/v1/monitoring/`, JWT, Teacher / Team Lead / Admin)

| Path | |
|---|---|
| `results/` | paginated rows (+ correct / incorrect / attempt №) |
| `results/summary/` | attempts, students, passed / failed, pass rate, average / best / lowest, average correct / questions, best student / group, daily dynamics; with `group` also the roster size |
| `results/students/` | per student: attempts, average, best, last result |
| `results/breakdown/?by=group|subject|teacher|test` | average and pass rate per row (`teacher`: Team Lead / Admin only) |
| `results/export/` | Excel of the filtered results |
| `attempts/<id>/` | detail incl. every answer: student's answer, correct answer, status, answer time |

Filters (all endpoints): `group, teacher, subject, test, session, student,
result=passed|failed, score_min, score_max, date_from, date_to, q`.

Scope is the monitoring scope: a Teacher sees results of their groups
(snapshot or current group) and of attempts they own; Team Lead / Admin see
the academy. Other results are 404 (no IDOR). Students see only their own
results in the student portal; a test that hides results hides the score.

All statistics are database aggregates (`Count / Avg / Min / Max`,
subqueries for per-row counts) — no rows are loaded to compute numbers.
