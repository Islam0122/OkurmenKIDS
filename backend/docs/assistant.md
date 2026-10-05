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
| Attendance | `attendance_service.bulk_mark_attendance` |
| Scholarships | `scholarships.services.generation.generate_period` / `add_award` (approval and payment stay Admin's) |

## History / audit

* A transfer is a `StudentStatusEvent` of type `transferred` with
  `from_group` → `group` (new nullable field); the student row is never
  re-created, the status does not change.
* Group creation and edits, student creation and edits, transfers, lesson
  moves, schedule changes and attendance corrections are also written to
  Django's admin history (`LogEntry`), shown on the group / student pages.

## Endpoints

| Method | Path | |
|---|---|---|
| GET | `dashboard/` | cards, today's lessons, attention items |
| GET | `options/` | courses (+subjects), trainers, rooms, open groups, weekdays, reasons |
| GET, POST | `groups/` | list (`status=active\|archived\|all`, `search`, `course`, `teacher`, `page`) / create |
| GET, PATCH | `groups/<id>/` | detail (programs, students, lessons, exams, surveys, history) / edit |
| POST | `groups/<id>/students/` | add existing students |
| POST | `groups/<id>/programs/` | create / change a program's trainer, subject and slots |
| POST | `groups/<id>/generate-lessons/` | generate / sync lessons |
| GET, POST | `students/` | list (`status=all\|active\|inactive\|paused\|archived`, `search`, `group`, `course`, `teacher`, `no_group`) / add |
| GET, PATCH | `students/<id>/` | profile / contacts |
| POST | `students/<id>/deactivate/`, `activate/`, `transfer/` | status and group actions |
| POST | `students/bulk/` | `transfer`, `add_to_group`, `deactivate`, `activate` — result per student |
| GET | `schedule/?start=&end=` | lessons (≤ 62 days) + weekly slot conflicts |
| POST | `lessons/<id>/move/`, `lessons/<id>/cancel/` | |
| GET | `attendance/?date=` | the day's lessons with rosters and marks |
| POST | `attendance/lessons/<id>/` | mark / correct |
| GET | `scholarships/` | periods with awards |
| POST | `scholarships/generate/` | form the latest cycle's period |
| GET, POST | `scholarships/periods/<id>/awards/` | eligible candidates / add an award (draft period) |

## Not implemented (no backend module yet)

* **Events** and **notifications**: the academy has no event or notification
  model. They are left out of the navigation instead of shipping
  placeholders; they belong here once such a module exists.
* Student «parent name» and group «level»: the models have no such fields,
  so the forms don't ask for them.
