"""«Мини-отчёт родителям» — a short Kyrgyz message the trainer copies into the
parents' chat after a lesson (the LMS sends nothing itself): topic → who attended → who didn't do the homework →
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

Two wordings of the same data (``messages``), one per «Автор отчёта»:
``system`` — «🤖 Система», the standard LMS report, and ``trainer`` —
«👨‍🏫 Тренер», a shorter first-person text. ``message`` stays the system
one. «✏️ Свой вариант» is the trainer's own edit in the browser — never
stored, and nothing in the LMS changes when it is edited.

Nothing is stored or cached: every call re-reads the rows above, so a
grade, status, attendance mark or homework text changed after the lesson
is in the next report. The view calls it on every GET.

When something is missing the message says so with a ⚠️ line (for the
trainer to fix before sending) instead of guessing; ``warnings`` repeats
it in Russian for the LMS screen only.

    report = ParentLessonReportService.generate(lesson_id)
"""
from __future__ import annotations

from django.db.models import Q

from ..models import Attendance, Homework, HomeworkResult, Lesson, Student

GREETING = "Саламатсыздарбы, урматтуу ата-энелер! 🌟"
NO_TOPIC = "⚠️ Тема занятия не указана."
NO_NEXT = "Үй тапшырмасы азырынча берилген жок."
NO_ATTENDANCE = "⚠️ Посещаемость не отмечена."
RESULTS_INCOMPLETE = "⚠️ Результаты ДЗ отмечены не у всех."
PARTIAL_TITLE = "🟡 Үй тапшырмасын жарым-жартылай аткарган окуучулар:"
NEXT_TITLE = "📚 Кийинки үй тапшырмасы:"

# One wording per report type; the blocks, their order and the data are shared.
STYLES = {
    "system": {
        "topic": "📚 Бүгүнкү сабакта окуучулар «{topic}» темасын үйрөнүштү.",
        "present": "👥 Сабакка катышкан окуучулар:",
        "absent": "🚫 Сабакка катышпаган окуучулар:",
        "not_done": "❌ Үй тапшырмасын аткарбаган окуучулар:",
        "all_done": "✅ Үй тапшырмасын баары аткарды.",
        "next_separator": "\n\n",
        "closing": "📚 Кийинки сабакта жаңы теманы улантабыз. Рахмат! 🌟",
    },
    "trainer": {
        "topic": "Бүгүнкү сабакта «{topic}» темасын өттүк. 📚",
        "present": "👥 Сабакка катышкандар:",
        "absent": "🚫 Сабакка катышпагандар:",
        "not_done": "❌ Өткөн сабактын үй тапшырмасын аткарбагандар:",
        "all_done": "✅ Өткөн сабактын үй тапшырмасын баары аткарды.",
        "next_separator": "\n",
        "closing": "Рахмат! Кийинки сабакта жолугушабыз 🌟",
    },
}

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


def homework_data(homeworks: list[Homework]) -> dict | None:
    """The lesson's homework as data (several are joined, the first id kept)."""
    if not homeworks:
        return None
    return {
        "id": homeworks[0].pk,
        "title": "; ".join(h.title.strip() for h in homeworks),
        "description": "\n".join(h.description.strip() for h in homeworks if h.description.strip()),
    }


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
                HomeworkResult.objects.filter(
                    homework__in=prev_homeworks, student__group=lesson.group, student__is_active=True,
                )
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
            "previous_homework": homework_data(prev_homeworks),
            "homework_not_completed": not_done,
            "homework_partial": [],  # no «partial» HomeworkResult status in the system
            "next_homework": next_homework,
            "current_homework": homework_data(homeworks),
            "warnings": warnings,
        }
        data["messages"] = {
            style: cls.build_message(
                data, style=style, attendance_marked=bool(records), results_complete=results_complete,
            )
            for style in STYLES
        }
        data["message"] = data["messages"]["system"]
        return data

    @staticmethod
    def build_message(data: dict, *, style: str = "system", attendance_marked: bool = True,
                      results_complete: bool = True) -> str:
        words = STYLES[style]
        blocks = [
            [GREETING],
            [words["topic"].format(topic=data["topic"]) if data["topic"] else NO_TOPIC],
            [words["present"], *(
                (_bullets(data["present_students"]) or ["—"]) if attendance_marked else [NO_ATTENDANCE]
            )],
        ]
        if data["absent_students"]:
            blocks.append([words["absent"], *_bullets(data["absent_students"])])
        if data["homework_checked"] is not None:
            if data["homework_not_completed"]:
                blocks.append([words["not_done"], *_bullets(data["homework_not_completed"])])
            elif results_complete:
                blocks.append([words["all_done"]])
            else:
                blocks.append([words["not_done"], RESULTS_INCOMPLETE])
        if data["homework_partial"]:
            blocks.append([PARTIAL_TITLE, *_bullets(data["homework_partial"])])
        blocks.append([NEXT_TITLE + words["next_separator"] + (data["next_homework"] or NO_NEXT)])
        blocks.append([words["closing"]])
        return "\n\n".join("\n".join(lines) for lines in blocks)
