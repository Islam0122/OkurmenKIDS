"""Export for the curriculum catalogue: Course and CourseLessonPlan.

Deliberately separate from the Student export in this same package and from
Teacher's in ``apps.users.import_export.teachers`` — Course and
CourseLessonPlan have a completely different shape (a course catalogue entry
vs. a syllabus row with an FK to a subject) and no natural upsert key, so
this module only exports; it doesn't try to force-fit the Student/Teacher
import machinery onto data that doesn't have a matching identity.
"""
from __future__ import annotations

from django.db.models import Count, QuerySet
from django.http import HttpResponse

from apps.users.import_export.formats import build_export_response

from ..models import Course, CourseLessonPlan

COURSE_EXPORT_FIELDS = [
    "id",
    "name",
    "description",
    "count_lesson",
    "lesson_plans_count",
    "subjects",
    "groups_count",
    "created_at",
    "updated_at",
]

COURSE_EXPORT_HEADERS = {
    "id": "ID",
    "name": "Название курса",
    "description": "Описание",
    "count_lesson": "Занятий по плану",
    "lesson_plans_count": "Планов занятий создано",
    "subjects": "Предметы",
    "groups_count": "Групп на курсе",
    "created_at": "Дата создания",
    "updated_at": "Дата обновления",
}

LESSON_PLAN_EXPORT_FIELDS = [
    "id",
    "course",
    "lesson_number",
    "subject",
    "topic",
    "description",
    "youtube_url",
    "presentation_urls",
    "homework_title",
    "homework_description",
    "created_at",
    "updated_at",
]

LESSON_PLAN_EXPORT_HEADERS = {
    "id": "ID",
    "course": "Курс",
    "lesson_number": "Номер занятия",
    "subject": "Предмет",
    "topic": "Тема занятия",
    "description": "Описание",
    "youtube_url": "Ссылка на YouTube",
    "presentation_urls": "Ссылки на презентации",
    "homework_title": "Домашнее задание",
    "homework_description": "Описание домашнего задания",
    "created_at": "Дата создания",
    "updated_at": "Дата обновления",
}


def export_courses(queryset: QuerySet[Course], fmt: str = "csv") -> HttpResponse:
    queryset = queryset.prefetch_related("subjects").annotate(
        _lesson_plans_count=Count("lesson_plans", distinct=True),
        _groups_count=Count("groups", distinct=True),
    )
    rows = []
    for course in queryset:
        rows.append(
            {
                "id": course.id,
                "name": course.name,
                "description": course.description,
                "count_lesson": course.count_lesson,
                "lesson_plans_count": course._lesson_plans_count,
                "subjects": "; ".join(subject.name for subject in course.subjects.all()),
                "groups_count": course._groups_count,
                "created_at": course.created_at.isoformat(),
                "updated_at": course.updated_at.isoformat(),
            }
        )
    return build_export_response(rows, COURSE_EXPORT_FIELDS, fmt, "courses", COURSE_EXPORT_HEADERS)


def export_lesson_plans(queryset: QuerySet[CourseLessonPlan], fmt: str = "csv") -> HttpResponse:
    queryset = queryset.select_related("course", "subject")
    rows = []
    for plan in queryset:
        rows.append(
            {
                "id": plan.id,
                "course": plan.course.name,
                "lesson_number": plan.lesson_number,
                "subject": plan.subject.name,
                "topic": plan.topic,
                "description": plan.description,
                "youtube_url": plan.youtube_url,
                "presentation_urls": "; ".join(plan.presentation_urls or []),
                "homework_title": plan.homework_title,
                "homework_description": plan.homework_description,
                "created_at": plan.created_at.isoformat(),
                "updated_at": plan.updated_at.isoformat(),
            }
        )
    return build_export_response(rows, LESSON_PLAN_EXPORT_FIELDS, fmt, "course_lesson_plans", LESSON_PLAN_EXPORT_HEADERS)
