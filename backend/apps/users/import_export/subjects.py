"""Export for Subject — a distinct shape from Teacher, not reused from it.

Subject has no fields of its own worth confusing with a person's profile:
just a name/description/status plus two reverse relations that are genuinely
useful to see in a spreadsheet — which teachers can deliver it, and which
courses it's part of.
"""
from __future__ import annotations

from django.db.models import QuerySet
from django.http import HttpResponse

from ..models import Subject
from .formats import build_export_response

EXPORT_FIELDS = [
    "id",
    "name",
    "description",
    "is_active",
    "teachers",
    "courses",
    "created_at",
    "updated_at",
]

EXPORT_HEADERS = {
    "id": "ID",
    "name": "Название предмета",
    "description": "Описание",
    "is_active": "Активен",
    "teachers": "Тренеры",
    "courses": "Курсы",
    "created_at": "Дата создания",
    "updated_at": "Дата обновления",
}


def export_subjects(queryset: QuerySet[Subject], fmt: str = "csv") -> HttpResponse:
    queryset = queryset.prefetch_related("teachers__user", "courses")
    rows = []
    for subject in queryset:
        teacher_names = [
            teacher.user.get_full_name() or teacher.user.username for teacher in subject.teachers.all()
        ]
        rows.append(
            {
                "id": subject.id,
                "name": subject.name,
                "description": subject.description,
                "is_active": subject.is_active,
                "teachers": "; ".join(teacher_names),
                "courses": "; ".join(course.name for course in subject.courses.all()),
                "created_at": subject.created_at.isoformat(),
                "updated_at": subject.updated_at.isoformat(),
            }
        )
    return build_export_response(rows, EXPORT_FIELDS, fmt, "subjects", EXPORT_HEADERS)
