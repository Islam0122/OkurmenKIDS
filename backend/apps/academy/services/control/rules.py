"""Control — "did the responsible trainer do everything a lesson requires?"

Pure per-lesson evaluation: no queries here, only the rules. `service.py`
loads the rows once and hands every Lesson's already-fetched data to
`evaluate_lesson`.

This is deliberately *not* a KPI (see services.kpi_engine): there is no
weighting, no attendance *rate*, no average score. Every number is "how many
of the required records exist", and every rule reuses a definition the
project already has:

* **Responsible trainer** — `Lesson.effective_teacher` (the lesson's own
  `teacher`, else its GroupTeacher's `teacher`), the same rule
  `LessonQuerySet.for_teacher` and `IsAdminOrOwningTeacher` use for write
  access. Never the logged-in user, never the legacy `Group.teacher`.
* **Held vs. upcoming** — `services.lesson_status`: a future date is never
  due; today's lesson is due once started, or once its slot is over
  (`attention_q`: still open AND already in the past).
* **Closed** — `Lesson.status == COMPLETED` (services.lesson_lifecycle).
* **Attendance filled** — `lesson_lifecycle.attendance_completed`: every
  *active* student of the group has an Attendance record.
* **Homework given** — `lesson_lifecycle.homework_satisfied`: a Homework
  row exists, or the lesson is explicitly marked "ДЗ не требуется".
* **Homework checked** — the Lesson list's operational status
  (frontend `useLessonOperationalStatus`): no active student's result is
  left in "Сдано"/"Сдано с опозданием" (handed in, not yet checked).
* **Scores** — `HomeworkResult.score` is the only grade in the LMS. A
  student counts as graded once their result has a score, or once the
  trainer explicitly recorded "Не сдано" (nothing to score). No result row
  at all means the trainer never graded that student.

Checking and scoring only become due once the homework's `deadline` has
passed (no deadline — due as soon as the lesson is held), the same
"overdue" rule the analytics insights use; before that the lesson reads
"ожидает срока сдачи", never as unfilled.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from apps.academy.models import HomeworkResult, Lesson

# -- lesson states ----------------------------------------------------------
STATE_DUE = "due"
STATE_UPCOMING = "upcoming"
STATE_CANCELLED = "cancelled"

# -- statuses (lesson rows and teacher×group rows) -------------------------
STATUS_OK = "ok"
STATUS_ATTENTION = "attention"
STATUS_NOT_FILLED = "not_filled"
STATUS_NO_DATA = "no_data"
STATUS_UPCOMING = "upcoming"
STATUS_CANCELLED = "cancelled"

STATUS_LABELS = {
    STATUS_OK: "OK",
    STATUS_ATTENTION: "Требует внимания",
    STATUS_NOT_FILLED: "Не заполнено",
    STATUS_NO_DATA: "Нет данных",
    STATUS_UPCOMING: "Предстоящий",
    STATUS_CANCELLED: "Отменён",
}

# "Problems first": the order rows are sorted in and the status filter offers.
STATUS_PRIORITY = {
    STATUS_NOT_FILLED: 0,
    STATUS_ATTENTION: 1,
    STATUS_OK: 2,
    STATUS_UPCOMING: 3,
    STATUS_NO_DATA: 4,
    STATUS_CANCELLED: 5,
}
FILTERABLE_STATUSES = (STATUS_NOT_FILLED, STATUS_ATTENTION, STATUS_OK, STATUS_UPCOMING, STATUS_NO_DATA)

# -- component levels (one cell of the table) ------------------------------
LEVEL_OK = "ok"
LEVEL_WARNING = "warning"
LEVEL_DANGER = "danger"
LEVEL_NONE = "none"  # nothing required in the period

# A component filled on at least this share of its lessons is a small gap
# (🟡); below it, a substantial one (🔴). 6/8 and 5/7 read as gaps, 4/6 and
# 4/8 as unfilled.
WARNING_THRESHOLD = 70.0
# A teacher×group row with this many 🔴 components is "Не заполнено".
NOT_FILLED_DANGER_COMPONENTS = 2

# -- per-component states of one lesson ------------------------------------
COMPONENT_OK = "ok"
COMPONENT_MISSING = "missing"
COMPONENT_PARTIAL = "partial"
COMPONENT_UNCHECKED = "unchecked"
COMPONENT_WAITING = "waiting"
COMPONENT_NOT_REQUIRED = "not_required"
COMPONENT_NO_STUDENTS = "no_students"
COMPONENT_NO_HOMEWORK = "no_homework"

# Handed in but not checked yet — the same pair the Lesson list treats as
# "Требуется проверка ДЗ".
PENDING_CHECK = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.LATE)


def percent(part: int, total: int) -> float | None:
    return round(part / total * 100, 1) if total else None


def component_level(completed: int, total: int) -> str:
    if not total:
        return LEVEL_NONE
    if completed >= total:
        return LEVEL_OK
    return LEVEL_WARNING if completed / total * 100 >= WARNING_THRESHOLD else LEVEL_DANGER


def lesson_state(lesson: Lesson, *, today: dt.date, now_time: dt.time) -> str:
    """Cancelled / upcoming / due — see `services.lesson_status`."""
    if lesson.status == Lesson.Status.CANCELLED:
        return STATE_CANCELLED
    if lesson.date > today:
        return STATE_UPCOMING
    if lesson.date == today and lesson.status == Lesson.Status.SCHEDULED and lesson.end_time > now_time:
        return STATE_UPCOMING
    return STATE_DUE


@dataclasses.dataclass(frozen=True)
class StudentRef:
    id: int
    name: str


@dataclasses.dataclass(frozen=True)
class HomeworkRef:
    id: int
    deadline: dt.date | None
    updated_at: dt.datetime


@dataclasses.dataclass(frozen=True)
class ResultRef:
    homework_id: int
    student_id: int
    status: str
    score: int | None
    updated_at: dt.datetime


@dataclasses.dataclass
class LessonCheck:
    lesson: Lesson
    state: str
    status: str
    students_total: int
    closed: bool
    attendance_state: str
    attendance_marked: int
    attendance_missing: list[StudentRef]
    homework_state: str
    homework_id: int | None
    homework_deadline: dt.date | None
    pending_check: int
    grades_state: str
    grades_required: int
    grades_missing: list[StudentRef]
    problems: list[str]
    notes: list[str]
    last_activity_at: dt.datetime | None

    # -- counted into the teacher×group row --------------------------------
    @property
    def is_due(self) -> bool:
        return self.state == STATE_DUE

    @property
    def attendance_counts(self) -> bool:
        return self.is_due and self.attendance_state not in (COMPONENT_NO_STUDENTS,)

    @property
    def attendance_ok(self) -> bool:
        return self.attendance_state == COMPONENT_OK

    @property
    def homework_counts(self) -> bool:
        return self.is_due and self.homework_state in (COMPONENT_OK, COMPONENT_MISSING, COMPONENT_UNCHECKED)

    @property
    def homework_ok(self) -> bool:
        return self.homework_state == COMPONENT_OK

    @property
    def grades_counts(self) -> bool:
        return self.is_due and self.grades_state in (COMPONENT_OK, COMPONENT_MISSING, COMPONENT_PARTIAL)

    @property
    def grades_ok(self) -> bool:
        return self.grades_state == COMPONENT_OK

    @property
    def grades_given(self) -> int:
        return self.grades_required - len(self.grades_missing)


def _fmt(day: dt.date) -> str:
    return day.strftime("%d.%m.%Y")


def _students_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "студент"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "студента"
    return "студентов"


def evaluate_lesson(
    lesson: Lesson,
    *,
    today: dt.date,
    now_time: dt.time,
    students: list[StudentRef],
    attendance: dict[int, dt.datetime],
    homeworks: list[HomeworkRef],
    results: list[ResultRef],
) -> LessonCheck:
    """Everything Control knows about one Lesson.

    `students` — the group's *active* students (inactive ones are never
    required); `attendance` — student id -> updated_at of this lesson's
    Attendance rows; `homeworks`/`results` — this lesson's Homework rows and
    their HomeworkResults.
    """
    state = lesson_state(lesson, today=today, now_time=now_time)
    student_ids = {s.id for s in students}
    problems: list[str] = []
    notes: list[str] = []

    # -- attendance ---------------------------------------------------------
    marked_ids = student_ids & set(attendance)
    attendance_missing = [s for s in students if s.id not in marked_ids]
    if not students:
        attendance_state = COMPONENT_NO_STUDENTS
    elif not attendance_missing:
        attendance_state = COMPONENT_OK
    elif marked_ids:
        attendance_state = COMPONENT_PARTIAL
    else:
        attendance_state = COMPONENT_MISSING

    # -- homework -------------------------------------------------------------
    deadlines = [hw.deadline for hw in homeworks if hw.deadline is not None]
    deadline = max(deadlines) if deadlines else None
    checking_due = bool(homeworks) and (deadline is None or deadline < today)
    active_results = [r for r in results if r.student_id in student_ids]
    pending_check = sum(1 for r in active_results if r.status in PENDING_CHECK)

    if not homeworks:
        homework_state = COMPONENT_NOT_REQUIRED if lesson.homework_not_required else COMPONENT_MISSING
    elif not checking_due:
        homework_state = COMPONENT_WAITING
    elif pending_check:
        homework_state = COMPONENT_UNCHECKED
    else:
        homework_state = COMPONENT_OK

    # -- scores ---------------------------------------------------------------
    grades_missing: list[StudentRef] = []
    if not homeworks:
        grades_state = COMPONENT_NOT_REQUIRED if lesson.homework_not_required else COMPONENT_NO_HOMEWORK
    elif not students:
        grades_state = COMPONENT_NO_STUDENTS
    elif not checking_due:
        grades_state = COMPONENT_WAITING
    else:
        by_key = {(r.homework_id, r.student_id): r for r in active_results}
        for student in students:
            for hw in homeworks:
                result = by_key.get((hw.id, student.id))
                graded = result is not None and (
                    result.score is not None or result.status == HomeworkResult.Status.NOT_SUBMITTED
                )
                if not graded:
                    grades_missing.append(student)
                    break
        if not grades_missing:
            grades_state = COMPONENT_OK
        elif len(grades_missing) < len(students):
            grades_state = COMPONENT_PARTIAL
        else:
            grades_state = COMPONENT_MISSING
    grades_required = len(students) if grades_state in (COMPONENT_OK, COMPONENT_PARTIAL, COMPONENT_MISSING) else 0

    closed = lesson.status == Lesson.Status.COMPLETED

    # -- status + human-readable problems --------------------------------------
    if state == STATE_CANCELLED:
        status = STATUS_CANCELLED
        if lesson.cancellation_reason:
            notes.append(f"Причина отмены: {lesson.cancellation_reason}")
    elif state == STATE_UPCOMING:
        status = STATUS_UPCOMING
    else:
        failed = 0
        if attendance_state in (COMPONENT_MISSING, COMPONENT_PARTIAL):
            failed += 1
            if attendance_state == COMPONENT_MISSING:
                problems.append("Посещаемость не отмечена")
            else:
                n = len(attendance_missing)
                problems.append(f"Посещаемость не отмечена у {n} {_students_word(n)}")
        if homework_state == COMPONENT_MISSING:
            failed += 1
            problems.append("ДЗ не выдано")
        elif homework_state == COMPONENT_UNCHECKED:
            failed += 1
            problems.append(f"ДЗ не проверено: {pending_check} ждут проверки")
        if grades_state in (COMPONENT_MISSING, COMPONENT_PARTIAL):
            failed += 1
            n = len(grades_missing)
            problems.append("Баллы не выставлены" if grades_state == COMPONENT_MISSING
                            else f"Без балла: {n} {_students_word(n)}")
        if not closed:
            problems.append("Занятие не закрыто")

        if failed >= NOT_FILLED_DANGER_COMPONENTS:
            status = STATUS_NOT_FILLED
        elif problems:
            status = STATUS_ATTENTION
        else:
            status = STATUS_OK

        if not students:
            notes.append("В группе нет активных студентов")
        if homework_state == COMPONENT_WAITING and deadline is not None:
            notes.append(f"Срок сдачи ДЗ — {_fmt(deadline)}, проверка ещё не требуется")
        if homework_state == COMPONENT_NOT_REQUIRED:
            notes.append("Отмечено «ДЗ не требуется»")

    if (
        lesson.teacher_id
        and lesson.group_teacher_id
        and lesson.group_teacher.teacher_id != lesson.teacher_id
    ):
        notes.append(f"Замена: вместо {lesson.group_teacher.teacher}")

    stamps = [lesson.completed_at, *attendance.values(), *(hw.updated_at for hw in homeworks),
              *(r.updated_at for r in results)]
    stamps = [s for s in stamps if s is not None]

    return LessonCheck(
        lesson=lesson,
        state=state,
        status=status,
        students_total=len(students),
        closed=closed,
        attendance_state=attendance_state,
        attendance_marked=len(marked_ids),
        attendance_missing=attendance_missing,
        homework_state=homework_state,
        homework_id=homeworks[0].id if homeworks else None,
        homework_deadline=deadline,
        pending_check=pending_check,
        grades_state=grades_state,
        grades_required=grades_required,
        grades_missing=grades_missing,
        problems=problems,
        notes=notes,
        last_activity_at=max(stamps) if stamps else None,
    )


def row_status(*, due: int, closed: int, levels: list[str]) -> str:
    """Status of one teacher×group row from its component levels
    (attendance, homework, scores): nothing due -> no data; every required
    record present and every lesson closed -> OK; two or more components
    mostly unfilled (🔴) -> Не заполнено; any other gap -> Требует внимания."""
    if not due:
        return STATUS_NO_DATA
    danger = sum(1 for level in levels if level == LEVEL_DANGER)
    if danger >= NOT_FILLED_DANGER_COMPONENTS:
        return STATUS_NOT_FILLED
    if closed < due or any(level in (LEVEL_WARNING, LEVEL_DANGER) for level in levels):
        return STATUS_ATTENTION
    return STATUS_OK
