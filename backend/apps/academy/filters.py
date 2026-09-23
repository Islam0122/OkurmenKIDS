"""FilterSets for the academy API.

Trivial exact-match filtering (a single FK or boolean) is left to
``filterset_fields`` on the viewset — a FilterSet class here only earns its
keep where a plain field list can't express what's needed: date ranges, or
filtering across a relation (e.g. Attendance by its lesson's group/date).
"""
from __future__ import annotations

import django_filters as filters
from django.db.models import Q

from .models import (
    Attendance,
    Course,
    Group,
    Homework,
    Lesson,
    Student,
)


class CourseFilter(filters.FilterSet):
    subject = filters.NumberFilter(field_name="subjects__id")

    class Meta:
        model = Course
        fields = ["subject"]


class StudentFilter(filters.FilterSet):
    class Meta:
        model = Student
        fields = ["group", "is_active"]


class GroupFilter(filters.FilterSet):
    class Meta:
        model = Group
        fields = ["course", "teacher", "room", "status"]


class LessonFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte")
    teacher = filters.NumberFilter(method="filter_teacher")

    class Meta:
        model = Lesson
        fields = ["group", "subject", "status", "date", "room"]

    def filter_teacher(self, queryset, name, value):
        # The lesson's effective teacher (see Lesson.effective_teacher) —
        # only ever narrows the viewset's own queryset, which is already
        # scoped to the requesting teacher's lessons for non-admins.
        return queryset.filter(Q(teacher_id=value) | Q(teacher__isnull=True, group_teacher__teacher_id=value))


class AttendanceFilter(filters.FilterSet):
    group = filters.NumberFilter(field_name="lesson__group_id")
    date = filters.DateFilter(field_name="lesson__date")
    date_from = filters.DateFilter(field_name="lesson__date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="lesson__date", lookup_expr="lte")

    class Meta:
        model = Attendance
        fields = ["student", "lesson", "status", "group", "date"]


class HomeworkFilter(filters.FilterSet):
    group = filters.NumberFilter(field_name="lesson__group_id")

    class Meta:
        model = Homework
        fields = ["lesson", "group"]
