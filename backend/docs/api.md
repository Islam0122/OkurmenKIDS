# API structure

Every endpoint lives under one flat `/api/v1/` namespace — no `academy/` or
`users/` app-name segment in the URL. `apps/users/urls.py` and
`apps/academy/urls.py` are both mounted at that same prefix
(`config/urls.py`); which Django app happens to own a resource is an
implementation detail, never part of its URL.

| Prefix | Resource | Owning app |
|---|---|---|
| `/api/v1/auth/` | `login/`, `refresh/`, `me/` | users |
| `/api/v1/trainers/` | Teacher accounts (`me`, `verify`, `export`, `import`, `import/preview`) | users |
| `/api/v1/subjects/` | Subject catalogue | users |
| `/api/v1/groups/` | Groups (`schedule`, `students`, `generate-lessons`, `subject-assignments` actions) | academy |
| `/api/v1/programs/` | GroupTeacher — one Teaching Program (teacher + subject + schedule + lesson plan + lessons); also the group's subject → trainer assignment | academy |
| `/api/v1/program-lesson-plans/` | GroupTeacherLessonPlan — a program's own lesson-by-lesson plan | academy |
| `/api/v1/schedules/` | GroupSchedule — a program's weekly recurring slots | academy |
| `/api/v1/lessons/` | Generated lessons (`attendance` action) | academy |
| `/api/v1/attendance/` | Attendance records | academy |
| `/api/v1/homework/` | Homework assignments (`results` action) | academy |
| `/api/v1/homework-results/` | Per-student homework results | academy |
| `/api/v1/courses/` | Course catalogue (`lesson-plans` action) | academy |
| `/api/v1/course-lesson-plans/` | CourseLessonPlan — a course's shared template | academy |
| `/api/v1/students/` | Students (`export`, `import`, `import/preview`) | academy |
| `/api/v1/rooms/` | Rooms (`available` action) | academy |
| `/api/v1/analytics/dashboard/` | KPI dashboard (period/compare/teacher/group/course/subject filters) | academy |
| `/api/v1/availability/` | Which teachers are free for a given date + time window | academy |

`GroupTeacher` is the "Teaching Program" concept described in the domain
architecture — deliberately named `programs` in the URL (not
`group-teachers`) to read the way the rest of the system talks about it:
a Group has several independent Programs, each with one Teacher, one
Subject, its own Schedule, its own Lesson Plan, and its own Lessons.

## Lesson generation and trainer assignment

A group has one shared course plan (e.g. 144 rows: IT 48 + Soft Skills 48 +
English 48) and one program (`/programs/`, GroupTeacher = trainer +
subject) per subject, each with its own weekly slots (`/schedules/`). The
plan is split **by subject**: each subject's rows are generated only into
that subject's own program slots, with that program's trainer — 144 is the
group's total, never 144 per program.

- `GET /api/v1/groups/{id}/subject-assignments/` lists every subject of the
  course plan: `plan_lessons` (its share of the plan), `generated_lessons`,
  trainer(s) and `status` — `assigned`, `multiple`, `legacy_slot` (taught in
  an old subject-less slot), `individual` (the program uses its own plan)
  or `unassigned` (no program with a schedule: its lessons are not generated).
- `POST /api/v1/groups/{id}/generate-lessons/` (admin only) is the **only**
  way lessons are generated — saving schedule slots no longer triggers it.
  It is idempotent (201 when something was created, 200 for a no-op
  re-run, 400 when nothing could be generated because of an error). A
  subject without a program schedule is not generated and not moved into
  another subject's slots; the response's `warnings` names it and a re-run
  after adding its program fills it in without touching anything else.
  Response: `created_count`, `first_lesson`, `last_lesson`, `first_date`,
  `last_date`, `already_existed`, `expected_total`, `missing_count`,
  `conflicts`, `warnings`, `errors`.
- A program with its own individual plan (`/program-lesson-plans/`) is
  numbered 1..N on its own slots; the shared plan's rows for its subject
  are then not used.
- `GET /api/v1/lessons/` additionally filters by `room` and `teacher`
  (the lesson's effective trainer; for a trainer it only ever narrows their
  own lessons).

## Cancelling a lesson (topic reschedule)

`POST /api/v1/lessons/{id}/cancel/` with `{"reason": "...", "reschedule": true}`
(`reschedule` defaults to true) cancels the lesson and moves its topic to
the program's next lesson date: a new make-up lesson (same topic/plan/
lesson_number, `rescheduled_from` = the cancelled lesson) takes the date of
the program's next open lesson, every later open lesson (scheduled, never
started) of the same program shifts one date forward, and the last one
moves to the program's next free slot. Completed/in-progress lessons and
the cancelled lesson itself never move; attendance and graded homework stay
where they are. The response is the cancelled lesson (with `rescheduled_to`)
plus a `reschedule` object: `makeup_lesson`, `makeup_date`, `shifted`,
`created`, `warning`. Repeating the call never shifts anything twice.
`POST /api/v1/lessons/{id}/reschedule/` retries the move for an already
cancelled lesson (e.g. after `reschedule: false`, or when no free date was
left before the group's end date).

Existing data produced by the old behaviour can be audited (read-only) and,
per group, rebuilt with `python manage.py repair_group_lessons` — see that
command's docstring.

## Cross-cutting behavior

- **Serializers / validation**: every writable resource validates
  ownership and cross-model consistency at the serializer level (e.g. an
  Attendance/HomeworkResult's `student` must belong to the same Group as
  its Lesson/Homework) — see `apps/academy/serializers.py`.
- **Filters**: list endpoints use `django-filter` (`filterset_class`/
  `filterset_fields`) plus DRF's `SearchFilter`/`OrderingFilter` — see
  `apps/academy/filters.py`.
- **Pagination**: `PageNumberPagination`, 20 per page by default
  (`REST_FRAMEWORK["PAGE_SIZE"]`), same shape (`count`/`next`/`previous`/
  `results`) on every list endpoint.
- **Permissions**: `IsAdminOrReadOnly` (admin writes, any authenticated
  user reads) for reference/catalogue data; `IsAdminOrOwningTeacher` (admin
  full access, a teacher only their own Teaching Program's data) for
  Lesson/Attendance/Homework/HomeworkResult — see `apps/academy/
  permissions.py`. Every queryset is scoped a second time in
  `get_queryset()`, independent of the permission class — see the
  Permissions section of this repo's architecture notes for the full IDOR
  analysis.
- **OpenAPI documentation**: generated by drf-spectacular —
  `/schema/` (raw schema, publicly reachable by design, same as
  `/swagger-ui/`/`/redoc/` — API documentation, not API data), `/swagger-ui/`,
  `/redoc/`. Validate it with `python manage.py spectacular --fail-on-warn`
  before shipping a URL/serializer change; a naming collision (e.g. two
  actions producing the same operationId) fails that command even though
  it wouldn't break the API itself.
- **Response format**: JSON only (`DEFAULT_RENDERER_CLASSES`), consistent
  error shape from DRF's own exception handling (`{"detail": "..."}` for
  simple errors, `{"field": ["..."]}` for validation errors).

## Renaming history

This flat structure replaces an earlier `/api/v1/academy/...` +
`/api/v1/users/...` nesting. Alongside the flattening, a few resources were
also renamed for consistency: `group-schedules` → `schedules`,
`group-teachers` → `programs`, `group-teacher-lesson-plans` →
`program-lesson-plans`, `homeworks` → `homework`, `subject` → `subjects`,
`teacher-availability` → `availability`. There is no backward-compatible
alias for the old paths — every consumer (this repo's own frontend
included) was updated in the same change.
