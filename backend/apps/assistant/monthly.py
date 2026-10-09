"""«Месячный отчёт» of the Assistant — one month (`year` + `month`), one
page: students and groups, attendance, homework, who needs attention,
surveys, scholarships, activity, inactive and departed students, why they
leave, finance, month over month, retention advice and the conclusions
(the retention part lives in retention.py).

Nothing is stored and nothing is written: the report is computed on demand
from the academy, feedback and scholarships data («Сформировать» /
«Обновить» simply recompute it). A past month is rebuilt as it was: who was
active and in which group on its last day comes from the status history
(history.py), not from today's status. A student's trainer appears only as
context of their group; trainer KPI and workload are the Team Lead's report.

Definitions are the ones the rest of the Assistant uses
(apps.assistant.activity / records): a held lesson is `held_q` without
cancelled ones; attended = PRESENT + LATE, an absence = ABSENT, EXCUSED is
neutral; a homework done = SUBMITTED / CHECKED / LATE, «на проверке» =
SUBMITTED / LATE; a homework counts once its deadline has passed (no
deadline: once its lesson is held). The month runs from the 1st 00:00 to
the last day 23:59 in the project's timezone; lessons and homework after
today never count.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
from collections import Counter, defaultdict
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Attendance, Group, Homework, HomeworkResult, Lesson, Student, StudentStatusEvent
from apps.academy.services.lesson_status import held_q
from apps.feedback.models import Survey, SurveyAnswer, SurveyAnswerOption, SurveyQuestion, SurveyResponse
from apps.scholarships.models import PaymentStatus, ScholarshipAward

from . import activity, history, retention
from .activity import ATTENDED
from .records import homework_row

MONTHS = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)
# The month's conclusions: «хорошо» from GOOD_*, a group «требует внимания» below LOW_GROUP_*.
GOOD_ATTENDANCE = 85
GOOD_HOMEWORK = 80
LOW_GROUP_ATTENDANCE = 70
LOW_GROUP_HOMEWORK = 60
LOW_PARTICIPATION = 50
GOOD_RATING = 4.0  # of 5
LOW_RATING_SHARE = 0.4  # an answer at or below 40% of the scale is a «проблемный ответ»
TEXT_LIMIT = 12


class ReportError(ValueError):
    pass


def _pct(part: int, whole: int) -> int | None:
    return round(part / whole * 100) if whole else None


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise ReportError("Неверный месяц или год.")
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def _aware(day: dt.date) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, dt.time.min))


def _ref(obj) -> dict | None:
    return {"id": obj.pk, "name": str(obj)} if obj is not None else None


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _overview(start: dt.date, end: dt.date, state: dict) -> dict:
    # Existed in the month: started (or, without a start date, created) by its end, not finished before it.
    groups = Group.objects.filter(
        Q(start_date__lte=end) | Q(start_date__isnull=True, created_at__date__lte=end),
    ).exclude(end_date__lt=start)
    active_groups = groups.filter(status=Group.Status.ACTIVE).count()
    total_groups = groups.count()
    statuses = Counter(r.status for r in state["roster"].values())
    return {
        "groups_total": total_groups,
        "groups_active": active_groups,
        "groups_inactive": total_groups - active_groups,
        # Students on the month's last day — rebuilt from the status history, not today's status.
        "students_total": sum(statuses.values()) - statuses[Student.Status.COMPLETED],
        "students_active": statuses[Student.Status.ACTIVE],
        "students_paused": statuses[Student.Status.PAUSED],
        "students_withdrawn": statuses[Student.Status.WITHDRAWN],
        "students_completed": statuses[Student.Status.COMPLETED],
        "students_new": Student.objects.filter(enrollment_date__gte=start, enrollment_date__lte=end).count(),
        "students_deactivated": retention.departed_count(start, end),
    }


def month_state(start: dt.date, until: dt.date, today: dt.date) -> dict:
    """Everything the sections share for one month: who was active and in
    which group on its last counted day (history.roster_on), their activity
    over the month and the month's held lessons."""
    roster = {r.student.pk: r for r in history.roster_on(until)}
    groups = history.groups_by_id(list(roster.values()))
    active = [
        r for r in roster.values()
        if r.status == Student.Status.ACTIVE and r.group_id in groups
        and groups[r.group_id].status != Group.Status.CANCELLED and history.started_by(groups[r.group_id], until, start)
    ]
    rows, _ = activity.analyse_students(
        [r.student for r in active], start=start, until=until, today=today,
        groups={r.student.pk: groups[r.group_id] for r in active},
    )
    rows = [r for r in rows if r.lessons or r.homework_due]  # had a lesson or a due homework this month
    return {
        "roster": roster,
        "groups": groups,
        "active_count": sum(1 for r in roster.values() if r.status == Student.Status.ACTIVE),
        "roster_counts": dict(Counter(r.group_id for r in active)),
        "activity_rows": rows,
        "lessons": _held_lessons(start, until, today),
    }


