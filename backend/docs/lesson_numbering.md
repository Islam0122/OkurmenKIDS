# Educational month and lesson — «3 месяц · 5 урок»

One service computes every lesson's educational month and lesson number:
`apps/academic_progress/numbering.py`. Every API payload carries its result
as `numbering` (`lesson_numbering` on homework / attendance rows):
`{number, month, lesson, per_month, subject_id, label, labels: {ru, ky, en}}`.

| Language | Format |
| --- | --- |
| Russian | `3 месяц · 5 урок` |
| Kyrgyz | `3-ай · 5-сабак` |
| English | `Month 3 · Lesson 5` |

## Where the numbers come from (audit)

* `Lesson.lesson_number` is **not** the lesson's number in its subject. A
  lesson generated from the group's shared course plan carries the plan row's
  number, and `CourseLessonPlan` is numbered once per course across all
  subjects. In a plan that interleaves IT, Soft Skills and English, IT lesson
  29 is row 85 — the first version of this feature split 85 into months and
  showed «Month 8 · Lesson 1». It is never used for display.
* **Position in the subject** — the lesson's rank among the plan rows of its
  own subject:
  * shared course plan (`Lesson.plan`): rank among the course's rows of that
    subject, ordered by row number;
  * a program's own plan (`Lesson.individual_plan`): rank in that plan;
  * no plan link (row deleted, lesson made by hand): the plan row of the same
    subject and number, if any.
  Otherwise the curriculum does not say, and **no number is shown** (nothing
  is invented). IT, English, Soft Skills and every other subject are separate
  sequences. A cancelled lesson and its make-up keep their plan row.
* **Educational month** — from the program's study months («Учебные месяцы»,
  `ProgramCurriculum` / `CurriculumMonth`), never from dates:
  * a subject named in the study months (main subject, or a month's own
    subject) follows those months: their numbers and lesson counts (e.g.
    React in months 4–6 starts at «4 месяц · 1 урок»; a month planned with 10
    lessons is 10 long);
  * every other subject (English, Soft Skills…) is split into months of the
    group's lessons per month — its own (12 / 20, «Нумерация уроков» on the
    group page), else the program's, else 12.
  Lessons beyond the planned months continue with the same size.

## Changing settings never renumbers the past

Any change of the lessons per month or of the study months — program API,
Django admin form, group setting — runs inside `numbering.preserving()`:
before, it notes every subject's last lesson already held (or dated today)
and its months; after, whatever would move is frozen as it was
(`NumberingFreeze`: group + subject + positions + month + size). The change
applies from the next educational month. Frozen ranges are listed on the
group card. Migration `0003_freeze_by_subject` converted freezes of the first
version (written in course-wide numbers) to subject positions.

Performance: one resolver per request (`NumberingMiddleware`); the curriculum
and plan ranks are read once per group/course.
