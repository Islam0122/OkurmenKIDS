"""Read-only overview of a Group's subject → teacher assignments.

For every subject that appears in the group's course lesson plan, answers
"who will teach its lessons?" by the same rules services.lesson_generator
applies (see its module docstring) — so the admin sees, *before* clicking
"Сгенерировать занятия", which subjects still have nobody assigned and will
therefore be skipped rather than silently given to another trainer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Count

from ..models import CourseLessonPlan, Group, GroupSchedule, GroupTeacher

STATUS_ASSIGNED = "assigned"
STATUS_MULTIPLE = "multiple"
STATUS_LEGACY_SLOT = "legacy_slot"
STATUS_UNASSIGNED = "unassigned"

STATUS_LABELS = {
    STATUS_ASSIGNED: "Назначен",
    STATUS_MULTIPLE: "Несколько тренеров",
    STATUS_LEGACY_SLOT: "Тренер слота «без предмета»",
    STATUS_UNASSIGNED: "Не назначен",
}


@dataclass
class SubjectAssignment:
    subject_id: int
    subject_name: str
    plan_lessons: int
    teachers: list = field(default_factory=list)
    legacy_teachers: list = field(default_factory=list)
    status: str = STATUS_UNASSIGNED

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    def as_dict(self) -> dict:
        return {
            "subject": self.subject_id,
            "subject_name": self.subject_name,
            "plan_lessons": self.plan_lessons,
            "teachers": [{"id": t.pk, "name": str(t)} for t in self.teachers],
            "legacy_teachers": [{"id": t.pk, "name": str(t)} for t in self.legacy_teachers],
            "status": self.status,
            "status_label": self.status_label,
        }


def subject_assignment_overview(group: Group) -> list[SubjectAssignment]:
    """One SubjectAssignment per subject of the group's course lesson plan,
    ordered by subject name. Programs with their own individual plan are
    left out — they never take shared course-plan lessons."""
    plan_subjects = (
        CourseLessonPlan.objects.filter(course_id=group.course_id)
        .values("subject_id", "subject__name")
        .annotate(lessons=Count("id"))
        .order_by("subject__name")
    )

    assignments = (
        GroupTeacher.objects.filter(
            group=group, is_active=True, subject__isnull=False, teacher__is_active=True,
        )
        .exclude(lesson_plans__isnull=False)
        .select_related("teacher__user")
    )
    teachers_by_subject: dict[int, list] = {}
    for gt in assignments:
        teachers_by_subject.setdefault(gt.subject_id, [])
        if gt.teacher not in teachers_by_subject[gt.subject_id]:
            teachers_by_subject[gt.subject_id].append(gt.teacher)

    legacy_teachers = []
    for slot in (
        GroupSchedule.objects.filter(group=group, is_active=True, subject__isnull=True, teacher__is_active=True)
        .select_related("teacher__user")
    ):
        if slot.teacher not in legacy_teachers:
            legacy_teachers.append(slot.teacher)

    overview = []
    for row in plan_subjects:
        teachers = teachers_by_subject.get(row["subject_id"], [])
        if len(teachers) == 1:
            status = STATUS_ASSIGNED
        elif len(teachers) > 1:
            status = STATUS_MULTIPLE
        elif legacy_teachers:
            status = STATUS_LEGACY_SLOT
        else:
            status = STATUS_UNASSIGNED
        overview.append(
            SubjectAssignment(
                subject_id=row["subject_id"],
                subject_name=row["subject__name"],
                plan_lessons=row["lessons"],
                teachers=teachers,
                legacy_teachers=legacy_teachers if status == STATUS_LEGACY_SLOT else [],
                status=status,
            )
        )
    return overview


def unassigned_subjects(group: Group) -> list[SubjectAssignment]:
    return [row for row in subject_assignment_overview(group) if row.status == STATUS_UNASSIGNED]
