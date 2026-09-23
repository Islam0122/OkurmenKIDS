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

Who teaches a generated lesson is decided by the **subject** of its lesson
plan row, not by who owns the weekly slot it lands in:

- `POST /api/v1/programs/` with `{group, teacher, subject}` (no schedule
  needed) assigns a trainer to a subject in a group. The trainer must be an
  active account with the Trainer role, and the subject must belong to the
  group's course.
- `GET /api/v1/groups/{id}/subject-assignments/` lists every subject of the
  course plan with its trainer(s) and a `status`: `assigned`, `multiple`,
  `legacy_slot` (covered by an old subject-less slot's teacher) or
  `unassigned`.
- `POST /api/v1/groups/{id}/generate-lessons/` (admin only) is the **only**
  way lessons are generated — saving schedule slots no longer triggers it.
  It is idempotent (201 when something was created, 200 for a no-op
  re-run, 400 when nothing could be generated because of an error). Lessons
  of a subject with no trainer are *not* created and not given to anyone
  else; their dates are kept free, the response's `warnings` names them,
  and a re-run after assigning the trainer fills exactly those dates.
  Response: `created_count`, `first_lesson`, `last_lesson`, `first_date`,
  `last_date`, `already_existed`, `expected_total`, `missing_count`,
  `conflicts`, `warnings`, `errors`.
- `GET /api/v1/lessons/` additionally filters by `room` and `teacher`
  (the lesson's effective trainer; for a trainer it only ever narrows their
  own lessons).

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