def _held_lessons(start: dt.date, until: dt.date, today: dt.date) -> list[Lesson]:
    return list(
        Lesson.objects.filter(held_q(today), date__gte=start, date__lte=until)
        .exclude(status=Lesson.Status.CANCELLED)
        .select_related("group")
    )


def _active_counts(group_ids) -> dict[int, int]:
    """Today's active students per group — for surveys answered now."""
    counts: Counter = Counter(
        Student.objects.filter(group_id__in=group_ids, status=Student.Status.ACTIVE).values_list("group_id", flat=True)
    )
    return dict(counts)


def _attendance(lessons: list[Lesson], roster: dict[int, int]) -> dict:
    per_group: dict[int, dict] = {}
    for lesson in lessons:
        row = per_group.setdefault(lesson.group_id, {
            "group": _ref(lesson.group), "students": roster.get(lesson.group_id, 0), "lessons": 0,
            "attended": 0, "absent": 0, "excused": 0, "marked": 0,
        })
        row["lessons"] += 1
    totals = Counter()
    for group_id, status in Attendance.objects.filter(lesson__in=lessons).values_list("lesson__group_id", "status"):
        row = per_group[group_id]
        row["marked"] += 1
        if status in ATTENDED:
            row["attended"] += 1
        elif status == Attendance.Status.ABSENT:
            row["absent"] += 1
        else:
            row["excused"] += 1
    for row in per_group.values():
        row["percent"] = _pct(row["attended"], row["marked"])
        totals.update({k: row[k] for k in ("lessons", "attended", "absent", "excused", "marked")})
    groups = sorted(per_group.values(), key=lambda r: (r["percent"] if r["percent"] is not None else 101, r["group"]["name"]))
    return {
        "lessons": totals["lessons"], "marked": totals["marked"], "attended": totals["attended"],
        "absent": totals["absent"], "excused": totals["excused"],
        "percent": _pct(totals["attended"], totals["marked"]),
        "groups": groups,
    }


def _homework(lessons: list[Lesson], roster: dict[int, int]) -> dict:
    homeworks = list(Homework.objects.filter(lesson__in=lessons).select_related("lesson", "lesson__group"))
    results = defaultdict(list)
    for result in HomeworkResult.objects.filter(homework__in=homeworks):
        results[result.homework_id].append(result)
    per_group: dict[int, dict] = {}
    totals = Counter()
    for hw in homeworks:
        row = homework_row(hw, roster.get(hw.lesson.group_id, 0), results[hw.pk])
        group = per_group.setdefault(hw.lesson.group_id, {
            "group": _ref(hw.lesson.group), "homeworks": 0, "due": 0, "done": 0, "not_done": 0, "pending": 0,
            "expected": 0,
        })
        group["homeworks"] += 1
        group["pending"] += row["pending"]
        if row["due"]:
            # Only a homework past its deadline is judged: done vs not handed in.
            group["due"] += 1
            group["done"] += row["done"]
            group["not_done"] += row["not_done"]
            group["expected"] += row["expected"]
    for group in per_group.values():
        group["percent"] = _pct(group["done"], group["expected"])
        totals.update({k: group[k] for k in ("homeworks", "due", "done", "not_done", "pending", "expected")})
    groups = sorted(per_group.values(), key=lambda r: (r["percent"] if r["percent"] is not None else 101, r["group"]["name"]))
    return {
        "given": totals["homeworks"], "due": totals["due"], "done": totals["done"], "not_done": totals["not_done"],
        "pending": totals["pending"], "expected": totals["expected"],
        "percent": _pct(totals["done"], totals["expected"]),
        "groups": groups,
    }


