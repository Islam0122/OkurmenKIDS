# Assistant Workspace

The **Assistant** (`User.Role.ASSISTANT`) runs the academy's daily operations:
groups, students, schedule, attendance, scholarships and surveys. It works
only in the LMS — `/assistant/*` in the frontend, `/api/v1/assistant/*` in
the API — never in Django admin and never in the Trainer / Team Lead pages
(`/app/*` redirects an Assistant to `/assistant`).

| Role | Where it works |
|---|---|
| Admin | `/admin/` (Django admin), may also open `/assistant/` |
| Team Lead | `/app/*` — reads the whole academy, KPI, analytics, reports |
| Assistant | `/assistant/*` — daily operations, no KPI / HR / roles / settings |
| Trainer | `/app/*` — own groups and lessons |

## Access

* `apps.users.permissions.IsAdminOrAssistant` gates every assistant view
  (active Assistant or Admin). An Assistant is deliberately **not** part of
  `can_view_academy`, so Team Lead reads (KPI, analytics, control, reports,
  worklog, monitoring) stay closed to it (403); the generic academy lists
  are scoped to a trainer's own groups and come back empty for it.
* `User.save()` keeps an Assistant non-staff and non-superuser;
  `OkurmenKidsAdminSite.has_permission` refuses it even with `is_staff`.
* Surveys reuse the feedback API (`/api/v1/feedback/surveys/`), now open to
  Admin and Assistant. Feedback analytics overview stays Admin-only.

## No new business logic

The assistant app has no models. Every write calls the service the admin /
Team Lead workspace already uses:

| Action | Service |
|---|---|
| Deactivate (reason → withdrawn) / Pause | `academy.services.student_status.deactivate_student` / `pause_student` (now accept an optional past `event_date`) |
| Activate | `reactivate_student` (from withdrawn, group required) / `continue_student` (from pause) |
| Add student | `academy.services.student_enrollment.enroll_student` |
| Transfer / add to group | `student_enrollment.transfer_student` / `add_students_to_group` |
| Create group | `academy.services.group_setup.create_group` (group + `save_program_config` per program + students, one transaction) |
| Teacher + weekly slots | `group_academic_config.save_program_config` (GroupSchedule.clean(): trainer / room / group conflicts) |
| Generate lessons | `lesson_generator.generate_lessons_for_group_with_report` |
| Move a lesson | `academy.services.lesson_move.move_lesson` (trainer / group / room conflict check, `schedule_overridden`) |
| Cancel a lesson | `lesson_reschedule.cancel_and_reschedule` |
| Scholarships | `scholarships.services.generation.generate_period` / `add_award` (approval and payment stay Admin's) |

## Attendance and homework are read only

Marks and homework are the trainer's record. For an Assistant both are
strictly read only, enforced on the server, not just hidden in the UI:

* `academy.permissions.IsAdminOrOwningTeacher` (attendance, homework,
  homework results, lesson complete / edit actions of `/api/v1/`) refuses
  every unsafe method for an Assistant — Admin and the owning trainer keep
  their rights unchanged.
* `assistant/attendance/lessons/<id>/` is Admin only.
* The new record endpoints (`groups/<id>/attendance|homework/`,
  `lessons/<id>/`, `homework/<id>/`, `control/…`) are GET only.

The numbers reuse the existing definitions: a held lesson is
`lesson_status.held_q` without cancelled ones; attended = present + late,
an absence = absent, excused is neutral; homework done = submitted /
checked / late, waiting for a check = submitted / late; a homework counts
once its deadline has passed (no deadline: once the lesson is held).
`apps/assistant/records.py` (group tabs, details) and
`apps/assistant/activity.py` (Контроль) only read.

## Контроль активности

`activity.py` judges every active student of an active, started group over
the chosen period — only their current stint in the group (since enrolment,
or since the latest transfer / reactivation into it). Unmarked lessons and
homework before its deadline are not counted as misses; a student with too
little data (`min_marked_lessons`, `min_due_homework`) is «Нет данных», never
flagged. Status: «Норма» (attendance ≥ 80 and homework ≥ 70), «Требует
внимания», «Низкая активность» (attendance < 60 or homework < 40), «В зоне
риска» (attendance < 50 and homework < 30). Categories: не ходят, не делают
ДЗ, не ходят + не делают ДЗ, часто пропускают (absence streak), давно не
сдавали ДЗ, низкая активность, в зоне риска.

All thresholds live in `activity.DEFAULT_THRESHOLDS`; override any of them
in settings without code changes:

```python
ASSISTANT_CONTROL_THRESHOLDS = {"normal_attendance": 85, "consecutive_absences": 2}
```

## Месячный отчёт

One report type: a month (`year` + `month`, the 1st 00:00 – the last day
23:59 in the project timezone). `apps/assistant/monthly.py` computes it on
request from existing data — no model, nothing stored, «Сформировать» /
re-requesting is the refresh. Order: overview → attendance (+ by group) →
low attendance → homework (+ by group) → not doing homework → risk →
surveys → scholarships → activity → conclusions.

* Attendance / homework / activity use the definitions above; lessons and
  homework after today never count. Student lists are «Контроль» over the
  month (`activity.analyse_students(..., start, until)`): active students
  of active, started groups, current stint only.
* Surveys (feedback app): surveys published or answered in the month.
  Average score only from single-choice questions with numeric options
  (1–5, 1–10), normalised to 5; participation only for a group's survey,
  against its active students; «низкая оценка» ≤ 40% of the scale. Text
  answers are quoted as written — repeated ones first.
* Scholarships: `ScholarshipAward` with `award_date` in the month.
* Conclusions are rules over these numbers (`GOOD_*` / `LOW_*` in
  monthly.py) — no generated advice.
* No trainer data at all (KPI, workload, ratings): that is the Team Lead's
  report.
* PDF: `monthly_pdf.build_monthly_pdf(report)` only renders the dict
  `monthly_report()` returns — the page and the PDF share one source and
  one period check. reportlab canvas in the academy reports' style (DejaVu
  fonts, LMS palette); tables wrap long names, continue across pages with
  a repeated header; running header, footer with generation time and
  «Страница N из M». Same permission as the rest of the workspace.

