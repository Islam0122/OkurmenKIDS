# Parallel lessons (shared classroom sessions)

Several groups study **at the same time, in one room, with one shared
trainer**. It is ONE actual lesson session, not N independent lessons.

Example: Room 101, 26 November, 15:00–16:00, trainer Islam, groups Python A,
Python B, Frontend A and English A.

## Architecture: what is reused, what is new

The feature is built on the existing academy models. It adds two small
tables and one nullable column, and nothing else.

| Concern | Existing entity reused |
|---|---|
| Groups / students | `academy.Group`, `academy.Student` (unchanged) |
| Trainer | `users.Teacher` |
| Classroom | `academy.Room` |
| Each group's lesson | `academy.Lesson`, one row per participating group, in the group's own program (`GroupTeacher`) |
| Attendance | `academy.Attendance` on that group's lesson, written by `services.attendance_service.bulk_mark_attendance` |
| Homework / results | `academy.Homework` / `HomeworkResult` on that group's lesson |
| Lesson lifecycle | `services.lesson_lifecycle` (start / complete rules per group) |
| Conflicts | `services.schedule_board.find_conflicts`, the one check the schedule board and lesson moves use |
| History | Django admin `LogEntry`, as `services.lesson_move` already does |
| Payroll | `apps.accounting.services.cycles`, unchanged |
| Roles | `users.permissions` (`can_run_operations`, `can_view_academy`, `is_admin_user`) |

### New models (migration `academy/0030_parallel_sessions`)

* **`ParallelSession`** holds what is shared: `teacher`, `room`, optional
  `subject`, `date`, `start_time`, `end_time`, `topic`, `description`, `notes`,
  `youtube_url`, `presentation_urls`, `status` (scheduled / in_progress /
  completed / cancelled), `cancellation_reason`, who created, completed and
  cancelled it, and when. A DB check constraint enforces `end_time > start_time`.
* **`ParallelSessionGroup`** stores participation history: `session`, `group`,
  the group's current `lesson`, `status` (active / removed), `students_count`
  (a snapshot taken at completion), who added or removed the group, when, and
  why. It has a unique constraint on `(session, group)`, so a group can't take
  part twice. Adding a removed group back re-activates the same row.
* **`Lesson.parallel_session`** is a nullable FK with `PROTECT`. A partial
  unique constraint `unique_active_parallel_session_group_lesson` allows only
  one live (not cancelled) lesson per `(session, group)`.

The migration is additive only. Existing rows get `parallel_session = NULL`
and behave exactly as before, so no data migration is needed and rollback
is safe.

### The groups' lessons

`services.parallel_sessions` creates one regular `Lesson` per group:

* **Program.** The lesson belongs to the group's own active `GroupTeacher`.
  If the trainer teaches in the group, that program is used. Otherwise the
  service picks the program for the session's `subject`, or the group's only
  program. If the choice is still ambiguous it asks for a subject or an
  explicit `programs` entry.
* **Trainer.** `Lesson.teacher` is the session's trainer. This is the same
  mechanism the LMS already uses for substitute trainers. No teacher
  assignment is created as a side effect.
* **Number.** `lesson_number` goes past both the program's existing lessons
  and its plan. The generator only creates lessons for plan rows, so it never
  claims or skips this number.
* **`schedule_overridden=True`.** Slot edits, «Сгенерировать занятия» and
  subject re-planning never move the lesson.
* **Topic and materials** are copied from the session. A later session edit
  copies them again.

Existing services were taught to respect the link:

* `lesson_move.move_lesson` refuses to move a session's lesson on its own.
* The `PATCH /lessons/{id}/` endpoint refuses to change date, time or room.
* `lesson_reschedule.cancel_and_reschedule` refuses to cancel a session's
  lesson on its own. Cancel the session, or remove the group instead. The
  topic shift chain never moves session lessons.
* `subject_start` treats session lessons as fixed.
* `schedule_board.period_conflicts` lets the lessons of one session occupy
  their trainer and room once, so they never flag each other. Clashes with
  anything else are still reported, with every member lesson listed.

## Business rules

