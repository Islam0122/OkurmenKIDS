"""Scholarship analytics and ranking export — read-only, computed from the
stored evaluations (the numbers a ranking was actually decided on)."""
from __future__ import annotations

import csv
import io
from collections import Counter

from django.db.models import Avg, Count, F, Q

from ..models import EligibilityStatus, ScholarshipAward, ScholarshipEvaluation, ScholarshipPeriod, ScholarshipSubjectScore


def _avg(value):
    return round(value, 2) if value is not None else None


def period_analytics(period: ScholarshipPeriod) -> dict:
    evaluations = period.evaluations.all()
    eligible = evaluations.filter(eligibility_status=EligibilityStatus.ELIGIBLE)
    averages = eligible.aggregate(
        overall=Avg("overall_score"),
        attendance=Avg("attendance_score"),
        homework=Avg("homework_score"),
        feedback=Avg("feedback_score"),
    )
    status_counts = Counter(evaluations.values_list("eligibility_status", flat=True))
    status_labels = dict(EligibilityStatus.choices)

    subjects = (
        ScholarshipSubjectScore.objects.filter(evaluation__period=period, aggregation_weight__gt=0)
        .values("subject_id", "subject_name")
        .annotate(
            students=Count("evaluation", distinct=True),
            subject_score=Avg("subject_score"),
            attendance=Avg("attendance_score"),
            homework=Avg("homework_score"),
            feedback=Avg("feedback_score"),
        )
        .order_by("subject_name")
    )

    return {
        "period_id": period.id,
        "total_evaluated": evaluations.count(),
        "total_eligible": eligible.count(),
        "total_recipients": period.awards.count(),
        "max_recipients": period.max_recipients,
        "incomplete_data": status_counts.get(EligibilityStatus.INCOMPLETE_DATA, 0),
        "with_data_warnings": evaluations.exclude(data_warnings=[]).count(),
        "ineligible": sum(n for key, n in status_counts.items() if key != EligibilityStatus.ELIGIBLE),
        "by_status": [
            {"status": key, "label": status_labels[key], "count": status_counts.get(key, 0)}
            for key, _ in EligibilityStatus.choices
        ],
        "averages": {key: _avg(value) for key, value in averages.items()},
        "subjects": [
            {
                "subject_id": row["subject_id"],
                "subject_name": row["subject_name"],
                "students": row["students"],
                "subject_score": _avg(row["subject_score"]),
                "attendance": _avg(row["attendance"]),
                "homework": _avg(row["homework"]),
                "feedback": _avg(row["feedback"]),
            }
            for row in subjects
        ],
    }


def awards_by_month() -> list[dict]:
    rows = (
        ScholarshipAward.objects.values("period__evaluation_date__year", "period__evaluation_date__month")
        .annotate(
            total=Count("id"),
            approved=Count("id", filter=Q(status=ScholarshipAward.Status.APPROVED)),
        )
        .order_by("period__evaluation_date__year", "period__evaluation_date__month")
    )
    return [
        {
            "year": row["period__evaluation_date__year"],
            "month": row["period__evaluation_date__month"],
            "total": row["total"],
            "approved": row["approved"],
        }
        for row in rows
    ]


def ranking_queryset(period: ScholarshipPeriod):
    return (
        ScholarshipEvaluation.objects.filter(period=period)
        .select_related("student", "award")
        .prefetch_related("subject_scores")
        .order_by(F("rank").asc(nulls_last=True), F("overall_score").desc(nulls_last=True), "student_name", "id")
    )


def _fmt(value) -> str:
    return "" if value is None else str(value)


def export_ranking_csv(period: ScholarshipPeriod) -> str:
    buffer = io.StringIO()
    buffer.write("﻿")  # BOM so Excel opens Cyrillic correctly
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([
        "Место", "Студент", "Группа", "Курс", "Дата начала обучения", "Итоговый балл",
        "Посещаемость", "ДЗ", "Оценка тренера", "Занятий", "Предметы", "Допуск", "Причина",
        "Стипендия", "Статус стипендии", "Предупреждения",
    ])
    for evaluation in ranking_queryset(period):
        award = getattr(evaluation, "award", None)
        subjects = "; ".join(
            f"{s.subject_name}: {_fmt(s.subject_score)}" for s in evaluation.subject_scores.all()
        )
        writer.writerow([
            _fmt(evaluation.rank), evaluation.student_name, evaluation.group_name, evaluation.course_name,
            _fmt(evaluation.enrollment_date), _fmt(evaluation.overall_score), _fmt(evaluation.attendance_score),
            _fmt(evaluation.homework_score), _fmt(evaluation.feedback_score), evaluation.lessons_count, subjects,
            evaluation.get_eligibility_status_display(), evaluation.ineligibility_reason,
            "да" if award else "нет", award.get_status_display() if award else "",
            " | ".join(evaluation.data_warnings),
        ])
    return buffer.getvalue()
