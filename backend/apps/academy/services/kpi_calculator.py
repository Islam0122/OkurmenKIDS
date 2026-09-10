"""Computes every KPI model from Lesson/Attendance/Homework/HomeworkResult — never the other way round.

Each ``calculate_*`` function re-derives its numbers from source data and
persists them with ``update_or_create``, so calling it again for the same
period always makes the stored KPI row match reality again — it is a cache
of the calculation, not a place data is manually entered.

Percentage conventions used throughout (kept consistent, documented once
here rather than repeated per function):
- Attendance percentage counts LATE as attended, ABSENT as not attended,
  and is measured against attendance records that actually exist (a lesson
  nobody marked yet doesn't count against anyone).
- Homework completion at the student level is measured against homeworks
  *assigned* in the period (a homework with no HomeworkResult row at all
  still counts as missed) — that is what makes "missed" meaningful.
- Homework completion at the group/teacher/lesson level is measured
  against the number of results that *could* exist (assigned homeworks ×
  active students) — how much of the class actually turned work in.
"""
from __future__ import annotations

import datetime as dt

from django.db.models import Avg

from apps.users.models import Teacher

from ..models import (
    Attendance,
    Group,
    Homework,
    HomeworkResult,
    KPIAttendance,
    KPIGroup,
    KPIHomework,
    KPILesson,
    KPIStudent,
    KPITeacher,
    Lesson,
    Student,
)

_COMPLETED_HOMEWORK_STATUSES = (
    HomeworkResult.Status.SUBMITTED,
    HomeworkResult.Status.CHECKED,
    HomeworkResult.Status.LATE,
)
_ATTENDED_STATUSES = (Attendance.Status.PRESENT, Attendance.Status.LATE)


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _avg_score(results_qs) -> float:
    return round(results_qs.aggregate(avg=Avg("score"))["avg"] or 0.0, 1)


def calculate_student_kpi(student: Student, group: Group, date_from: dt.date, date_to: dt.date) -> KPIStudent:
    lessons_qs = Lesson.objects.filter(group=group, date__gte=date_from, date__lte=date_to)
    total_lessons = lessons_qs.count()

    attendance_qs = Attendance.objects.filter(student=student, lesson__in=lessons_qs)
    present_count = attendance_qs.filter(status=Attendance.Status.PRESENT).count()
    absent_count = attendance_qs.filter(status=Attendance.Status.ABSENT).count()
    late_count = attendance_qs.filter(status=Attendance.Status.LATE).count()
    marked_total = attendance_qs.count()
    attendance_percent = _pct(present_count + late_count, marked_total)

    homeworks_qs = Homework.objects.filter(lesson__in=lessons_qs)
    total_homeworks = homeworks_qs.count()
    student_results_qs = HomeworkResult.objects.filter(student=student, homework__in=homeworks_qs)
    completed_homeworks = student_results_qs.filter(status__in=_COMPLETED_HOMEWORK_STATUSES).count()
    missed_homeworks = max(total_homeworks - completed_homeworks, 0)
    homework_completion_percent = _pct(completed_homeworks, total_homeworks)
    average_score = _avg_score(student_results_qs)

    kpi, _ = KPIStudent.objects.update_or_create(
        student=student,
        group=group,
        date_from=date_from,
        date_to=date_to,
        defaults={
            "total_lessons": total_lessons,
            "present_count": present_count,
            "absent_count": absent_count,
            "late_count": late_count,
            "attendance_percent": attendance_percent,
            "total_homeworks": total_homeworks,
            "completed_homeworks": completed_homeworks,
            "missed_homeworks": missed_homeworks,
            "homework_completion_percent": homework_completion_percent,
            "average_score": average_score,
        },
    )
    return kpi


def calculate_group_kpi(group: Group, date_from: dt.date, date_to: dt.date) -> KPIGroup:
    lessons_qs = Lesson.objects.filter(group=group, date__gte=date_from, date__lte=date_to)
    total_lessons = lessons_qs.count()
    completed_lessons = lessons_qs.filter(status=Lesson.Status.COMPLETED).count()
    cancelled_lessons = lessons_qs.filter(status=Lesson.Status.CANCELLED).count()

    total_students = group.students.filter(is_active=True).count()

    attendance_qs = Attendance.objects.filter(lesson__in=lessons_qs)
    marked_total = attendance_qs.count()
    attended = attendance_qs.filter(status__in=_ATTENDED_STATUSES).count()
    attendance_percent = _pct(attended, marked_total)

    homeworks_qs = Homework.objects.filter(lesson__in=lessons_qs)
    total_homeworks = homeworks_qs.count()
    results_qs = HomeworkResult.objects.filter(homework__in=homeworks_qs)
    completed_results = results_qs.filter(status__in=_COMPLETED_HOMEWORK_STATUSES).count()
    possible_results = total_homeworks * total_students
    homework_completion_percent = _pct(completed_results, possible_results)
    average_score = _avg_score(results_qs)

    kpi, _ = KPIGroup.objects.update_or_create(
        group=group,
        date_from=date_from,
        date_to=date_to,
        defaults={
            "total_students": total_students,
            "total_lessons": total_lessons,
            "completed_lessons": completed_lessons,
            "cancelled_lessons": cancelled_lessons,
            "attendance_percent": attendance_percent,
            "homework_completion_percent": homework_completion_percent,
            "average_score": average_score,
        },
    )
    return kpi


