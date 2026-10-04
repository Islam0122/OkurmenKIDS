"""Figures a Team Lead report gets from the LMS instead of typing them in.

Every number comes from what already computes it:

* groups / students / trainers, attendance, homework, results, KPI —
  apps.academy.services.reports (the Reports / KPI engine), for the
  report's own period;
* tests and exams — apps.testing (TestSession / StudentAttempt; the
  Team Lead's own attempts, StudentAttempt.user, never count);
* quality of work — the Team Lead's own journal and reports in the period
  (lesson visits, trainers checked, problems found / solved, meetings).

The result is stored on the report as a snapshot (TeamLeadReport.metrics),
so a report keeps saying what it said when it was written; «Пересчитать»
refreshes it.
"""
from __future__ import annotations

import datetime as dt

from django.db.models import Avg, Q
from django.utils import timezone

from apps.academy.models import Group, Lesson, Student
from apps.academy.services.reports import ReportFilters, build_overview, build_student_rows, build_teacher_detail
from apps.users.models import Teacher

from .models import ReportKind, TaskStatus, TeamLeadReport, WorkLogEntry, WorkType

LOW_ATTENDANCE = 70.0   # %, «низкая посещаемость»
LOW_RESULTS = 60.0      # %, «низкие результаты»
HOMEWORK_NORM = 80.0    # %, groups below it are «ниже нормы»


def _filters(start: dt.date, end: dt.date, **extra) -> ReportFilters:
    params = {"period": "custom", "start_date": start.isoformat(), "end_date": end.isoformat()}
    params.update({k: v for k, v in extra.items() if v is not None})
    return ReportFilters.from_query(params, today=timezone.localdate())


def _round(value):
    return round(value, 1) if isinstance(value, (int, float)) else value


def _tests(start: dt.date, end: dt.date, group_ids=None) -> dict:
    from apps.testing.models import AttemptStatus, SessionType, StudentAttempt, TestSession

    sessions = TestSession.objects.filter(
        Q(scheduled_start__date__range=(start, end)) | Q(scheduled_start__isnull=True, started_at__date__range=(start, end))
    ).exclude(status="cancelled")
    if group_ids is not None:
        sessions = sessions.filter(group_id__in=group_ids)
    finished = StudentAttempt.objects.filter(
        session__in=sessions, status=AttemptStatus.FINISHED, user__isnull=True,
    ).select_related("session__test")
    below = sum(1 for a in finished if a.score < a.session.test.passing_score)
    exam_groups = set(
        sessions.filter(session_type=SessionType.EXAM, group__isnull=False).values_list("group_id", flat=True)
    )
    return {
        "tests_held": sessions.filter(session_type=SessionType.TRAINING).count(),
        "exams_held": sessions.filter(session_type=SessionType.EXAM).count(),
        "average_score": _round(finished.aggregate(avg=Avg("score"))["avg"]),
        "students_below_passing": below,
        "groups_with_exam": len(exam_groups),
    }


def _quality(author, start: dt.date, end: dt.date) -> dict:
    reports = TeamLeadReport.objects.filter(author=author, date__range=(start, end))
    visits = reports.filter(kind=ReportKind.LESSON_VISIT)
    entries = WorkLogEntry.objects.filter(author=author, date__range=(start, end))
    problems = entries.filter(Q(work_type=WorkType.PROBLEM) | ~Q(problem=""))
    # Visits and checks are work done (journal records), not tasks planned.
    logs = entries.filter(entry_kind=WorkLogEntry.Kind.LOG)
    checked = set(visits.exclude(teacher__isnull=True).values_list("teacher_id", flat=True)) | set(
        reports.filter(kind=ReportKind.TRAINER_REVIEW).exclude(teacher__isnull=True).values_list("teacher_id", flat=True)
    ) | set(
        logs.filter(work_type__in=[WorkType.LESSON_CONTROL, WorkType.TRAINER]).exclude(teacher__isnull=True)
        .values_list("teacher_id", flat=True)
    )
    return {
        "lessons_visited": visits.count() + logs.filter(work_type=WorkType.LESSON_CONTROL).count(),
        "trainers_checked": len(checked),
        "problems_found": problems.count(),
        "problems_resolved": problems.filter(status=TaskStatus.DONE).count(),
        "problems_in_progress": problems.exclude(status=TaskStatus.DONE).count(),
        "meetings": reports.filter(kind=ReportKind.MEETING).count(),
    }