def _reason(row: activity.StudentActivity) -> str:
    """Why the student is flagged — from the same categories «Контроль» set."""
    no_activity = (row.marked or row.homework_due) and not row.attended and not row.homework_done
    if no_activity:
        return "Нет активности"
    attending, homework = "not_attending" in row.categories, "no_homework" in row.categories
    if attending and homework:
        return "Низкая посещаемость + низкое выполнение ДЗ"
    if attending:
        return "Низкая посещаемость"
    if homework:
        return "Не выполняет ДЗ"
    return row.status_label


def _student_row(row: activity.StudentActivity) -> dict:
    return {
        "reason": _reason(row),
        "student_id": row.student_id, "name": row.name, "group": row.group,
        "attendance": row.attendance, "attended": row.attended, "marked": row.marked, "absent": row.absent,
        "consecutive_absences": row.consecutive_absences,
        "homework": row.homework, "homework_done": row.homework_done, "homework_due": row.homework_due,
        "homework_missed": row.homework_missed, "consecutive_missed_homework": row.consecutive_missed_homework,
        "last_activity": row.last_activity, "status": row.status, "status_label": row.status_label,
    }


def _students(rows: list[activity.StudentActivity]) -> dict:
    """Who needs attention — «Контроль активности» over the month: students
    active on its last day in started groups, their stint in that group."""
    by_attendance = sorted(
        (r for r in rows if "not_attending" in r.categories),
        key=lambda r: (r.attendance if r.attendance is not None else 101, -r.consecutive_absences),
    )
    by_homework = sorted(
        (r for r in rows if "no_homework" in r.categories),
        key=lambda r: (r.homework if r.homework is not None else 101, -r.consecutive_missed_homework),
    )
    risk = sorted(
        (r for r in rows if r.status == activity.STATUS_RISK),
        key=lambda r: ((r.attendance or 0) + (r.homework or 0), r.last_activity or dt.date.min),
    )
    no_activity = [r for r in rows if (r.marked or r.homework_due) and not r.attended and not r.homework_done]
    statuses = Counter(r.status for r in rows)
    return {
        "attendance_attention": [_student_row(r) for r in by_attendance],
        "homework_attention": [_student_row(r) for r in by_homework],
        "risk": [_student_row(r) for r in risk],
        "activity": {
            "analysed": len(rows),
            "normal": statuses[activity.STATUS_NORMAL],
            "attention": statuses[activity.STATUS_ATTENTION],
            "low": statuses[activity.STATUS_LOW] + statuses[activity.STATUS_RISK],
            "risk": statuses[activity.STATUS_RISK],
            "no_data": statuses[activity.STATUS_NO_DATA],
            "not_attending": len(by_attendance),
            "no_homework": len(by_homework),
            "no_activity": len(no_activity),
        },
        "no_activity": [_student_row(r) for r in no_activity],
    }


def _rating_scale(question: SurveyQuestion) -> dict[int, int] | None:
    """A single-choice question whose options are all numbers (1…5, 1…10)
    is a rating; anything else is not averaged — free-form questions have
    no honest «average» (see feedback.services.analytics)."""
    if question.question_type != SurveyQuestion.QuestionType.SINGLE_CHOICE:
        return None
    values = {}
    for option in question.options.all():
        text = option.text.strip()
        if not re.fullmatch(r"\d{1,2}", text):
            return None
        values[option.pk] = int(text)
    if len(values) < 3 or min(values.values()) < 0 or max(values.values()) > 10:
        return None
    return values