## History / audit

* A transfer is a `StudentStatusEvent` of type `transferred` with
  `from_group` → `group` (new nullable field); the student row is never
  re-created, the status does not change.
* Group creation and edits, student creation and edits, transfers, lesson
  moves and schedule changes are also written to
  Django's admin history (`LogEntry`), shown on the group / student pages.

## Endpoints

| Method | Path | |
|---|---|---|
| GET | `dashboard/` | cards, today's lessons, attention items, recent activity (admin history + status events) |
| GET | `options/` | courses (+subjects), trainers, rooms, open groups, weekdays, reasons |
| GET | `search/?q=` | global search (header / Ctrl+K): students, groups, trainers, the coming week's lessons |
| GET, POST | `groups/` | list (`status=active\|archived\|all`, `search`, `course`, `teacher`, `day`, `page`) / create |
| GET, PATCH | `groups/<id>/` | detail (programs, students, lessons, exams, surveys, history) / edit |
| POST | `groups/<id>/students/` | add existing students |
| POST | `groups/<id>/programs/` | create / change a program's trainer, subject and slots |
| POST | `groups/<id>/generate-lessons/` | generate / sync lessons |
| GET, POST | `students/` | list (`status=all\|active\|inactive\|paused\|archived`, `search`, `group`, `course`, `teacher`, `no_group`) / add |
| GET, PATCH | `students/<id>/` | profile / contacts |
| POST | `students/<id>/deactivate/`, `activate/`, `transfer/` | status and group actions |
| POST | `students/bulk/` | `transfer`, `add_to_group`, `deactivate`, `activate` — result per student |
| GET | `schedule/?start=&end=` | lessons (≤ 62 days; `group`, `teacher`, `course`, `day`) + weekly slot conflicts |
| POST | `lessons/<id>/move/`, `lessons/<id>/cancel/` | |
| GET | `attendance/?date=` | the day's lessons with rosters and marks (`unmarked=1`: last 3 days' lessons nobody marked) |
| POST | `attendance/lessons/<id>/` | mark / correct — **Admin only** (Assistant: 403) |
| GET | `groups/<id>/attendance/` | summary, held lessons with counts, students' % and absence streaks (`period=today\|week\|month\|all\|custom` + `start`/`end`, `student`, `teacher`, `status=present\|absent\|late\|unmarked`) |
| GET | `groups/<id>/homework/` | KPIs + homework rows (same period / `teacher` filters, `status=open\|review\|complete\|missing`) |
| GET | `lessons/<id>/` | lesson details: roster with marks + the lesson's homework |
| GET | `homework/<id>/` | homework details: every student's result (status, submitted / checked, score, comment) |
| GET | `control/` | «Контроль активности» (`period=7d\|14d\|30d\|month\|all`, default `30d`; `group`, `category`, `sort`) |
| GET | `control/students/<id>/` | one student's risk profile and timeline (`period`) |
| GET | `reports/monthly/?year=&month=` | «Месячный отчёт» (default: current month; a future month → 400) |
| GET | `reports/monthly/<year>/<month>/pdf/` | the same report as an A4 PDF, `monthly_report_<month>_<year>.pdf` |
| GET | `scholarships/` | periods with awards |
| POST | `scholarships/generate/` | form the latest cycle's period |
| GET, POST | `scholarships/periods/<id>/awards/` | eligible candidates / add an award (draft period) |

## Not implemented (no backend module yet)

* **Events** and **notifications**: the academy has no event or notification
  model. They are left out of the navigation instead of shipping
  placeholders; they belong here once such a module exists.
* Student «parent name» and group «level»: the models have no such fields,
  so the forms don't ask for them.