def academy_metrics(author, start: dt.date, end: dt.date, *, monthly: bool = False) -> dict:
    filters = _filters(start, end)
    overview = build_overview(filters)
    groups = Group.objects.all()
    active_groups = groups.filter(status=Group.Status.ACTIVE)
    group_rows = overview.get("attention_groups", [])
    from apps.academy.services.reports.service import build_group_rows, report_group_ids

    all_group_rows = build_group_rows(filters, report_group_ids(filters))
    students = build_student_rows(filters, Student.objects.filter(status=Student.Status.ACTIVE).select_related("group"))
    teachers = Teacher.objects.all()
    teacher_kpis = [row["kpi"] for row in overview.get("teacher_summary", []) if row.get("kpi") is not None]

    result = {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "groups": {
            "total": groups.count(),
            "active": active_groups.count(),
            "new": groups.filter(start_date__range=(start, end)).count(),
            "with_problems": sum(1 for row in all_group_rows if row.get("kpi_level") in ("low", "attention")),
            "problem_names": [row["name"] for row in group_rows],
        },
        "trainers": {
            "total": teachers.count(),
            "active": teachers.filter(is_active=True).count(),
        },
        "students": {
            "total": overview["students"]["total"],
            "active": overview["students"]["active"],
            "low_attendance": sum(1 for r in students if r["attendance_rate"] is not None and r["attendance_rate"] < LOW_ATTENDANCE),
            "low_results": sum(1 for r in students if r["progress_rate"] is not None and r["progress_rate"] < LOW_RESULTS),
        },
        "homework": {
            "average_completion": _round(overview["homework"]["completion_rate"]),
            "groups_below_norm": sum(
                1 for row in all_group_rows if row.get("homework_rate") is not None and row["homework_rate"] < HOMEWORK_NORM
            ),
        },
        "kpi": {
            "attendance": _round(overview["attendance"]["rate"]),
            "homework": _round(overview["homework"]["completion_rate"]),
            "results": _round(overview["metrics"].get("progress")),
            "academy_kpi": _round(overview["kpi"]["total"]),
            "average_trainer_kpi": _round(sum(teacher_kpis) / len(teacher_kpis)) if teacher_kpis else None,
        },
        "tests": _tests(start, end),
        "quality": _quality(author, start, end),
    }
    if monthly:
        result["groups"]["closed"] = groups.filter(
            status__in=[Group.Status.COMPLETED, Group.Status.CANCELLED], end_date__range=(start, end)
        ).count()
        result["exams"] = {
            "groups_passed": result["tests"]["groups_with_exam"],
            "groups_total": active_groups.count(),
            "average_score": result["tests"]["average_score"],
            "students_below": result["tests"]["students_below_passing"],
        }
    return result


def teacher_metrics(teacher: Teacher, start: dt.date, end: dt.date) -> dict:
    detail = build_teacher_detail(teacher, _filters(start, end))
    metrics = detail.get("metrics", {})
    visits = TeamLeadReport.objects.filter(kind=ReportKind.LESSON_VISIT, teacher=teacher, date__range=(start, end))
    scores = [r.data.get("overall") for r in visits if isinstance(r.data.get("overall"), int)]
    return {
        "teacher": {"id": teacher.pk, "name": str(teacher)},
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "groups": [g["name"] for g in detail.get("groups", [])],
        "students": detail.get("students", {}),
        "attendance": _round(metrics.get("attendance")),
        "homework": _round(metrics.get("homework")),
        "results": _round(metrics.get("progress")),
        "lessons_held": _round(metrics.get("lesson_completion")),
        "kpi": _round(detail.get("kpi", {}).get("total")),
        "kpi_status": detail.get("kpi", {}).get("status_label"),
        "lessons": detail.get("lessons", {}),
        "tests": _tests(start, end, group_ids=[g["id"] for g in detail.get("groups", [])]),
        "lesson_visits": len(scores),
        "lesson_visit_average": _round(sum(scores) / len(scores)) if scores else None,
    }


def student_metrics(student: Student, on: dt.date) -> dict:
    start = on - dt.timedelta(days=30)
    rows = build_student_rows(_filters(start, on), Student.objects.filter(pk=student.pk).select_related("group"))
    row = rows[0] if rows else {}
    group = student.group
    trainers = []
    if group is not None:
        trainers = sorted({str(p.teacher) for p in group.teachers.filter(is_active=True).select_related("teacher__user")})
    return {
        "student": {"id": student.pk, "name": str(student)},
        "group": {"id": group.pk, "name": group.name} if group else None,
        "trainers": trainers,
        "period": {"start": start.isoformat(), "end": on.isoformat()},
        "attendance": _round(row.get("attendance_rate")),
        "homework": _round(row.get("homework_rate")),
        "average_score": row.get("average_score"),
        "progress": _round(row.get("progress_rate")),
    }


def lesson_metrics(lesson: Lesson) -> dict:
    return {
        "lesson": {"id": lesson.pk, "number": lesson.lesson_number, "topic": lesson.topic},
        "date": lesson.date.isoformat(),
        "time": f"{lesson.start_time:%H:%M}–{lesson.end_time:%H:%M}",
        "group": {"id": lesson.group_id, "name": lesson.group.name},
        "teacher": {"id": lesson.effective_teacher.pk, "name": str(lesson.effective_teacher)} if lesson.effective_teacher else None,
        "subject": lesson.subject.name if lesson.subject_id else None,
        "room": lesson.room.name if lesson.room_id else None,
        "status": lesson.get_status_display(),
    }


def compute(report: TeamLeadReport) -> dict:
    start = report.period_start or report.date
    end = report.period_end or report.date
    if report.kind == ReportKind.WEEKLY:
        return academy_metrics(report.author, start, end)
    if report.kind == ReportKind.MONTHLY:
        return academy_metrics(report.author, start, end, monthly=True)
    if report.kind in (ReportKind.TRAINER_REVIEW, ReportKind.PROBATION, ReportKind.INTERNSHIP) and report.teacher_id:
        return teacher_metrics(report.teacher, start, end)
    if report.kind == ReportKind.PROBLEM_STUDENT and report.student_id:
        return student_metrics(report.student, report.date)
    if report.kind == ReportKind.LESSON_VISIT and report.lesson_id:
        return lesson_metrics(report.lesson)
    if report.kind == ReportKind.DAILY:
        entries = WorkLogEntry.objects.filter(author=report.author, date=report.date, entry_kind=WorkLogEntry.Kind.LOG)
        return {"entries": entries.count()}
    return {}
