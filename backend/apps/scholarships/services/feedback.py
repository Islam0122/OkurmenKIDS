"""Which trainer must assess which student in which subject for a period.

A trainer is expected to give feedback for every (student, subject) pair
where they actually gave that student a non-cancelled lesson of that
subject during the period (attendance recorded) — the same ownership rule
the rest of the LMS uses (`Lesson.objects.for_teacher`), so a trainer can
never assess, or even see, a student they didn't teach.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError

from apps.academy.models import Attendance, Lesson, Student
from apps.users.models import Subject, Teacher

from ..models import ScholarshipPeriod, TrainerFeedback


@dataclass
class RequiredFeedback:
    student: Student
    subject: Subject
    feedback: TrainerFeedback | None

    @property
    def is_submitted(self) -> bool:
        return self.feedback is not None


def taught_pairs(teacher: Teacher, period: ScholarshipPeriod) -> set[tuple[int, int]]:
    lessons = (
        Lesson.objects.for_teacher(teacher)
        .filter(date__gte=period.period_start, date__lte=period.period_end, subject__isnull=False)
        .exclude(status=Lesson.Status.CANCELLED)
    )
    return set(
        Attendance.objects.filter(lesson__in=lessons)
        .values_list("student_id", "lesson__subject_id")
        .distinct()
    )


def required_feedback(teacher: Teacher, period: ScholarshipPeriod) -> list[RequiredFeedback]:
    pairs = taught_pairs(teacher, period)
    students = Student.objects.in_bulk({student_id for student_id, _ in pairs})
    subjects = Subject.objects.in_bulk({subject_id for _, subject_id in pairs})
    existing = {
        (fb.student_id, fb.subject_id): fb
        for fb in TrainerFeedback.objects.filter(period=period, teacher=teacher)
    }
    items = [
        RequiredFeedback(students[student_id], subjects[subject_id], existing.get((student_id, subject_id)))
        for student_id, subject_id in pairs
    ]
    items.sort(key=lambda item: (item.is_submitted, item.student.last_name, item.student.first_name, item.subject.name))
    return items


def validate_feedback_target(*, period: ScholarshipPeriod, teacher: Teacher, student: Student, subject: Subject) -> None:
    if not period.is_draft:
        raise ValidationError("Период уже утверждён — оценки тренеров больше не принимаются.")
    if (student.id, subject.id) not in taught_pairs(teacher, period):
        raise ValidationError(
            f"Тренер «{teacher}» не вёл у студента «{student}» занятия по предмету «{subject}» в этом периоде."
        )
