# Импорт данных (admin bulk Excel import/export)

One admin dashboard — **Django Admin → Система → Импорт данных**
(`/admin/academy/import-data/`) — for downloading Excel templates, bulk
importing data from `.xlsx`/`.csv`, and exporting existing data back out.
Admin-only (`is_superuser` or `role == "admin"`); any other user, including
a `is_staff` teacher account, gets `403`.

It's a thin presentation layer over the same services the pre-existing
per-model Student/Teacher import screens already used — no import logic is
duplicated:

| Entity | Service | Upsert key |
|---|---|---|
| Студенты | `apps.academy.services.import_export` | `id` (optional column — see below) |
| Тренеры | `apps.users.import_export.teachers` | `username` or `email` |
| Группы | `apps.academy.services.group_import_export` | `name` (unique) |

Расписание (`apps.academy.services.schedule_export`) is **export-only** —
`GroupSchedule` rows carry live teacher/room conflict checks and an
auto-derived `group_teacher` link (see `models.GroupSchedule.clean`/
`save()`), which makes a safe bulk-import path meaningfully riskier than a
plain field upsert; the feature deliberately stops at export for that
entity rather than build an under-tested importer for it.

## Supported file formats

`.xlsx` and `.csv` (UTF-8, with a BOM so Excel doesn't mangle Cyrillic on
Windows). The first row is always the header; blank rows are skipped.
Uploading anything else is rejected before any row is read.

## Import behavior

- **Preview first**: every import form has a "Предпросмотр" button that
  runs full validation and shows the same row-by-row report the real
  import would, without writing anything.
- **Transactional**: a file with *any* invalid row saves *nothing* — one
  bad row never lets the rest of the file through.
- **Idempotent by design**: reimporting the same file twice never creates
  duplicates — each entity's upsert key (table above) decides create vs.
  update.
- **Foreign keys are looked up by name, never auto-created**: a `group`/
  `course`/`subject` column that doesn't match an existing record fails
  that row with a clear error instead of silently creating a new one.
- **Duplicate rows inside one file** (same upsert key appearing twice) are
  rejected with a "Строка N — дублирующ..." error, not silently merged.

### Students (`Студенты`)

Columns: `id` (optional — see below), `first_name` (required), `last_name`,
`phone`, `parent_phone`, `group`, `is_active`.

- Student has no safe unique business field (first/last name collisions
  happen), so `id` is the only supported update key: leave it empty to
  create a new student, or set it to an existing student's id to update
  them.
- `group` matches an existing `Group` by exact name; unmatched → row error.
- `phone`/`parent_phone` must look like a phone number (digits, spaces,
  `+`, `-`, `()`, 5–30 chars) if given.
- `is_active` accepts да/нет, true/false, yes/no, 1/0 (empty = true).

### Teachers (`Тренеры`)

Columns: `username` (required), `email` (required), `first_name`
(required), `last_name`, `phone`, `position`, `experience_years`, `bio`,
`hire_date` (`ГГГГ-ММ-ДД`), `subjects` (comma-separated existing Subject
names), `is_active`, `is_verified`, `password`.

- Update key: an existing `User` matched by `username` **or** `email`.
- `password` only matters on create (hashed via `set_password`); if empty
  a random password is generated. Never exported back out.
- A row can't be used to promote/demote an existing non-Teacher user's
  role — that's rejected as a row error.

### Groups (`Группы`)

Columns: `name` (required, unique — the update key), `course` (required,
exact existing Course name), `status` (`active`/`paused`/`completed`/
`cancelled`, or the Russian label — case-insensitive; empty = `active`),
`start_date` (required, `ГГГГ-ММ-ДД`), `end_date`, `max_students`,
`description`.

- `Group.name` is already unique on the model, so it's the upsert key —
  no invented identifier needed.
- `course` is looked up by exact name; never created implicitly.

## Excel templates

Each template (`Скачать шаблон` → pick a type) is a real, generated
`.xlsx` with two sheets:

- **Данные** — the exact header row the importer reads (column keys, not
  translated labels — a template downloaded and reuploaded unmodified must
  round-trip), one example row below it, a frozen header, and a coloured
  header cell per column (darker = required) with a hover comment
  explaining that column.
- **Инструкция** — a full legend: which columns are required, an example
  value and description for each, the entity's create/update strategy, and
  the shared format rules (dates, booleans, phone numbers).

## Export

- **Экспорт студентов** reuses the existing `admin:academy_student_export`
  endpoint (also used by the Student changelist's own Import/Export
  buttons).
- **Экспорт групп** — name, course, status, dates, capacity, description,
  active student count, created date.
- **Экспорт расписания** — group, teacher, subject, day of week, start/end
  time, room, active status (every `GroupSchedule` row, active and
  inactive alike).

All three support `?format=xlsx` (default) or `?format=csv`.

## Errors

A validation error always names the row and the reason, e.g.:

```
Строка 4 — Группа "Python-01" не найдена.
Строка 8 — Поле first_name обязательно.
Строка 11 — Дублирующееся название группы «JS-02» в файле (строка 9).
```

No raw traceback is ever shown for bad user input; only Django/system
errors outside the importer's control would surface as a 500.
