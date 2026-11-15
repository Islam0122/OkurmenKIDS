# Monthly lesson numbering — «Месяц 2 · Урок 1»

Lessons are shown by **educational month** and **lesson in that month**
instead of a running number. Code: `apps/academic_progress/numbering.py`.

## Rules

* The stored `Lesson.lesson_number` stays the internal, global sequence (one
  sequence per `GroupTeacher` — each subject/trainer program of a group). It is
  never rewritten; a cancelled lesson keeps its number and its make-up re-uses
  it, so nothing after it shifts.
* Month and lesson are **derived**, not stored:

  ```
  month  = (n - 1) // lessons_per_month + 1
  lesson = (n - 1) %  lessons_per_month + 1
  ```

  12 per month: №12 → Месяц 1 · Урок 12, №13 → Месяц 2 · Урок 1.
  20 per month: №20 → Месяц 1 · Урок 20, №21 → Месяц 2 · Урок 1.
* An educational month is a number of lessons, **not a calendar month**.

## Configuration (12 or 20)

| Level | Where | Who |
| --- | --- | --- |
| Group (overrides the program) | `GroupLessonNumbering` — group page «Нумерация уроков», `PUT /api/v1/academic-progress/groups/<id>/numbering/` (`null` = as the program) | admin, operations director, team lead of the program |
| Program | `ProgramCurriculum.lessons_per_month` — «Настройки программ» | same |
| Default | 12 | — |

The study months of «Учебные месяцы» (progress) use the same value; a group's
own setting sizes every month of that group. A program saved earlier with
another number keeps it until it is changed (new values: 12 or 20 only).

## Changing the setting never renumbers what took place

On any change of a group's effective value (API or Django admin; signals in
`signals.py`), `freeze_history()` writes `NumberingFreeze` rows: for each
lesson sequence, the educational months up to the last lesson already held
(or dated today or earlier) are fixed with the **old** size — the started month
is finished as it began — and the new size applies from the next month on.
Sequences with nothing held yet simply follow the new value. Frozen ranges are
listed on the group card and read-only in admin.

## Where it appears

Every lesson payload carries `numbering` (`{number, month, lesson, per_month,
label}`; homework and attendance rows: `lesson_numbering`): the lesson API
(teacher schedule, lesson page, attendance), homework, the attendance matrix,
assistant records and schedule, «Контроль», the schedule board, student
progress, the operations academy cabinet, the student/parent portal
(dashboard, schedule, homework, attendance — RU «Месяц 2 · Урок 1», KY
«2-ай · 1-сабак»). Team Lead reports store it in their metrics snapshot, so a
saved report keeps the label it was written with. The frontend formats it with
`lib/lessonNumbering.ts` (`lessonLabel`).

Performance: one resolver per request (`NumberingMiddleware`) reads each
group's setting and frozen ranges once.