def _normalise(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def _surveys(start: dt.date, end: dt.date) -> dict:
    lo, hi = _aware(start), _aware(end + dt.timedelta(days=1))
    responses = SurveyResponse.objects.filter(submitted_at__gte=lo, submitted_at__lt=hi)
    surveys = list(
        Survey.objects.filter(Q(responses__in=responses) | Q(published_at__gte=lo, published_at__lt=hi))
        .distinct().select_related("group").prefetch_related("questions__options").order_by("title")
    )
    roster = _active_counts([s.group_id for s in surveys if s.group_id])
    count_by_survey = Counter(responses.values_list("survey_id", flat=True))
    option_counts = Counter(
        SurveyAnswerOption.objects.filter(answer__response__in=responses).values_list("option_id", flat=True)
    )

    rows, scores, expected_total, answered_total = [], [], 0, 0
    for survey in surveys:
        participants = count_by_survey.get(survey.pk, 0)
        expected = roster.get(survey.group_id) if survey.group_id else None
        weighted, n, low = 0.0, 0, 0
        for question in survey.questions.all():
            scale = _rating_scale(question)
            if not scale:
                continue
            top = max(scale.values())
            for option_id, value in scale.items():
                count = option_counts.get(option_id, 0)
                weighted += value / top * 5 * count
                n += count
                if value <= top * LOW_RATING_SHARE:
                    low += count
        average = round(weighted / n, 1) if n else None
        if n:
            scores.append((weighted, n))
        if expected:
            expected_total += expected
            answered_total += min(participants, expected)
        rows.append({
            "id": survey.pk, "title": survey.title, "group": _ref(survey.group),
            "audience": survey.audience, "audience_display": survey.get_audience_display(),
            "status": survey.status, "status_display": survey.get_status_display(),
            "participants": participants, "expected": expected,
            "participation": _pct(min(participants, expected), expected) if expected else None,
            "average": average, "ratings": n, "low_ratings": low,
        })

    texts = list(
        SurveyAnswer.objects.filter(response__in=responses, question__question_type=SurveyQuestion.QuestionType.TEXT)
        .exclude(text_value="").select_related("response__survey", "question").order_by("-response__submitted_at")
    )
    repeated = Counter(_normalise(a.text_value) for a in texts)
    seen, quotes = set(), []
    # Repeated answers first (what many say), then the latest ones — real text only.
    for answer in sorted(texts, key=lambda a: -repeated[_normalise(a.text_value)]):
        key = _normalise(answer.text_value)
        if not key or key in seen:
            continue
        seen.add(key)
        quotes.append({
            "text": answer.text_value.strip()[:500], "count": repeated[key],
            "survey": answer.response.survey.title, "question": answer.question.text,
            "date": timezone.localtime(answer.response.submitted_at).date(),
        })
        if len(quotes) >= TEXT_LIMIT:
            break

    total_weight = sum(n for _, n in scores)
    return {
        "surveys": len(rows),
        "participants": sum(r["participants"] for r in rows),
        "participation": _pct(answered_total, expected_total),
        "average": round(sum(w for w, _ in scores) / total_weight, 1) if total_weight else None,
        "low_ratings": sum(r["low_ratings"] for r in rows),
        "rows": rows,
        "quotes": quotes,
        "texts_total": len(texts),
    }


def _scholarships(start: dt.date, end: dt.date) -> dict:
    awards = list(
        ScholarshipAward.objects.filter(award_date__gte=start, award_date__lte=end)
        .select_related("student__group", "period", "evaluation").order_by("rank")
    )
    rows = []
    for award in awards:
        evaluation = award.evaluation
        reason = f"{award.rank} место в рейтинге"
        if evaluation is not None and evaluation.overall_score is not None:
            reason += f" · итоговый балл {evaluation.overall_score}"
        group_name = (evaluation.group_name if evaluation is not None else "") or (
            award.student.group.name if award.student.group_id else "")
        rows.append({
            "id": award.pk, "student": _ref(award.student), "group": group_name,
            "title": award.period.title, "amount": award.amount, "reason": reason,
            "status": award.status, "status_display": award.get_status_display(),
            "payment_status": award.payment_status, "payment_display": award.get_payment_status_display(),
            "award_date": award.award_date,
        })
    total = sum((a.amount for a in awards), Decimal("0"))
    paid = [a for a in awards if a.payment_status == PaymentStatus.PAID]
    return {
        "awards": len(awards),
        "recipients": len({a.student_id for a in awards}),
        "total_amount": total,
        "paid": len(paid),
        "paid_amount": sum((a.paid_amount or Decimal("0") for a in paid), Decimal("0")),
        "groups": sorted({r["group"] for r in rows if r["group"]}),
        "rows": rows,
    }


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _students_word(n: int) -> str:
    return f"{n} {_plural(n, 'студент', 'студента', 'студентов')}"


def _conclusions(report: dict) -> dict:
    """Rule-based, from the numbers above only — no invented advice."""
    good, attention = [], []
    att, hw, st, sv = report["attendance"], report["homework"], report["students"], report["surveys"]
    act = st["activity"]
    if att["percent"] is not None:
        if att["percent"] >= GOOD_ATTENDANCE:
            good.append(f"Средняя посещаемость {att['percent']}% — выше {GOOD_ATTENDANCE}%.")
        for g in att["groups"]:
            if g["percent"] is not None and g["percent"] < LOW_GROUP_ATTENDANCE:
                attention.append(f"В {g['group']['name']} низкая посещаемость — {g['percent']}%.")
    if hw["percent"] is not None:
        if hw["percent"] >= GOOD_HOMEWORK:
            good.append(f"Высокое выполнение ДЗ — {hw['percent']}%.")
        for g in hw["groups"]:
            if g["percent"] is not None and g["percent"] < LOW_GROUP_HOMEWORK:
                attention.append(f"В {g['group']['name']} ДЗ выполняют на {g['percent']}%.")
    if act["analysed"] and act["normal"] / act["analysed"] >= 0.75:
        good.append(f"У {act['normal']} из {act['analysed']} студентов активность в норме.")
    if sv["average"] is not None and sv["average"] >= GOOD_RATING:
        good.append(f"Хорошие результаты опросов — средняя оценка {sv['average']} из 5.")
    if report["scholarships"]["awards"]:
        good.append(f"Стипендии получили: {_students_word(report['scholarships']['recipients'])}.")

    if st["attendance_attention"]:
        attention.append(f"Низкая посещаемость: {_students_word(len(st['attendance_attention']))}.")
    if st["homework_attention"]:
        attention.append(f"Не сдают ДЗ: {_students_word(len(st['homework_attention']))}.")
    if st["risk"]:
        attention.append(f"В зоне риска: {_students_word(len(st['risk']))}.")
    if act["no_activity"]:
        attention.append(f"Без активности за месяц: {_students_word(act['no_activity'])}.")
    if report["overview"]["students_deactivated"]:
        attention.append(f"Деактивировано за месяц: {_students_word(report['overview']['students_deactivated'])}.")
    for row in sv["rows"]:
        if row["participation"] is not None and row["participation"] < LOW_PARTICIPATION:
            attention.append(f"Участие в опросе «{row['title']}» — {row['participation']}%, ниже {LOW_PARTICIPATION}%.")
    if sv["low_ratings"]:
        attention.append(f"Низких оценок в опросах: {sv['low_ratings']}.")
    if hw["pending"]:
        attention.append(f"Ждут проверки тренера: {hw['pending']} {_plural(hw['pending'], 'работа', 'работы', 'работ')} по ДЗ.")
    # Who exactly: the groups below the group thresholds and the flagged students.
    groups = sorted({g["group"]["name"] for g in att["groups"] if g["percent"] is not None and g["percent"] < LOW_GROUP_ATTENDANCE}
                    | {g["group"]["name"] for g in hw["groups"] if g["percent"] is not None and g["percent"] < LOW_GROUP_HOMEWORK})
    flagged, students = set(), []
    for row in st["risk"] + st["attendance_attention"] + st["homework_attention"]:
        if row["student_id"] not in flagged:
            flagged.add(row["student_id"])
            students.append({"student_id": row["student_id"], "name": row["name"],
                             "group": (row["group"] or {}).get("name", ""), "reason": row["reason"]})
    return {"good": good, "attention": attention, "groups": groups, "students": students}


def previous_month(start: dt.date) -> tuple[dt.date, dt.date]:
    end = start - dt.timedelta(days=1)
    return end.replace(day=1), end


def monthly_report(year: int, month: int, *, filters: dict | None = None, finance_allowed: bool = False) -> dict:
    """The month's report. `filters` (group / teacher / reason) narrow the
    departure sections only; `finance_allowed` — the caller may see finance."""
    start, end = month_bounds(year, month)
    today = timezone.localdate()
    if start > today:
        raise ReportError("Отчёт за будущий месяц ещё нельзя сформировать.")
    filters = {k: v for k, v in (filters or {}).items() if v}
    until = min(end, today)
    state = month_state(start, until, today)
    lessons, counts = state["lessons"], state["roster_counts"]
    trainers = retention.trainers_by_group(state["groups"].keys(), until, start) if state["groups"] else {}
    report = {
        "year": year, "month": month, "title": f"{MONTHS[month - 1]} {year}",
        "start": start, "end": end, "until": until, "is_complete": end < today,
        "generated_at": timezone.now(),
        "overview": _overview(start, end, state),
        "attendance": _attendance(lessons, counts),
        "homework": _homework(lessons, counts),
        "students": _students(state["activity_rows"]),
        "surveys": _surveys(start, end),
        "scholarships": _scholarships(start, end),
        "inactive": retention.inactivity(state["activity_rows"], state["roster"], until, trainers),
        "departures": retention.departures(start, end, filters),
    }
    report["overview"].update({
        "attendance_percent": report["attendance"]["percent"],
        "homework_percent": report["homework"]["percent"],
        "students_at_risk": len(report["students"]["risk"]),
    })
    report["finance"] = retention.finance(finance_allowed, report["overview"]["students_active"],
                                          report["overview"]["students_deactivated"])
    report["conclusions"] = _conclusions(report)

    prev_start, prev_end = previous_month(start)
    current = {
        "attendance": report["attendance"]["percent"], "homework": report["homework"]["percent"],
        "active": report["overview"]["students_active"], "new": report["overview"]["students_new"],
        "departed": report["overview"]["students_deactivated"], "risk": len(report["students"]["risk"]),
        "inactive": report["inactive"]["counts"]["inactive"], "survey": report["surveys"]["average"],
    }
    previous = retention.month_core(prev_start, prev_end, today) if prev_start.year >= 2000 else None
    report["inactive"]["previous"] = previous and {"inactive": previous["inactive"], "risk": previous["risk"]}
    # Month over month compares all departures; a filter only narrows the tables.
    report["departures"]["month_total"] = report["overview"]["students_deactivated"]
    report["departures"]["previous_total"] = previous["departed"] if previous else None
    report["departures"]["change"] = (
        report["overview"]["students_deactivated"] - previous["departed"] if previous else None)
    report["comparison"] = retention.comparison(current, previous, f"{MONTHS[prev_start.month - 1]} {prev_start.year}")
    report["recommendations"] = retention.recommendations(report)
    report["summary"] = retention.management_summary(report)
    return report
