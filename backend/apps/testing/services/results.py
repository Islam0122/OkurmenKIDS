"""Test Results — the LMS view of finished test attempts of LMS students.

A result *is* a StudentAttempt (no separate result table): finished, linked
to an academy Student, with its historical snapshot (group / teacher /
subject / test title — services.result_snapshot). Who may see which result
is the monitoring scope (services.monitoring.visible_attempts): a Teacher —
results of their groups and of the attempts they own; Team Lead / Admin —
the whole academy. Filters are monitoring's (`filter_attempts`) plus the
result ones (student, passed/failed, score range).

Every statistic here is a database aggregate (Count / Avg / Min / Max) —
no result rows are loaded into Python to compute a number.
"""
from __future__ import annotations

import io

from django.db.models import (
    Avg,
    Count,
    F,
    FloatField,
    Func,
    IntegerField,
    Max,
    Min,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce, TruncDate

from ..models import Answer, AttemptStatus, StudentAttempt
from . import monitoring

PASSED = Q(score__gte=F("session__test__passing_score"))


class JSONArrayLength(Func):
    """Length of a JSON array column (the attempt's own question list)."""

    function = "JSON_ARRAY_LENGTH"
    output_field = IntegerField()

    def as_postgresql(self, compiler, connection, **extra):
        return self.as_sql(compiler, connection, function="JSONB_ARRAY_LENGTH", **extra)


def scope(user) -> QuerySet:
    """Finished results of LMS students the user may see."""
    return monitoring.visible_attempts(user).filter(status=AttemptStatus.FINISHED, student__isnull=False)


def filtered(user, params) -> QuerySet:
    return monitoring.filter_attempts(scope(user), params)


def _answers(attempt_ref: str, **flt):
    return Subquery(
        Answer.objects.filter(attempt=OuterRef(attempt_ref), **flt)
        .order_by().values("attempt").annotate(n=Count("pk")).values("n")[:1],
        output_field=IntegerField(),
    )


def annotate_results(results: QuerySet) -> QuerySet:
    """Per-row correct / incorrect answers, question count and attempt number
    (the n-th attempt of this student at this test)."""
    attempt_no = Subquery(
        StudentAttempt.objects.filter(
            student=OuterRef("student"), session__test=OuterRef("session__test"), started_at__lte=OuterRef("started_at"),
        ).order_by().values("student").annotate(n=Count("pk")).values("n")[:1],
        output_field=IntegerField(),
    )
    return monitoring.annotate_rows(results).annotate(
        correct_count=Coalesce(_answers("pk", is_correct=True), Value(0)),
        incorrect_count=Coalesce(_answers("pk", is_correct=False), Value(0)),
        attempt_no=attempt_no,
    )


def _round(value, digits=1):
    return round(value, digits) if value is not None else None


def summary(results: QuerySet) -> dict:
    """Totals for any set of results (a group, a teacher, a test, a session…)."""
    agg = results.annotate(
        _correct=Coalesce(_answers("pk", is_correct=True), Value(0)),
        _questions=JSONArrayLength("question_ids"),
    ).aggregate(
        attempts=Count("pk"),
        students=Count("student", distinct=True),
        groups=Count("group", distinct=True),
        tests=Count("session__test", distinct=True),
        passed=Count("pk", filter=PASSED),
        average=Avg("score"),
        best=Max("score"),
        lowest=Min("score"),
        avg_correct=Avg("_correct", output_field=FloatField()),
        avg_questions=Avg("_questions", output_field=FloatField()),
    )
    attempts = agg["attempts"]
    return {
        "attempts": attempts,
        "students_tested": agg["students"],
        "groups": agg["groups"],
        "tests": agg["tests"],
        "passed": agg["passed"],
        "failed": attempts - agg["passed"],
        "pass_rate": _round(agg["passed"] / attempts * 100) if attempts else None,
        "failed_rate": _round((attempts - agg["passed"]) / attempts * 100) if attempts else None,
        "average_score": _round(agg["average"]),
        "best_score": _round(agg["best"]),
        "lowest_score": _round(agg["lowest"]),
        "average_correct": _round(agg["avg_correct"]),
        "average_questions": _round(agg["avg_questions"]),
    }


def dynamics(results: QuerySet) -> list[dict]:
    """Average result per day (by finish date)."""
    rows = (
        results.annotate(day=TruncDate("finished_at")).values("day")
        .annotate(average=Avg("score"), attempts=Count("pk"), passed=Count("pk", filter=PASSED)).order_by("day")
    )
    return [
        {"date": r["day"], "average_score": _round(r["average"]), "attempts": r["attempts"],
         "pass_rate": _round(r["passed"] / r["attempts"] * 100) if r["attempts"] else None}
        for r in rows if r["day"] is not None
    ]


def best_of(results: QuerySet, field: str, name_of) -> dict | None:
    row = (
        results.exclude(**{f"{field}__isnull": True}).values(field)
        .annotate(average=Avg("score"), attempts=Count("pk")).order_by("-average", "-attempts").first()
    )
    if row is None:
        return None
    return {"id": row[field], "name": name_of(row[field]), "average_score": _round(row["average"]), "attempts": row["attempts"]}


def overview(results: QuerySet) -> dict:
    """summary + best student / best group (teacher and dashboard blocks)."""
    from apps.academy.models import Group, Student

    data = summary(results)
    data["best_student"] = best_of(results, "student", lambda pk: str(Student.objects.filter(pk=pk).first() or ""))
    data["best_group"] = best_of(results, "group", lambda pk: getattr(Group.objects.filter(pk=pk).first(), "name", ""))
    return data


def students(results: QuerySet) -> list[dict]:
    """One row per student: attempts, average, best, last result."""
    from apps.academy.models import Student

    last = results.filter(student=OuterRef("student")).order_by("-finished_at")
    rows = (
        results.values("student")
        .annotate(
            attempts=Count("pk"), average=Avg("score"), best=Max("score"),
            last_score=Subquery(last.values("score")[:1]),
            last_passing=Subquery(last.values("session__test__passing_score")[:1]),
            last_at=Max("finished_at"),
        )
    )
    names = {s.pk: s for s in Student.objects.filter(pk__in=[r["student"] for r in rows])}
    result = []
    for r in rows:
        student = names.get(r["student"])
        if student is None:
            continue
        result.append({
            "student": {"id": student.pk, "name": str(student)},
            "attempts": r["attempts"],
            "average_score": _round(r["average"]),
            "best_score": _round(r["best"]),
            "last_score": _round(r["last_score"]),
            "last_passed": (r["last_score"] >= r["last_passing"]) if r["last_score"] is not None else None,
            "last_at": r["last_at"],
        })
    return sorted(result, key=lambda row: row["student"]["name"])


BREAKDOWNS = {
    "group": ("group", "group__name"),
    "subject": ("subject", "subject__name"),
    "teacher": ("teacher", None),
    "test": ("session__test", "session__test__title"),
}


def breakdown(results: QuerySet, by: str) -> list[dict]:
    """Average / pass rate per group, subject, teacher or test."""
    field, name_field = BREAKDOWNS[by]
    values = [field] + ([name_field] if name_field else [])
    rows = (
        results.exclude(**{f"{field}__isnull": True}).values(*values)
        .annotate(attempts=Count("pk"), students=Count("student", distinct=True), average=Avg("score"),
                  passed=Count("pk", filter=PASSED))
    )
    names = {}
    if by == "teacher":
        from apps.users.models import Teacher

        names = {t.pk: str(t) for t in Teacher.objects.select_related("user").filter(pk__in=[r[field] for r in rows])}
    result = [
        {
            "id": str(r[field]), "name": r[name_field] if name_field else names.get(r[field], ""),
            "attempts": r["attempts"], "students": r["students"], "average_score": _round(r["average"]),
            "pass_rate": _round(r["passed"] / r["attempts"] * 100) if r["attempts"] else None,
        }
        for r in rows
    ]
    return sorted(result, key=lambda row: -(row["average_score"] or 0))


EXPORT_COLUMNS = ("Студент", "Группа", "Тренер", "Тест", "Предмет", "Попытка №", "Правильно", "Неправильно",
                  "Вопросов", "Балл, %", "Статус", "Дата", "Время, мин")


def export_xlsx(results: QuerySet) -> bytes:
    """The filtered results as an Excel sheet (same columns as the table)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    sheet = book.active
    sheet.title = "Результаты тестов"
    sheet.append(EXPORT_COLUMNS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for attempt in annotate_results(results).order_by("-finished_at").iterator(chunk_size=500):
        row = monitoring.attempt_row(attempt)
        sheet.append([
            row["student_name"], (row["group"] or {}).get("name", ""), (row["teacher"] or {}).get("name", ""),
            row["test"]["title"], row["test"]["subject"], row.get("attempt_no"), row.get("correct_count"),
            row.get("incorrect_count"), row["question_total"], row["score"],
            "Өттү" if row["passed"] else "Өткөн жок",
            attempt.finished_at.strftime("%d.%m.%Y %H:%M") if attempt.finished_at else "",
            round(row["duration_seconds"] / 60, 1) if row["duration_seconds"] is not None else "",
        ])
    for column, width in zip("ABCDEFGHIJKLM", (28, 16, 22, 30, 14, 10, 10, 12, 10, 10, 12, 18, 10)):
        sheet.column_dimensions[column].width = width
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
