"""Раздел «Академия» кабинета операционного директора: группы, студенты,
успеваемость, месячные результаты и студенты, требующие внимания.

Только чтение и ничего не считается заново — каждая цифра из сервиса, который
уже считает её для остальной LMS:

* группы, студенты и общие показатели периода (посещаемость, ДЗ, тесты,
  активность, прогресс, KPI, приход/уход студентов) — Reports / KPI Engine
  (academy.services.reports: build_group_rows, build_group_detail,
  build_student_rows, build_overview);
* показатели студента внутри группы и сравнение с прошлым периодом —
  «Прогресс студентов» (academy.services.analytics.student_progress);
* пройдено / осталось занятий — план программы (academy.services.group_analytics);
* экзамены — результаты тестирования (academy.services.analytics.assessments),
  сессии типа «Экзамен»;
* XP — правила публичного рейтинга (leaderboard.student_xp);
* достижения — утверждённые стипендии (scholarships.ScholarshipAward).
  Отдельных бейджей в LMS нет — они не выдумываются;
* договор и оплаты — оплата обучения (billing.services.contracts.money_summary,
  та же функция, что в карточке договора бухгалтера; accounting.StudentPayment);
* требующие внимания — «Контроль активности» ассистента (assistant.activity)
  с его порогами (settings.ASSISTANT_CONTROL_THRESHOLDS), плюс снижение
  успеваемости к прошлому периоду по порогу оттуда же.

Запросы: списки собираются пачкой (сгруппированные запросы на весь список);
то, что считается на договор или на группу (деньги, план программы), — только
для строк текущей страницы.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Q

from apps.academy.models import Group, GroupSchedule, GroupTeacher, Lesson, Student, StudentStatusEvent
from apps.academy.services.analytics import assessments
from apps.academy.services.analytics.student_progress import group_student_progress, student_progress_detail
from apps.academy.services.group_analytics import get_group_analytics
from apps.academy.services.reports import (
    ReportFilters,
    build_all_student_rows,
    build_group_detail,
    build_group_rows,
    build_overview,
    build_student_rows,
    filter_options,
)
from apps.academy.services.reports.service import report_group_ids
from apps.assistant import activity

from .period import OpsFilters

PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
HISTORY_MONTHS = 6
LESSON_HISTORY_LIMIT = 200

# Как «Контроль активности» ассистента: пороги в settings.ASSISTANT_CONTROL_THRESHOLDS.
DECLINE_KEY = "decline_points"
LOW_TEST_KEY = "low_test_score"


def thresholds() -> dict:
    return activity.thresholds()


# ---------------------------------------------------------------------------
# Фильтры и страницы
# ---------------------------------------------------------------------------

def _int(params, name):
    value = params.get(name)
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def report_filters(f: OpsFilters, params) -> ReportFilters:
    """Период кабинета + программа / группа / тренер → фильтры Reports."""
    extra = {key: params.get(key) for key in ("program", "group", "teacher") if params.get(key)}
    return ReportFilters.from_query(f.report_query(**extra), today=f.today)


def paginate(rows: list, params) -> dict:
    page_size = min(max(_int(params, "page_size") or PAGE_SIZE, 1), MAX_PAGE_SIZE)
    count = len(rows)
    pages = max((count + page_size - 1) // page_size, 1)
    page = min(max(_int(params, "page") or 1, 1), pages)
    start = (page - 1) * page_size
    return {"count": count, "page": page, "pages": pages, "page_size": page_size,
            "results": rows[start:start + page_size]}


def month_ranges(end: dt.date, months: int = HISTORY_MONTHS) -> list[tuple[dt.date, dt.date]]:
    """Последние `months` календарных месяцев, заканчивая месяцем `end`
    (текущий месяц — по `end`, не дальше)."""
    result = []
    year, month = end.year, end.month
    for _ in range(months):
        first = dt.date(year, month, 1)
        nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
        result.append((first, min(nxt - dt.timedelta(days=1), end)))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return list(reversed(result))


def _month_filters(rf: ReportFilters, start: dt.date, end: dt.date) -> ReportFilters:
    query = {"period": "custom", "start_date": start.isoformat(), "end_date": end.isoformat()}
    for key, attr in (("program", "course_id"), ("group", "group_id"), ("teacher", "teacher_id")):
        if getattr(rf, attr):
            query[key] = getattr(rf, attr)
    return ReportFilters.from_query(query, today=rf.today)


def _money(value) -> str | None:
    return None if value is None else str(Decimal(value).quantize(Decimal("0.01")))


def options() -> dict:
    return {
        **filter_options(),
        "group_statuses": [{"value": v, "label": label} for v, label in Group.Status.choices],
        "student_statuses": [{"value": v, "label": label} for v, label in Student.Status.choices],
        "thresholds": thresholds(),
    }


# ---------------------------------------------------------------------------
# Тренеры, XP, достижения — пачкой
# ---------------------------------------------------------------------------

def trainers_by_group(group_ids) -> dict[int, list[dict]]:
    rows = (GroupTeacher.objects.filter(group_id__in=group_ids, is_active=True)
            .select_related("teacher__user", "subject").order_by("subject__name", "pk"))
    result: dict[int, list[dict]] = defaultdict(list)
    for gt in rows:
        if gt.teacher_id and all(t["id"] != gt.teacher_id for t in result[gt.group_id]):
            result[gt.group_id].append({"id": gt.teacher_id, "name": str(gt.teacher),
                                        "subject": gt.subject.name if gt.subject_id else None})
    return result


def xp_by_student(start: dt.date, end: dt.date, student_ids=None) -> dict[int, dict]:
    """XP за период по правилам рейтинга (посещаемость, ДЗ, тесты)."""
    from apps.leaderboard.services import Period, student_xp

    raw = student_xp(Period("custom", start, end))
    ids = None if student_ids is None else set(student_ids)
    return {sid: {**points, "total": sum(points.values())} for sid, points in raw.items()
            if ids is None or sid in ids}


def achievements_by_student(student_ids, start: dt.date | None = None, end: dt.date | None = None) -> dict[int, list]:
    """Утверждённые стипендии — единственные «достижения», которые LMS ведёт."""
    from apps.scholarships.models import ScholarshipAward

    qs = ScholarshipAward.objects.filter(student_id__in=student_ids, status=ScholarshipAward.Status.APPROVED)
    if start and end:
        qs = qs.filter(award_date__range=(start, end))
    result: dict[int, list] = defaultdict(list)
    for award in qs.select_related("period").order_by("-award_date"):
        result[award.student_id].append({
            "kind": "scholarship", "title": f"Стипендия — {award.rank} место", "date": award.award_date,
            "amount": _money(award.amount), "period": str(award.period),
        })
    return result


# ---------------------------------------------------------------------------
# Деньги: та же функция, что в карточке договора бухгалтера
# ---------------------------------------------------------------------------

def _contract_money(profile) -> dict:
    from apps.billing.services.contracts import money_summary

    summary = money_summary(profile)
    return {
        "original": _money(summary.get("standard_course_price")),
        "discount": _money(summary.get("discount_amount")),
        "final": _money(summary.get("final_course_price")),
        "paid": _money(summary["paid_total"]),
        "debt": _money(summary["outstanding"]),
        "due_now": _money(summary["due_now"]),
        "overdue": _money(summary["overdue"]),
        "paid_in_full": summary["course_paid_in_full"],
    }


def finance_by_student(student_ids) -> dict[int, dict]:
    """Сумма договоров студента (у студента может быть договор на каждый
    предмет): итоговая стоимость, оплачено, долг — из money_summary."""
    from apps.billing.models import StudentBillingProfile

    totals: dict[int, dict] = {}
    profiles = StudentBillingProfile.objects.filter(student_id__in=student_ids).select_related("plan")
    for profile in profiles:
        money = _contract_money(profile)
        row = totals.setdefault(profile.student_id, {"contracts": 0, "contract_amount": Decimal(0),
                                                     "paid": Decimal(0), "debt": Decimal(0), "has_amount": False})
        row["contracts"] += 1
        if money["final"] is not None:
            row["contract_amount"] += Decimal(money["final"])
            row["has_amount"] = True
        row["paid"] += Decimal(money["paid"])
        row["debt"] += Decimal(money["debt"])
    return {
        sid: {"contracts": r["contracts"], "contract_amount": _money(r["contract_amount"]) if r["has_amount"] else None,
              "paid": _money(r["paid"]), "debt": _money(r["debt"])}
        for sid, r in totals.items()
    }


def student_contracts(student: Student) -> dict:
    from apps.accounting.models import StudentPayment
    from apps.billing.models import StudentBillingProfile

    contracts = []
    for profile in (StudentBillingProfile.objects.filter(student=student)
                    .select_related("plan__course", "subject").order_by("-start_date", "-pk")):
        contracts.append({
            "id": profile.pk,
            "plan": profile.plan.name,
            "program": profile.plan.course.name if profile.plan.course_id else None,
            "subject": profile.subject.name if profile.subject_id else None,
            "status": profile.status,
            "status_display": profile.get_status_display(),
            "start_date": profile.start_date,
            "discount_reason": profile.discount_reason,
            **_contract_money(profile),
        })
    payments = (StudentPayment.objects.filter(student=student)
                .select_related("group", "course").order_by("-received_date", "-pk"))
    return {
        "contracts": contracts,
        "payments": [{
            "id": p.pk, "date": p.received_date, "amount": _money(p.amount), "kind": p.kind,
            "kind_display": p.get_kind_display(), "method_display": p.get_method_display(),
            "status": p.status, "status_display": p.get_status_display(),
            "group": p.group.name if p.group_id else None, "program": p.course.name if p.course_id else None,
            "comment": p.comment,
        } for p in payments],
    }


# ---------------------------------------------------------------------------
# Группы
# ---------------------------------------------------------------------------

def _plan_progress(group: Group, today: dt.date) -> dict:
    """Пройдено / осталось по плану программы — сводка «Аналитики группы»."""
    summary = get_group_analytics(group, today=today).summary
    total, done = summary.get("plan_total") or 0, summary.get("completed_all_time") or 0
    return {"completed": done, "planned": total, "remaining": max(total - done, 0) if total else None,
            "progress": summary.get("progress")}


def plan_progress_for(groups: list[Group]) -> dict[int, dict]:
    """То же, что `_plan_progress`, для страницы групп без полной аналитики
    каждой: план — `planned_lessons_by_program` (как в «Аналитике группы»),
    проведено — проведённые занятия группы одним запросом на все группы."""
    from apps.academy.services.lesson_generator import planned_lessons_by_program

    done = dict(Lesson.objects.filter(group__in=groups, status=Lesson.Status.COMPLETED)
                .values("group_id").annotate(n=Count("pk")).values_list("group_id", "n"))
    result = {}
    for group in groups:
        total, completed = sum(planned_lessons_by_program(group).values()), done.get(group.pk, 0)
        result[group.pk] = {
            "completed": completed, "planned": total, "remaining": max(total - completed, 0) if total else None,
            "progress": min(round(completed / total * 100, 1), 100.0) if total else None,
        }
    return result


def _group_list_row(row: dict, trainers: list[dict]) -> dict:
    return {
        "id": row["id"], "name": row["name"], "program": row["program"], "program_id": row["program_id"],
        "status": row["status"], "status_display": row["status_display"], "start_date": row["start_date"],
        "trainers": trainers or row["teachers"], "trainer_names": row["teacher_names"],
        "students": row["students"], "lessons": row["lessons"],
        "attendance_rate": row["attendance_rate"], "homework_rate": row["homework_rate"],
        "test_score_rate": row["test_score_rate"], "progress_rate": row["progress_rate"],
        "kpi": row["kpi"], "kpi_level": row["kpi_level"], "has_data": row["has_data"],
    }


def groups_page(f: OpsFilters, params) -> dict:
    rf = report_filters(f, params)
    rows = build_group_rows(rf)
    status = params.get("status")
    if status:
        rows = [r for r in rows if r["status"] == status]
    search = (params.get("search") or "").strip().lower()
    if search:
        rows = [r for r in rows if search in r["name"].lower() or search in (r["program"] or "").lower()]
    page = paginate(rows, params)
    ids = [r["id"] for r in page["results"]]
    trainers = trainers_by_group(ids)
    plans = plan_progress_for(list(Group.objects.filter(pk__in=ids)))
    results = []
    for row in page["results"]:
        item = _group_list_row(row, trainers.get(row["id"], []))
        item["plan"] = plans[row["id"]]
        results.append(item)
    rated = [r for r in rows if r["attendance_rate"] is not None]
    return {
        "filters": {**f.as_dict(), "program": rf.course_id, "teacher": rf.teacher_id, "status": status or None},
        "summary": {
            "groups": len(rows),
            "active": sum(1 for r in rows if r["status"] == Group.Status.ACTIVE),
            "students": sum(r["students"]["active"] for r in rows),
            "average_attendance": round(sum(r["attendance_rate"] for r in rated) / len(rated), 1) if rated else None,
            "attention": sum(1 for r in rows if r["kpi_level"] in ("low", "attention")),
        },
        **{**page, "results": results},
    }


def _schedule(group: Group) -> list[dict]:
    rows = (GroupSchedule.objects.filter(group=group).select_related("teacher__user", "subject", "room")
            .order_by("day_of_week", "start_time"))
    return [{
        "day": s.get_day_of_week_display(), "day_of_week": s.day_of_week,
        "start": s.start_time.strftime("%H:%M"), "end": s.end_time.strftime("%H:%M"),
        "subject": s.subject.name if s.subject_id else None, "trainer": str(s.teacher) if s.teacher_id else None,
        "room": str(s.room) if s.room_id else None,
        "is_active": getattr(s, "is_active", True),
    } for s in rows]


def _lesson_history(group: Group, rf: ReportFilters) -> list[dict]:
    lessons = (Lesson.objects.filter(group=group, date__range=(rf.start, rf.end))
               .select_related("subject", "teacher__user", "group_teacher__teacher__user")
               .annotate(marked=Count("attendance_records", distinct=True),
                         attended=Count("attendance_records", distinct=True,
                                        filter=Q(attendance_records__status__in=("present", "late"))))
               .order_by("-date", "-start_time")[:LESSON_HISTORY_LIMIT])
    result = []
    for lesson in lessons:
        teacher = lesson.effective_teacher
        result.append({
            "id": lesson.pk, "date": lesson.date, "number": lesson.lesson_number,
            "start": lesson.start_time.strftime("%H:%M") if lesson.start_time else None,
            "topic": lesson.topic, "subject": lesson.subject.name if lesson.subject_id else None,
            "trainer": str(teacher) if teacher else None,
            "status": lesson.status, "status_display": lesson.get_status_display(),
            "attendance": {"marked": lesson.marked, "attended": lesson.attended},
        })
    return result


def _exams(rf: ReportFilters, *, group_id: int | None = None, student_id: int | None = None) -> dict:
    """Тесты и экзамены периода — результаты тестирования (assessments.results_qs:
    завершённые и проверенные попытки) раздельно по типу сессии."""
    from apps.testing.models import SessionType

    scope = rf.scope()
    if group_id is not None:
        scope = dataclasses.replace(scope, group_id=group_id)
    qs = assessments.results_qs(scope, scope.date_range)
    if student_id is not None:
        qs = qs.filter(student_id=student_id)
    exam = Q(session__session_type=SessionType.EXAM)
    result = {}
    for key, flt in (("tests", ~exam), ("exams", exam)):
        agg = qs.filter(flt).aggregate(attempts=Count("pk", distinct=True),
                                       passed=Count("pk", filter=assessments.PASSED, distinct=True),
                                       average=Avg("score"))
        result[key] = {
            "attempts": agg["attempts"], "passed": agg["passed"],
            "pass_rate": round(agg["passed"] / agg["attempts"] * 100, 1) if agg["attempts"] else None,
            "average_score": round(agg["average"], 1) if agg["average"] is not None else None,
        }
    sessions = (qs.values("session_id", "session__title", "session__session_type")
                .annotate(attempts=Count("pk", distinct=True), average=Avg("score"),
                          passed=Count("pk", filter=assessments.PASSED, distinct=True))
                .order_by("-attempts")[:20])
    result["sessions"] = [{
        "id": row["session_id"], "title": row["session__title"],
        "type": "exam" if row["session__session_type"] == SessionType.EXAM else "test",
        "attempts": row["attempts"], "passed": row["passed"],
        "average_score": round(row["average"], 1) if row["average"] is not None else None,
    } for row in sessions]
    return result


def group_detail(group: Group, f: OpsFilters, params) -> dict:
    rf = dataclasses.replace(report_filters(f, params), group_id=group.pk)
    detail = build_group_detail(group, rf)
    progress = group_student_progress(group, period="custom", start_date=rf.start, end_date=rf.end, today=f.today)
    student_ids = [s["id"] for s in progress["students"]]
    xp = xp_by_student(rf.start, rf.end, student_ids)
    awards = achievements_by_student(student_ids, rf.start, rf.end)
    for row in progress["students"]:
        row["xp"] = xp.get(row["id"], {}).get("total", 0)
        row["achievements"] = len(awards.get(row["id"], []))
    monthly = []
    for start, end in month_ranges(rf.end):
        rows = build_group_rows(_month_filters(rf, start, end), [group.pk])
        row = rows[0] if rows else {}
        monthly.append({"month": start.isoformat()[:7], "start": start, "end": end,
                        "attendance_rate": row.get("attendance_rate"), "homework_rate": row.get("homework_rate"),
                        "test_score_rate": row.get("test_score_rate"), "kpi": row.get("kpi"),
                        "students": (row.get("students") or {}).get("active")})
    return {
        **detail,
        "trainers": trainers_by_group([group.pk]).get(group.pk, []),
        "plan": _plan_progress(group, f.today),
        "schedule": _schedule(group),
        "lesson_history": _lesson_history(group, rf),
        "student_progress": progress["students"],
        "assessments": _exams(rf, group_id=group.pk),
        "achievements": [{**a, "student_id": sid, "student": next((s["name"] for s in progress["students"]
                                                                   if s["id"] == sid), "")}
                         for sid, items in awards.items() for a in items],
        "xp_total": sum(r["xp"] for r in progress["students"]),
        "monthly": monthly,
        "period": {**f.as_dict()},
    }


# ---------------------------------------------------------------------------
# Студенты
# ---------------------------------------------------------------------------

def _students_qs(params):
    qs = Student.objects.select_related("group__course")
    for word in (params.get("search") or "").split()[:4]:
        qs = qs.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word) | Q(phone__icontains=word)
                       | Q(parent_phone__icontains=word) | Q(group__name__icontains=word))
    if _int(params, "group"):
        qs = qs.filter(group_id=_int(params, "group"))
    if _int(params, "program"):
        qs = qs.filter(group__course_id=_int(params, "program"))
    if _int(params, "teacher"):
        qs = qs.filter(group__teachers__teacher_id=_int(params, "teacher"), group__teachers__is_active=True).distinct()
    if params.get("status") in Student.Status.values:
        qs = qs.filter(status=params["status"])
    return qs.order_by("last_name", "first_name", "pk")


def students_page(f: OpsFilters, params, *, with_finance: bool) -> dict:
    qs = _students_qs(params)
    count = qs.count()
    page_size = min(max(_int(params, "page_size") or PAGE_SIZE, 1), MAX_PAGE_SIZE)
    pages = max((count + page_size - 1) // page_size, 1)
    page = min(max(_int(params, "page") or 1, 1), pages)
    students = list(qs[(page - 1) * page_size:page * page_size])
    rf = ReportFilters.from_query(f.report_query(), today=f.today)
    academic = {r["id"]: r for r in build_student_rows(rf, students)}
    ids = [s.pk for s in students]
    trainers = trainers_by_group({s.group_id for s in students if s.group_id})
    finance = finance_by_student(ids) if with_finance else {}
    results = []
    for s in students:
        a = academic.get(s.pk, {})
        results.append({
            "id": s.pk, "name": str(s), "status": s.status, "status_display": s.get_status_display(),
            "group": {"id": s.group_id, "name": s.group.name} if s.group_id else None,
            "program": s.group.course.name if s.group_id and s.group.course_id else None,
            "trainers": [t["name"] for t in trainers.get(s.group_id, [])],
            "enrollment_date": s.enrollment_date,
            "attendance_rate": a.get("attendance_rate"), "homework_rate": a.get("homework_rate"),
            "average_score": a.get("average_score"), "progress_rate": a.get("progress_rate"),
            "level": a.get("level"),
            "finance": finance.get(s.pk) if with_finance else None,
        })
    return {"filters": f.as_dict(), "count": count, "page": page, "pages": pages, "page_size": page_size,
            "results": results, "finance_visible": with_finance}


def student_profile(student: Student, f: OpsFilters, *, with_finance: bool) -> dict:
    group = student.group
    progress = None
    if group is not None:
        progress = student_progress_detail(group, student.pk, period="custom", start_date=f.start,
                                           end_date=f.elapsed_end, today=f.today)
    rf = ReportFilters.from_query(f.report_query(), today=f.today)
    figures = build_student_rows(rf, [student])[0]
    xp = xp_by_student(f.start, f.elapsed_end, [student.pk]).get(student.pk, {"attendance": 0, "homework": 0,
                                                                              "tests": 0, "total": 0})
    events = (StudentStatusEvent.objects.filter(student=student)
              .select_related("group", "from_group").order_by("-event_date", "-pk")[:50])
    return {
        "filters": f.as_dict(),
        "student": {
            "id": student.pk, "name": str(student), "status": student.status,
            "status_display": student.get_status_display(), "enrollment_date": student.enrollment_date,
            "group": {"id": group.pk, "name": group.name, "status_display": group.get_status_display()} if group else None,
            "program": group.course.name if group and group.course_id else None,
            "trainers": trainers_by_group([group.pk]).get(group.pk, []) if group else [],
        },
        "academic": {
            **figures,
            "period": progress["student"] if progress else None,
            "lessons": progress["lessons"] if progress else [],
            "tests": progress["tests"] if progress else [],
            "assessments": _exams(rf, student_id=student.pk),
            "xp": xp,
            "achievements": achievements_by_student([student.pk]).get(student.pk, []),
            "badges_tracked": False,
        },
        "history": [{
            "date": e.event_date, "type": e.event_type, "type_display": e.get_event_type_display(),
            "group": e.group.name if e.group_id else None,
            "from_group": e.from_group.name if e.from_group_id else None,
        } for e in events],
        "finance": student_contracts(student) if with_finance else None,
    }


# ---------------------------------------------------------------------------
# Успеваемость и месячные результаты
# ---------------------------------------------------------------------------

def _overview(rf: ReportFilters, *, group_rows=None) -> dict:
    """`build_overview` без разделов тренеров и предметов: здесь нужны только
    студенты, посещаемость, ДЗ, тесты, прогресс и KPI периода (их расчёт
    от этих разделов не зависит), а группы — уже посчитанные строки."""
    return build_overview(rf, group_rows=build_group_rows(rf) if group_rows is None else group_rows,
                          teacher_rows=[], subject_rows=[])


def _indicators(rf: ReportFilters, *, group_rows=None) -> dict:
    overview = _overview(rf, group_rows=group_rows)
    attendance, homework, tests = overview["attendance"], overview["homework"], overview["tests"]
    return {
        "attendance_rate": attendance["rate"],
        "attended": attendance["present"] + attendance["late"],
        "missed": attendance["absent"] + attendance["excused"],
        "homework_rate": homework["completion_rate"],
        "homework_average": homework["average_score"],
        "test_average": tests["average_score"],
        # Успеваемость — показатель KPI «Прогресс (средний балл ДЗ)», KPI — итог KPI Engine.
        "progress_rate": (overview.get("metrics") or {}).get("progress"),
        "kpi": (overview.get("kpi") or {}).get("total"),
        "kpi_level": (overview.get("kpi") or {}).get("status"),
        "students": overview["students"],
        "groups": overview["groups"],
        "_overview": overview,
    }


def _change(current, previous):
    if current is None or previous is None:
        return None
    return round(current - previous, 1)


def _previous(f: OpsFilters) -> OpsFilters:
    return f.previous()


def performance(f: OpsFilters, params) -> dict:
    rf = report_filters(f, params)
    prev_f = _previous(f)
    prev_rf = report_filters(prev_f, params)
    current, previous = _indicators(rf), _indicators(prev_rf)
    group_ids = report_group_ids(rf)
    rows = build_all_student_rows(rf, group_ids)
    students = Student.objects.filter(pk__in=[r["id"] for r in rows])
    prev_rows = {r["id"]: r for r in build_student_rows(prev_rf, students)}
    ids = [r["id"] for r in rows]
    xp = xp_by_student(rf.start, rf.end, ids)
    prev_xp = xp_by_student(prev_rf.start, prev_rf.end, ids)
    awards = achievements_by_student(ids, rf.start, rf.end)
    for row in rows:
        before = prev_rows.get(row["id"], {})
        row["xp"] = xp.get(row["id"], {}).get("total", 0)
        row["achievements"] = len(awards.get(row["id"], []))
        row["missed"] = row["attendance_total"] - row["attended"]
        row["change"] = {key: _change(row.get(key), before.get(key))
                         for key in ("attendance_rate", "homework_rate", "average_score")}
    exams = _exams(rf)
    prev_exams = _exams(prev_rf)
    indicators = {key: value for key, value in current.items() if not key.startswith("_")}
    xp_total, prev_xp_total = sum(r["xp"] for r in rows), sum(v["total"] for v in prev_xp.values())
    order = params.get("ordering") or "name"
    sorters = {
        "name": lambda r: r["name"].lower(), "attendance": lambda r: (r["attendance_rate"] is None, r["attendance_rate"] or 0),
        "homework": lambda r: (r["homework_rate"] is None, r["homework_rate"] or 0), "xp": lambda r: -r["xp"],
        "change": lambda r: (r["change"]["attendance_rate"] is None, r["change"]["attendance_rate"] or 0),
    }
    rows.sort(key=sorters.get(order, sorters["name"]))
    # Активность студентов: доля студентов периода, посетивших хотя бы одно занятие.
    active_now = sum(1 for r in rows if r["attended"])
    active_before = sum(1 for r in prev_rows.values() if r.get("attended"))
    current["activity_rate"] = round(active_now / len(rows) * 100, 1) if rows else None
    previous["activity_rate"] = round(active_before / len(prev_rows) * 100, 1) if prev_rows else None
    indicators["activity_rate"] = current["activity_rate"]
    return {
        "filters": {**f.as_dict(), "program": rf.course_id, "group": rf.group_id, "teacher": rf.teacher_id},
        "previous_period": {"start": prev_f.start, "end": prev_f.end},
        "indicators": {
            **indicators,
            "exams": exams["exams"], "tests": exams["tests"],
            "xp": xp_total, "achievements": sum(len(v) for v in awards.values()),
            "active_students": active_now, "students": len(rows),
        },
        "previous": {
            "attendance_rate": previous["attendance_rate"], "attended": previous["attended"],
            "missed": previous["missed"], "homework_rate": previous["homework_rate"],
            "test_average": previous["test_average"], "progress_rate": previous["progress_rate"],
            "activity_rate": previous["activity_rate"], "exams": prev_exams["exams"], "xp": prev_xp_total,
        },
        "change": {key: _change(current[key], previous[key])
                   for key in ("attendance_rate", "homework_rate", "test_average", "progress_rate", "activity_rate")},
        "badges_tracked": False,
        **paginate(rows, params),
    }


def _activity_reasons(row, t: dict) -> list[str]:
    """Причины из «Контроля активности» ассистента — по его же категориям и порогам."""
    reasons = []
    if "frequent_absence" in row.categories:
        reasons.append(f"Частые пропуски: {row.absent} за период (порог {t['frequent_absences']})")
    if row.consecutive_absences >= t["consecutive_absences"]:
        reasons.append(f"Пропустил подряд: {row.consecutive_absences} занятия")
    if row.attendance is not None and row.marked >= t["min_marked_lessons"] and row.attendance < t["low_attendance"]:
        reasons.append(f"Низкая посещаемость: {row.attendance}% (порог {t['low_attendance']}%)")
    if row.homework is not None and row.homework_due >= t["min_due_homework"] and row.homework < t["low_homework"]:
        reasons.append(f"Не выполняет ДЗ: {row.homework}% (порог {t['low_homework']}%)")
    if row.consecutive_missed_homework >= t["consecutive_missed_homework"]:
        reasons.append(f"Не сдал подряд: {row.consecutive_missed_homework} ДЗ")
    if "stale_homework" in row.categories:
        reasons.append(f"Не сдаёт ДЗ больше {t['stale_homework_days']} дней")
    return reasons


def attention(f: OpsFilters, rf: ReportFilters, prev_rf: ReportFilters) -> list[dict]:
    """Требующие внимания: «Контроль активности» ассистента (частые пропуски,
    низкая посещаемость, не делают ДЗ) + низкие результаты тестов и снижение
    успеваемости к прошлому периоду. Все пороги — ASSISTANT_CONTROL_THRESHOLDS."""
    t = thresholds()
    group_ids = set(report_group_ids(rf))
    students = [s for s in activity.control_students() if s.group_id in group_ids]
    by_student = {s.pk: s for s in students}
    rows, _ = activity.analyse_students(students, start=rf.start, today=f.today)
    entries: dict[int, dict] = {}

    def entry(student_id: int, status: str, attendance=None, homework=None) -> dict:
        student = by_student[student_id]
        return entries.setdefault(student_id, {
            "id": student_id, "name": str(student),
            "group": student.group.name if student.group_id else None, "group_id": student.group_id,
            "status": status, "status_display": activity.STATUS_LABELS.get(status, status),
            "attendance_rate": attendance, "homework_rate": homework, "reasons": [],
        })

    for row in rows:
        reasons = _activity_reasons(row, t)
        if reasons:
            entry(row.student_id, row.status, row.attendance, row.homework)["reasons"].extend(reasons)

    current = {r["id"]: r for r in build_student_rows(rf, students)}
    previous = {r["id"]: r for r in build_student_rows(prev_rf, students)}
    scope = rf.scope()
    test_scores = dict(assessments.results_qs(scope, scope.date_range).filter(student_id__in=list(by_student))
                       .values("student_id").annotate(a=Avg("score")).values_list("student_id", "a"))
    for student_id in by_student:
        extra = []
        score = test_scores.get(student_id)
        if score is not None and score < t[LOW_TEST_KEY]:
            extra.append(f"Низкие результаты тестов: {round(score, 1)} из 100 (порог {t[LOW_TEST_KEY]})")
        now, before = current.get(student_id, {}), previous.get(student_id, {})
        for key, label in (("attendance_rate", "Снизилась посещаемость"), ("homework_rate", "Снизилось выполнение ДЗ")):
            if now.get(key) is not None and before.get(key) is not None and before[key] - now[key] >= t[DECLINE_KEY]:
                extra.append(f"{label}: {before[key]}% → {now[key]}% (порог −{t[DECLINE_KEY]} п.п.)")
        if extra:
            entry(student_id, activity.STATUS_ATTENTION, now.get("attendance_rate"),
                  now.get("homework_rate"))["reasons"].extend(extra)
    return sorted(entries.values(), key=lambda r: (activity.STATUS_ORDER.get(r["status"], 9), -len(r["reasons"]),
                                                   r["name"]))


def monthly(f: OpsFilters, params) -> dict:
    rf = report_filters(f, params)
    prev_rf = report_filters(_previous(f), params)
    scope_groups = report_group_ids(rf)
    group_rows = build_group_rows(rf, scope_groups)
    current = _indicators(rf, group_rows=group_rows)
    overview = current.pop("_overview")
    transfers = StudentStatusEvent.objects.filter(
        event_type=StudentStatusEvent.EventType.TRANSFERRED, event_date__range=(rf.start, rf.end),
    ).filter(Q(group_id__in=scope_groups) | Q(from_group_id__in=scope_groups)).count()
    student_ids = list(Student.objects.filter(group_id__in=scope_groups).values_list("pk", flat=True))
    awards = achievements_by_student(student_ids, rf.start, rf.end)
    xp = xp_by_student(rf.start, rf.end, student_ids)
    attention_rows = attention(f, rf, prev_rf)
    dynamics = []
    for start, end in month_ranges(rf.end):
        month = overview if (start, end) == (rf.start, rf.end) else _overview(_month_filters(rf, start, end), group_rows=[])
        dynamics.append({
            "month": start.isoformat()[:7], "start": start, "end": end,
            "attendance_rate": month["attendance"]["rate"], "homework_rate": month["homework"]["completion_rate"],
            "test_average": month["tests"]["average_score"], "progress_rate": (month.get("metrics") or {}).get("progress"),
            "kpi": (month.get("kpi") or {}).get("total"), "active": month["students"]["active"], "new": month["students"]["new"],
            "left": month["students"]["left"],
        })
    return {
        "filters": {**f.as_dict(), "program": rf.course_id, "group": rf.group_id, "teacher": rf.teacher_id},
        "indicators": {
            "active_students": overview["students"]["active"], "new_students": overview["students"]["new"],
            "left_students": overview["students"]["left"], "returned_students": overview["students"]["returned"],
            "transferred_students": transfers,
            "attendance_rate": current["attendance_rate"], "homework_rate": current["homework_rate"],
            "academic_performance": current["progress_rate"], "test_average": current["test_average"],
            "kpi": current["kpi"], "achievements": sum(len(v) for v in awards.values()),
            "xp": sum(v["total"] for v in xp.values()),
            "attention": len(attention_rows), "groups": overview["groups"]["total"],
        },
        "dynamics": dynamics,
        "groups": [{
            "id": r["id"], "name": r["name"], "program": r["program"], "students": r["students"]["active"],
            "attendance_rate": r["attendance_rate"], "homework_rate": r["homework_rate"],
            "test_score_rate": r["test_score_rate"], "kpi": r["kpi"], "kpi_level": r["kpi_level"],
        } for r in group_rows],
        "attention": attention_rows,
        "thresholds": thresholds(),
        "badges_tracked": False,
    }


__all__ = ["groups_page", "group_detail", "students_page", "student_profile", "performance", "monthly",
           "attention", "options", "finance_by_student", "student_contracts"]
