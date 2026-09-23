"""Read-only overview: who teaches each subject of a Group's course plan.

For every subject in the group's course lesson plan, answers "which
program (trainer + schedule) will get its lessons?" by the very same
routing services.lesson_generator uses — so the admin sees, *before*
clicking "Сгенерировать занятия", e.g. that English has 48 lessons in the
plan but no program with a schedule yet, and will therefore be skipped
rather than squeezed into the IT or Soft Skills slots.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..models import Group, Lesson
from .lesson_generator import (
    ROUTE_DEDICATED,
    ROUTE_INDIVIDUAL,
    ROUTE_LEGACY,
    _shared_plan_setup,
)

STATUS_ASSIGNED = "assigned"
STATUS_MULTIPLE = "multiple"
STATUS_LEGACY_SLOT = "legacy_slot"
STATUS_INDIVIDUAL = "individual"
STATUS_UNASSIGNED = "unassigned"

STATUS_LABELS = {
    STATUS_ASSIGNED: "Программа с расписанием",
    STATUS_MULTIPLE: "Несколько программ",
    STATUS_LEGACY_SLOT: "Слот «без предмета»",
    STATUS_INDIVIDUAL: "Индивидуальный план программы",
    STATUS_UNASSIGNED: "Нет программы с расписанием",
}


@dataclass
class SubjectAssignment:
    subject_id: int
    subject_name: str
    plan_lessons: int
    generated_lessons: int = 0
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
            "generated_lessons": self.generated_lessons,
            "teachers": [{"id": t.pk, "name": str(t)} for t in self.teachers],
            "legacy_teachers": [{"id": t.pk, "name": str(t)} for t in self.legacy_teachers],
            "status": self.status,
            "status_label": self.status_label,
        }


def subject_assignment_overview(group: Group) -> list[SubjectAssignment]:
    """One SubjectAssignment per subject of the group's course lesson plan,
    ordered by subject name."""
    group_teachers = list(group.teachers.filter(is_active=True).select_related("teacher__user", "subject"))
    individual = [gt for gt in group_teachers if gt.lesson_plans.exists()]
    shared = [gt for gt in group_teachers if gt not in individual]
    plans, _slots, routing = _shared_plan_setup(group, shared, individual)

    rows_by_subject = Counter(plan.subject_id for plan in plans)
    names = {plan.subject_id: plan.subject.name for plan in plans}
    generated = Counter(
        Lesson.objects.filter(group=group, subject_id__in=rows_by_subject).values_list("subject_id", flat=True)
    )

    overview = []
    for subject_id, count in rows_by_subject.items():
        route = routing.route.get(subject_id)
        teachers, legacy_teachers = [], []
        if route == ROUTE_DEDICATED:
            teachers = _unique(gt.teacher for gt in routing.owners(subject_id))
            status = STATUS_ASSIGNED if len(teachers) == 1 else STATUS_MULTIPLE
        elif route == ROUTE_LEGACY:
            if routing.assignments.get(subject_id):
                teachers = _unique(gt.teacher for gt in routing.assignments[subject_id])
            else:
                legacy_teachers = _unique(slot.teacher for slot in routing.legacy_slots)
            status = STATUS_LEGACY_SLOT
        elif route == ROUTE_INDIVIDUAL:
            teachers = _unique(gt.teacher for gt in individual if gt.subject_id == subject_id)
            status = STATUS_INDIVIDUAL
        else:
            status = STATUS_UNASSIGNED
        overview.append(
            SubjectAssignment(
                subject_id=subject_id,
                subject_name=names[subject_id],
                plan_lessons=count,
                generated_lessons=generated.get(subject_id, 0),
                teachers=teachers,
                legacy_teachers=legacy_teachers,
                status=status,
            )
        )
    return sorted(overview, key=lambda row: row.subject_name)


def _unique(items) -> list:
    return list({item.pk: item for item in items}.values())


def unassigned_subjects(group: Group) -> list[SubjectAssignment]:
    return [row for row in subject_assignment_overview(group) if row.status == STATUS_UNASSIGNED]
