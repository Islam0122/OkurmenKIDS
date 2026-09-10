"""KPI analytics for the academy app.

KPI is deliberately not a table of stored numbers — it is a
(student, group, period) slice, and every statistic is derived on the fly
from Attendance and Homework. This keeps a single source of truth: fix an
Attendance record and every KPI period covering that date is automatically
correct, nothing to re-save.
"""
from __future__ import annotations

from django.db.models import Avg

from .models import Attendance, Homework, KPI


def calculate_attendance_stats(student_id: int, group_id: int, date_from, date_to) -> dict:
    qs = Attendance.objects.filter(
        student_id=student_id,
        group_id=group_id,
        date__gte=date_from,
        date__lte=date_to,
    )

    total = qs.count()
    present = qs.filter(status=Attendance.Status.PRESENT).count()
    absent = qs.filter(status=Attendance.Status.ABSENT).count()
    late = qs.filter(status=Attendance.Status.LATE).count()
    excused = qs.filter(status=Attendance.Status.EXCUSED).count()

    # A late arrival still counts as attendance for the percentage; only
    # absence pulls it down.
    attended = present + late
    percentage = round(attended / total * 100, 1) if total else 0.0

    return {
        "total_lessons": total,
        "present": present,
        "absent": absent,
        "late": late,
        "excused": excused,
        "attendance_percentage": percentage,
    }


def calculate_homework_stats(student_id: int, group_id: int, date_from, date_to) -> dict:
    qs = Homework.objects.filter(
        student_id=student_id,
        group_id=group_id,
        date__gte=date_from,
        date__lte=date_to,
    )

    total = qs.count()
    average_score = qs.aggregate(avg=Avg("score"))["avg"] or 0.0
    average_score = round(average_score, 1)
    percentage = round(average_score / 10 * 100, 1) if total else 0.0

    return {
        "total_records": total,
        "average_score": average_score,
        "homework_percentage": percentage,
    }


def calculate_kpi_summary(kpi: KPI) -> dict:
    return {
        "attendance": calculate_attendance_stats(
            kpi.student_id, kpi.group_id, kpi.date_from, kpi.date_to
        ),
        "homework": calculate_homework_stats(
            kpi.student_id, kpi.group_id, kpi.date_from, kpi.date_to
        ),
    }
