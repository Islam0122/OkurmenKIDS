"""Academy Health — a single calculated score, never persisted (spec §7:
"This MUST NOT be stored in the database").

Formula (equal-weight average of five 0-100 components, documented here
since nothing else records it):

- **attendance**      = attendance_rate for the period.
- **homework**         = homework submission_rate for the period.
- **lesson_completion** = lesson_completion_rate for the period.
- **retention**        = 100 * active_students / total_students — how much
  of everyone ever registered (in scope, as of the period) is still active.
  0 total students reads as a perfect 100 (nothing to retain, not a
  penalty).
- **teacher_workload** = 100 * teachers_with_lessons / active_teachers —
  how many of the active teachers in scope actually taught during the
  period, as a crude balance/engagement signal. 0 active teachers reads as
  100 for the same reason.

``score`` is the unweighted mean of the five, rounded to the nearest whole
number. ``level`` buckets it: >=85 "excellent", >=70 "good", >=50 "fair",
else "poor" — thresholds are a starting point, easy to retune in one place.
"""
from __future__ import annotations

_LEVEL_THRESHOLDS = (
    (85, "excellent"),
    (70, "good"),
    (50, "fair"),
)


def _level_for(score: float) -> str:
    for threshold, label in _LEVEL_THRESHOLDS:
        if score >= threshold:
            return label
    return "poor"


def build(sections: dict) -> dict:
    students = sections["students"]
    teachers = sections["teachers"]

    attendance = sections["attendance"]["attendance_rate"]["value"]
    homework = sections["homework"]["submission_rate"]["value"]
    lesson_completion = sections["lessons"]["lesson_completion_rate"]["value"]

    total_students = students["total_students"]["value"]
    active_students = students["active_students"]["value"]
    retention = round(active_students / total_students * 100, 1) if total_students else 100.0

    active_teachers = teachers["active_teachers"]["value"]
    teachers_with_lessons = teachers["teachers_with_lessons"]["value"]
    teacher_workload = round(teachers_with_lessons / active_teachers * 100, 1) if active_teachers else 100.0

    components = {
        "attendance": attendance,
        "homework": homework,
        "lesson_completion": lesson_completion,
        "retention": retention,
        "teacher_workload": teacher_workload,
    }
    score = round(sum(components.values()) / len(components))

    return {
        "score": score,
        "level": _level_for(score),
        "components": components,
    }