* **No limit** on the number of groups. Classroom capacity is not validated.
* **Conflicts.** The trainer, the room and each group must be free. Two
  intervals overlap when `start_a < end_b and start_b < end_a`: 15:00–16:00
  and 15:30–16:30 conflict, while 15:00–16:00 and 16:00–17:00 do not. The
  check runs against every live `Lesson`, so regular lessons and other
  sessions' lessons are covered by the same rule. It also runs against open
  `ParallelSession` rows, because a session whose groups were all removed
  still holds its trainer and room. Moving a regular lesson into a session's
  time is refused by the same check. No module can bypass it.
* **Concurrency.** Every write runs in one transaction. It first takes
  `SELECT … FOR UPDATE` locks on the trainer, the room and every group, in a
  fixed order (trainers, then rooms, then groups, each by pk), so two writers
  can't deadlock. Two sessions sharing any resource are serialised, and the
  second one sees the first one's lessons. The group lock is the same one
  lesson generation and rescheduling take.
* **Edit.** Date, time, room and trainer can change only while the session is
  scheduled. Conflicts are re-checked and every group's lesson is updated.
  Content (topic, description, notes, materials) can change until the session
  is completed or cancelled.
* **Groups.** You can add a group only to a scheduled session, after a
  conflict check for that group. Removing a group cancels its lesson (never
  deletes it, and keeps its attendance and homework) and marks the
  participation «removed». The last group can't be removed: cancel the
  session instead. A completed or cancelled session's participation is
  frozen.
* **Start / complete.** `start` starts every group's lesson. `complete`
  completes every group's lesson under the regular rules: attendance marked
  for every student, and homework added or «ДЗ не требуется». It is all or
  nothing: if one group isn't ready, nothing completes and the missing items
  are listed per group. Completing again does nothing.
* **Cancel** cancels every group's lesson with no topic shifting, because the
  session is an extra lesson of each program. A completed session can't be
  cancelled. Cancelling again does nothing.
* **Attendance** is stored per group on that group's lesson. A student of
  another group is refused, and marking again updates the record rather than
  creating a duplicate. The statuses are present, absent, late and excused.
  The regular `/lessons/{id}/attendance/` endpoint keeps working for each
  group's lesson.
* **Homework.** «Shared homework» creates one regular `Homework` per group's
  lesson, or only for the listed groups (group-specific). Each group's lesson
  can also get its own homework through the regular homework API.

## Payroll integration

