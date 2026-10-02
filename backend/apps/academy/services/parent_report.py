"""«Мини-отчёт родителям» — a short Kyrgyz message for the parents' Telegram
chat after a lesson: topic → who attended → who didn't do the homework →
the next homework. Nothing else (no KPI, scores or analytics).

Everything comes from existing rows; nothing is invented:

- topic — ``Lesson.topic``;
- attended — Attendance PRESENT / LATE, absent — ABSENT / EXCUSED;
- homework checked today — the Homework of this program's previous
  (not cancelled) lesson: in this project a Homework belongs to the lesson
  it was *given* at, and is graded afterwards. «Не выполнили» = its
  HomeworkResult rows with NOT_SUBMITTED (LATE counts as done). There is
  no «partial» status, so ``homework_partial`` is always empty;
- next homework — the Homework given at this lesson.

When something is missing the message says so with a ⚠️ line (for the
trainer to fix before sending) instead of guessing; ``warnings`` repeats
it in Russian for the LMS screen only.

    report = ParentLessonReportService.generate(lesson_id)
"""
from __future__ import annotations

from django.db.models import Q

from ..models import Attendance, Homework, HomeworkResult, Lesson, Student

GREETING = "Саламатсыздарбы, урматтуу ата-энелер! 🌟"
TOPIC_LINE = "Бүгүнкү сабакта окуучулар «{topic}» темасын үйрөнүштү. 📚"
NO_TOPIC = "⚠️ Тема занятия не указана."
PRESENT_TITLE = "👥 Сабакка катышкан окуучулар:"
ABSENT_TITLE = "🚫 Сабакка катышпаган окуучулар:"
NOT_DONE_TITLE = "❌ Үй тапшырмасын аткарбаган окуучулар:"
PARTIAL_TITLE = "🟡 Үй тапшырмасын жарым-жартылай аткарган окуучулар:"
ALL_DONE = "Баары аткарды ✅"
NEXT_TITLE = "📝 Кийинки үй тапшырмасы:"
NO_NEXT = "Үй тапшырмасы азырынча берилген жок."
CLOSING = "📚 Кийинки сабакта жаңы теманы улантабыз. Рахмат! 🌟"
NO_ATTENDANCE = "⚠️ Посещаемость не отмечена."
RESULTS_INCOMPLETE = "⚠️ Результаты ДЗ отмечены не у всех."

PRESENT_STATUSES = (Attendance.Status.PRESENT, Attendance.Status.LATE)


def _name(student: Student) -> str:
    return f"{student.first_name} {student.last_name}".strip()


def _names(students) -> list[str]:
    """Same order as the attendance roster: last name, then first name."""
    return [_name(s) for s in sorted(students, key=lambda s: (s.last_name.casefold(), s.first_name.casefold()))]


def _bullets(names: list[str]) -> list[str]:
    return [f"• {name}" for name in names]


def previous_lesson(lesson: Lesson) -> Lesson | None:
    """The same program's (GroupTeacher's — or, without one, the group's)
    last not-cancelled lesson before this one."""
    scope = Lesson.objects.filter(group_teacher_id=lesson.group_teacher_id) if lesson.group_teacher_id \
        else Lesson.objects.filter(group_id=lesson.group_id)
    return (
        scope.exclude(pk=lesson.pk)
        .exclude(status=Lesson.Status.CANCELLED)
        .filter(Q(date__lt=lesson.date) | Q(date=lesson.date, start_time__lt=lesson.start_time))
        .order_by("-date", "-start_time")
        .first()
    )


def homework_text(homework: Homework) -> str:
    title, description = homework.title.strip(), homework.description.strip()
    return f"{title} — {description}" if description else title