def calculate_teacher_kpi(teacher: Teacher, date_from: dt.date, date_to: dt.date) -> KPITeacher:
    groups_qs = Group.objects.filter(teacher=teacher)
    total_groups = groups_qs.count()

    lessons_qs = Lesson.objects.filter(group__in=groups_qs, date__gte=date_from, date__lte=date_to)
    total_lessons = lessons_qs.count()
    completed_lessons = lessons_qs.filter(status=Lesson.Status.COMPLETED).count()
    cancelled_lessons = lessons_qs.filter(status=Lesson.Status.CANCELLED).count()

    attendance_qs = Attendance.objects.filter(lesson__in=lessons_qs)
    marked_total = attendance_qs.count()
    attended = attendance_qs.filter(status__in=_ATTENDED_STATUSES).count()
    attendance_percent = _pct(attended, marked_total)

    total_students = Student.objects.filter(group__in=groups_qs, is_active=True).count()
    homeworks_qs = Homework.objects.filter(lesson__in=lessons_qs)
    total_homeworks = homeworks_qs.count()
    results_qs = HomeworkResult.objects.filter(homework__in=homeworks_qs)
    completed_results = results_qs.filter(status__in=_COMPLETED_HOMEWORK_STATUSES).count()
    possible_results = total_homeworks * total_students
    homework_completion_percent = _pct(completed_results, possible_results)
    average_student_score = _avg_score(results_qs)

    kpi, _ = KPITeacher.objects.update_or_create(
        teacher=teacher,
        date_from=date_from,
        date_to=date_to,
        defaults={
            "total_groups": total_groups,
            "total_lessons": total_lessons,
            "completed_lessons": completed_lessons,
            "cancelled_lessons": cancelled_lessons,
            "attendance_percent": attendance_percent,
            "homework_completion_percent": homework_completion_percent,
            "average_student_score": average_student_score,
        },
    )
    return kpi


def calculate_lesson_kpi(lesson: Lesson) -> KPILesson:
    total_students = lesson.group.students.filter(is_active=True).count()

    attendance_qs = Attendance.objects.filter(lesson=lesson)
    present_count = attendance_qs.filter(status=Attendance.Status.PRESENT).count()
    absent_count = attendance_qs.filter(status=Attendance.Status.ABSENT).count()
    late_count = attendance_qs.filter(status=Attendance.Status.LATE).count()
    marked_total = attendance_qs.count()
    attendance_percent = _pct(present_count + late_count, marked_total)

    homeworks_qs = Homework.objects.filter(lesson=lesson)
    total_homeworks = homeworks_qs.count()
    results_qs = HomeworkResult.objects.filter(homework__in=homeworks_qs)
    homework_completed_count = results_qs.filter(status__in=_COMPLETED_HOMEWORK_STATUSES).count()
    possible_results = total_homeworks * total_students
    homework_completion_percent = _pct(homework_completed_count, possible_results)
    average_homework_score = _avg_score(results_qs)

    kpi, _ = KPILesson.objects.update_or_create(
        lesson=lesson,
        defaults={
            "total_students": total_students,
            "present_count": present_count,
            "absent_count": absent_count,
            "late_count": late_count,
            "attendance_percent": attendance_percent,
            "total_homeworks": total_homeworks,
            "homework_completed_count": homework_completed_count,
            "homework_completion_percent": homework_completion_percent,
            "average_homework_score": average_homework_score,
        },
    )
    return kpi


def calculate_attendance_kpi(group: Group, date_from: dt.date, date_to: dt.date) -> KPIAttendance:
    qs = Attendance.objects.filter(lesson__group=group, lesson__date__gte=date_from, lesson__date__lte=date_to)
    total_records = qs.count()
    present_count = qs.filter(status=Attendance.Status.PRESENT).count()
    absent_count = qs.filter(status=Attendance.Status.ABSENT).count()
    late_count = qs.filter(status=Attendance.Status.LATE).count()
    excused_count = qs.filter(status=Attendance.Status.EXCUSED).count()
    attendance_percent = _pct(present_count + late_count, total_records)

    kpi, _ = KPIAttendance.objects.update_or_create(
        group=group,
        date_from=date_from,
        date_to=date_to,
        defaults={
            "total_records": total_records,
            "present_count": present_count,
            "absent_count": absent_count,
            "late_count": late_count,
            "excused_count": excused_count,
            "attendance_percent": attendance_percent,
        },
    )
    return kpi


def calculate_homework_kpi(group: Group, date_from: dt.date, date_to: dt.date) -> KPIHomework:
    homeworks_qs = Homework.objects.filter(lesson__group=group, lesson__date__gte=date_from, lesson__date__lte=date_to)
    total_homeworks = homeworks_qs.count()

    results_qs = HomeworkResult.objects.filter(homework__in=homeworks_qs)
    total_results = results_qs.count()
    submitted_count = results_qs.filter(status=HomeworkResult.Status.SUBMITTED).count()
    checked_count = results_qs.filter(status=HomeworkResult.Status.CHECKED).count()
    not_submitted_count = results_qs.filter(status=HomeworkResult.Status.NOT_SUBMITTED).count()
    late_count = results_qs.filter(status=HomeworkResult.Status.LATE).count()
    completed_total = submitted_count + checked_count + late_count
    completion_percent = _pct(completed_total, total_results)
    average_score = _avg_score(results_qs)

    kpi, _ = KPIHomework.objects.update_or_create(
        group=group,
        date_from=date_from,
        date_to=date_to,
        defaults={
            "total_homeworks": total_homeworks,
            "total_results": total_results,
            "submitted_count": submitted_count,
            "checked_count": checked_count,
            "not_submitted_count": not_submitted_count,
            "late_count": late_count,
            "completion_percent": completion_percent,
            "average_score": average_score,
        },
    )
    return kpi