Payroll was inspected before implementation. There is no per-lesson pay in
this LMS. The two salary types are a fixed salary and a **percent of the
course price, paid per completed block (cycle) of a group and subject**:

    students × tariff × percent / 100 × (trainer's lessons / lessons in the cycle)

Cycles count each group's completed `Lesson` rows (`cycles.counted_lessons`).

How the session fits into that:

* A session gives **each participating group exactly one lesson** in its own
  cycle. This is the group's real course progress, and the partial unique
  constraint makes it impossible to count it twice.
* Re-saving or re-completing the session never creates extra `CycleLesson`
  or `CycleAccrual` rows. The existing per-(cycle, employee) uniqueness and
  idempotent sync are untouched.
* Salary rules, payroll periods, payment triggers and the accountant's
  workflow are **unchanged**. A trainer who gives a session to another
  trainer's group is credited in that group's cycle like any substitute
  trainer, with the share of the group's own tuition defined by the course's
  existing `trainer_split_rule` (or reviewed by the accountant under
  `REVIEW`). No new payment is generated, and no group's money is counted
  twice.
* The trainer's **workload counters** count the session **once**: the
  analytics workload (`analytics/teachers._workload`), the trainer's monthly
  report (`lessons_total`, `lessons_completed`), the schedule board legend,
  and `/parallel-lessons/analytics/`. The helper is
  `parallel_sessions.teaching_occasions`. Per-group figures still show one
  lesson for each group.

Tests: `apps/accounting/tests/test_parallel_payroll.py`.

## API

Base path: `/api/v1/parallel-lessons/` (DRF router, tag «Parallel lessons» in
Swagger).

| Method & path | Who | What |
|---|---|---|
| `GET /` | all below (trainer: own) | List. Filters: `date`, `date_from`, `date_to`, `teacher`, `room`, `group`, `status`, `page` |
| `POST /` | Admin, Assistant | Create `{teacher, room, date, start_time, end_time, groups: [ids], subject?, topic?, description?, notes?, youtube_url?, presentation_urls?, programs?: {group_id: program_id}}` |
| `GET /{id}/` | read | Details, including `groups` (with removed ones), `groups_count`, `students_count` and `capabilities` |
| `PATCH /{id}/` | Admin, Assistant | Edit (rules above) |
| `POST /check/` | Admin, Assistant | Conflict preview `{teacher, room, date, start_time, end_time, groups, session?}` returns `{ok, conflicts}` |
| `POST /{id}/start/` | trainer, Admin | Start |
| `POST /{id}/complete/` | trainer, Admin | Complete. A 400 response's `completion` lists what each group is missing |
| `POST /{id}/cancel/` | Admin, Assistant | Cancel `{reason?}` |
| `GET /{id}/groups/` | read | Participation rows |
| `POST /{id}/groups/` | Admin, Assistant | Add `{group, program?}` |
| `DELETE /{id}/groups/{group_id}/` | Admin, Assistant | Remove `{reason?}` |
| `GET /{id}/attendance/` | read | Students grouped by group, with their marks |
| `POST /{id}/attendance/` | trainer, Admin | Mark one group `{group, entries: [{student, status, comment?}]}` |
| `GET /{id}/homework/` | read | Homework of every group's lesson |
| `POST /{id}/homework/` | trainer, Admin | Shared or group-specific homework `{title, description?, deadline?, groups?}` |
| `GET /{id}/statistics/` | read | Per group and in total: students, attendance by status, rate, homework |
| `GET /{id}/history/` | read | Change log |
| `GET /analytics/?start&end&teacher` | read (trainer: own) | Totals, trainer workload, attendance by group, sessions |
| `GET /options/` | read | Trainers, rooms, open groups (with student counts), subjects |

The schedule board (`GET /api/v1/schedule/board/`) now returns
`parallel_session: {id, groups_count}` on each lesson and
`stats.parallel_sessions`, and the lessons API returns `parallel_session`
(an id or null). Both are additive fields.

## Permissions

These are the existing roles; no new permission system was added.

* **Admin** can do everything.
* **Assistant** creates, edits and cancels sessions and adds or removes
  groups. It stays read-only on attendance and homework, the same rule as
  `IsAdminOrOwningTeacher`.
* **Team Lead** reads every session and never writes.
* **Trainer** reads only the sessions they give, marks attendance, adds
  homework, and starts or completes their own sessions.
* **Accountant, Director and other roles** have no access. Payroll reads the
  groups' lessons as before.

## Frontend (`frontend/`)

* Pages: `features/parallelLessons/` contains the list (stats, filters,
  trainer workload), the create/edit modal (live conflict preview, any number
  of groups), and the session page (info, per-group attendance, homework,
  statistics, groups, history).
* Routes: `/app/parallel-lessons[/:id]` for Admin, Team Lead and Trainer,
  and `/assistant/parallel-lessons[/:id]` for Assistant and Admin. Navigation
  entries are in `navItems.ts`, `teamLeadNav.ts` and `assistantNav.ts`.
* Calendar: on the existing schedule board, a session's lessons carry a
  layers icon and a dashed outline, and the lesson modals link to the
  session. In the Assistant's lesson modal, move and cancel are hidden for
  such lessons. A trainer's own schedule cards show the icon and open the
  session.

## Known limitations

* The conflict check works on concrete dated lessons. A weekly slot whose
  lessons haven't been generated yet is only protected when its lessons are
  generated: the generator skips occupied trainer, room and group times.
* `move_lesson` and the lessons `PATCH` endpoint don't take row locks
  (they didn't before this feature either). The window for a race between
  them and a session write is small but not zero. Session writes themselves
  are fully serialised.
* There is no capacity check, by design.
* The Director role has no read access. Its existing scope (`/accounting`)
  was left as is.