class ParentLessonReportService:
    @classmethod
    def generate(cls, lesson_id: int) -> dict:
        lesson = Lesson.objects.select_related("group").get(pk=lesson_id)
        return cls.generate_for(lesson)

    @classmethod
    def generate_for(cls, lesson: Lesson) -> dict:
        warnings: list[str] = []
        topic = (lesson.topic or "").strip()
        if not topic:
            warnings.append("У занятия не указана тема — заполните её или исправьте текст вручную.")

        # -- Attendance --------------------------------------------------
        records = list(Attendance.objects.filter(lesson=lesson).select_related("student"))
        present = _names(r.student for r in records if r.status in PRESENT_STATUSES)
        absent = _names(r.student for r in records if r.status not in PRESENT_STATUSES)
        active = list(lesson.group.students.filter(is_active=True))
        marked_ids = {r.student_id for r in records}
        unmarked = [s for s in active if s.id not in marked_ids]
        if not records:
            warnings.append("Посещаемость этого занятия не отмечена.")
        elif unmarked:
            warnings.append(f"Посещаемость не отмечена у {len(unmarked)} студент(ов): {', '.join(_names(unmarked))}.")

        # -- Homework checked today (given at the previous lesson) -------
        checked = None
        not_done: list[str] = []
        results_complete = True
        prev = previous_lesson(lesson)
        prev_homeworks = list(Homework.objects.filter(lesson=prev).order_by("created_at")) if prev else []
        if prev_homeworks:
            results = list(
                HomeworkResult.objects.filter(homework__in=prev_homeworks, student__group=lesson.group)
                .select_related("student")
            )
            not_done = _names({
                r.student_id: r.student for r in results if r.status == HomeworkResult.Status.NOT_SUBMITTED
            }.values())
            graded_ids = {r.student_id for r in results}
            ungraded = [s for s in active if s.id not in graded_ids]
            results_complete = not ungraded
            checked = {
                "title": "; ".join(h.title for h in prev_homeworks),
                "lesson_id": prev.pk,
                "lesson_number": prev.lesson_number,
                "lesson_date": prev.date.isoformat(),
            }
            if ungraded:
                warnings.append(
                    f"Результаты ДЗ «{checked['title']}» не отмечены у {len(ungraded)} студент(ов): "
                    f"{', '.join(_names(ungraded))}."
                )

        # -- Next homework (given at this lesson) -----------------------
        homeworks = list(Homework.objects.filter(lesson=lesson).order_by("created_at"))
        next_homework = "\n".join(homework_text(h) for h in homeworks) or None

        data = {
            "lesson_id": lesson.pk,
            "group": lesson.group.name,
            "lesson_date": lesson.date.isoformat(),
            "topic": topic or None,
            "present_students": present,
            "absent_students": absent,
            "homework_checked": checked,
            "homework_not_completed": not_done,
            "homework_partial": [],  # no «partial» HomeworkResult status in the system
            "next_homework": next_homework,
            "warnings": warnings,
        }
        data["message"] = cls.build_message(data, attendance_marked=bool(records), results_complete=results_complete)
        return data

    @staticmethod
    def build_message(data: dict, *, attendance_marked: bool = True, results_complete: bool = True) -> str:
        blocks = [
            [GREETING],
            [TOPIC_LINE.format(topic=data["topic"]) if data["topic"] else NO_TOPIC],
            [PRESENT_TITLE, *(
                (_bullets(data["present_students"]) or ["—"]) if attendance_marked else [NO_ATTENDANCE]
            )],
        ]
        if data["absent_students"]:
            blocks.append([ABSENT_TITLE, *_bullets(data["absent_students"])])
        if data["homework_checked"] is not None:
            if data["homework_not_completed"]:
                body = _bullets(data["homework_not_completed"])
            else:
                body = [ALL_DONE if results_complete else RESULTS_INCOMPLETE]
            blocks.append([NOT_DONE_TITLE, *body])
        if data["homework_partial"]:
            blocks.append([PARTIAL_TITLE, *_bullets(data["homework_partial"])])
        blocks.append([NEXT_TITLE])
        blocks.append([data["next_homework"] or NO_NEXT])
        blocks.append([CLOSING])
        return "\n\n".join("\n".join(lines) for lines in blocks)
