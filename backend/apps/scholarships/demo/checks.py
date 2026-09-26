"""Automatic verification of the scholarship system against the demo data.

Every check reads the generated data; checks that need to *write* (re-run
generation, try other dates, switch the award mode, measure a
recalculation) do it inside a transaction that is always rolled back, so
running the checks never changes the database.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

from django.db import connection, transaction
from django.db.models import Count
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academy.models import Attendance
from apps.scholarships.models import (
    AwardMode,
    EligibilityStatus,
    ScholarshipAward,
    ScholarshipConfiguration,
    ScholarshipEvaluation,
    ScholarshipPeriod,
)
from apps.scholarships.services.generation import ScholarshipError, generate_period, recalculate_period, run_schedule
from apps.users.models import User

from . import namespace as ns

TOLERANCE = Decimal("0.02")


@dataclass
class CheckResult:
    number: int
    title: str
    passed: bool
    details: str


class _Rollback(Exception):
    pass


@contextmanager
def count_queries():
    """CaptureQueriesContext with a clean log — the log is a bounded deque,
    and once it is full the context's before/after indices read as 0."""
    connection.queries_log.clear()
    with CaptureQueriesContext(connection) as ctx:
        yield ctx


@contextmanager
def rolled_back():
    try:
        with transaction.atomic():
            yield
            raise _Rollback
    except _Rollback:
        pass


def _mean(values):
    values = list(values)
    return sum(values, Decimal(0)) / len(values) if values else None


class ScholarshipChecks:
    def __init__(self, report):
        self.report = report
        self.periods = list(ScholarshipPeriod.objects.filter(pk__in=[p.pk for p in report.periods]).order_by("period_start"))
        self.latest = self.periods[-1] if self.periods else None
        self.student = {key: student for key, (student, _) in report.scenarios.items()}
        self.results: list[CheckResult] = []
        self.perf: dict = {}

    def ev(self, key, period=None):
        return ScholarshipEvaluation.objects.prefetch_related("subject_scores").get(
            period=period or self.latest, student=self.student[key]
        )

    def run(self) -> list[CheckResult]:
        checks = [
            (1, "Студент с 1 предметом", self.check_one_subject),
            (2, "Студент с 2 предметами (сценарий A)", self.check_two_subjects),
            (3, "Студент с 3+ предметами (сценарии B, C)", self.check_three_plus),
            (4, "Оценивается только предыдущий завершённый месяц", self.check_previous_month),
            (5, "Право на стипендию в первый месяц (G, H)", self.check_first_month),
            (6, "Лимит получателей", self.check_limit),
            (7, "Рейтинг", self.check_ranking),
            (8, "Тай-брейк (T1–T4)", self.check_ties),
            (9, "Нет оценки тренера (F и др.)", self.check_missing_feedback),
            (10, "Нет ДЗ / нет результата ДЗ (D, Soft Skills)", self.check_missing_homework),
            (11, "Посещаемость (пересчёт из Attendance)", self.check_attendance),
            (12, "Защита от дубликатов", self.check_duplicates),
            (13, "Начисление 1-го числа", self.check_first_day),
            (14, "Поведение 15-го числа", self.check_fifteenth),
            (15, "Производительность / число SQL-запросов", self.check_performance),
        ]
        # Several checks provoke *expected* refusals (e.g. an unfinished
        # month); keep them out of the console so they don't read as errors.
        service_logger = logging.getLogger("apps.scholarships")
        previous_level = service_logger.level
        service_logger.setLevel(logging.CRITICAL)
        try:
            for number, title, fn in checks:
                try:
                    passed, details = fn()
                except Exception as exc:  # a crashing check is a failed check, with the reason
                    passed, details = False, f"{type(exc).__name__}: {exc}"
                self.results.append(CheckResult(number, title, passed, details))
        finally:
            service_logger.setLevel(previous_level)
        return self.results

    # ------------------------------------------------------------------ checks

    def _overall_is_subject_mean(self, ev) -> bool:
        counted = [s.subject_score for s in ev.subject_scores.all() if s.aggregation_weight > 0]
        return abs(_mean(counted) - ev.overall_score) <= TOLERANCE

    def check_one_subject(self):
        ev = (
            ScholarshipEvaluation.objects.filter(period=self.latest, subjects_count=1, eligibility_status=EligibilityStatus.ELIGIBLE)
            .prefetch_related("subject_scores").order_by("id").first()
        )
        if ev is None:
            return False, "нет допущенного студента с одним предметом"
        [row] = [s for s in ev.subject_scores.all() if s.aggregation_weight > 0]
        return row.subject_score == ev.overall_score, (
            f"{ev.student_name}: {row.subject_name} {row.subject_score} = итог {ev.overall_score}"
        )

    def check_two_subjects(self):
        ev = self.ev("A")
        rows = {s.subject_name: s for s in ev.subject_scores.all() if s.aggregation_weight > 0}
        ok = set(rows) == {"Python", "CyberSecurity"} and self._overall_is_subject_mean(ev)
        ok = ok and rows["Python"].subject_score > rows["CyberSecurity"].subject_score
        return ok, (
            f"Python {rows['Python'].subject_score}, CyberSecurity {rows['CyberSecurity'].subject_score} → "
            f"итог {ev.overall_score} (среднее обоих), статус {ev.get_eligibility_status_display()}"
        )

    def check_three_plus(self):
        b, c = self.ev("B"), self.ev("C")
        ok = b.subjects_count == 3 and c.subjects_count == 5
        ok = ok and self._overall_is_subject_mean(b) and self._overall_is_subject_mean(c)
        fmt = lambda ev: ", ".join(f"{s.subject_name} {s.subject_score}" for s in ev.subject_scores.all())
        return ok, f"B ({b.subjects_count}): {fmt(b)} → {b.overall_score}; C ({c.subjects_count}): {fmt(c)} → {c.overall_score}"

    def check_previous_month(self):
        problems = []
        for p in self.periods:
            expected_start = (p.evaluation_date - dt.timedelta(days=1)).replace(day=1)
            if p.period_start != expected_start or p.period_end != p.evaluation_date - dt.timedelta(days=1):
                problems.append(str(p))
        today = self.report.data_end + dt.timedelta(days=1)
        next_first = (today.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        refused = False
        with rolled_back():
            try:
                generate_period(next_first, 1, today=today)
            except ScholarshipError:
                refused = True
        windows = "; ".join(f"{p.evaluation_date:%d.%m} → {p.period_start:%d.%m}–{p.period_end:%d.%m}" for p in self.periods)
        return not problems and refused, (
            f"{windows}. Незавершённый месяц ({today:%m.%Y}) с датой {next_first:%d.%m} — "
            f"{'отклонён' if refused else 'НЕ отклонён'}"
        )

    def check_first_month(self):
        first = self.periods[0]
        by_status = dict(first.evaluations.values_list("eligibility_status").annotate(n=Count("id")))
        late_in_first = first.evaluations.filter(enrollment_date__gt=first.period_start)
        late_ok = not late_in_first.exclude(eligibility_status=EligibilityStatus.NOT_FULL_PERIOD).exists()
        g_periods = {
            p.period_start: self.ev("G", p).eligibility_status for p in self.periods
            if ScholarshipEvaluation.objects.filter(period=p, student=self.student["G"]).exists()
        }
        g_enrolled = self.student["G"].enrollment_date
        g_ok = all(
            (status == EligibilityStatus.NOT_FULL_PERIOD) == (start < g_enrolled) for start, status in g_periods.items()
        )
        h = self.student["H"]
        h_ok = (
            not ScholarshipAward.objects.filter(student=h).exists()
            and self.ev("H").eligibility_status == EligibilityStatus.NOT_FULL_PERIOD
        )
        return late_ok and g_ok and h_ok, (
            f"1-й период ({first.period_start:%m.%Y}): допущено {by_status.get('eligible', 0)}, "
            f"поздних зачислений {late_in_first.count()} — все «не весь период»; "
            f"G (с {g_enrolled:%d.%m}): "
            + ", ".join(f"{s:%m.%Y}={st}" for s, st in sorted(g_periods.items()))
            + f"; H (с {h.enrollment_date:%d.%m}): стипендий нет, статус за последний период — «не весь период»"
        )

    def check_limit(self):
        lines, ok = [], True
        for p in self.periods:
            eligible = p.evaluations.filter(eligibility_status=EligibilityStatus.ELIGIBLE).count()
            awards = p.awards.count()
            ok &= awards == min(eligible, p.max_recipients) and awards <= p.max_recipients
            lines.append(f"{p.period_start:%m.%Y}: допущено {eligible}, стипендий {awards}/{p.max_recipients}")
        ok &= any(p.evaluations.filter(eligibility_status=EligibilityStatus.ELIGIBLE).count() > p.max_recipients
                  for p in self.periods)
        return ok, "; ".join(lines)

    def check_ranking(self):
        ok = True
        for p in self.periods:
            ranked = list(p.evaluations.filter(rank__isnull=False).order_by("rank").values_list("rank", "overall_score"))
            ok &= [r for r, _ in ranked] == list(range(1, len(ranked) + 1))
            ok &= all(a[1] >= b[1] for a, b in zip(ranked, ranked[1:]))
            award_ranks = sorted(p.awards.values_list("rank", flat=True))
            ok &= award_ranks == list(range(1, len(award_ranks) + 1))
            ok &= not p.evaluations.filter(rank__isnull=False).exclude(eligibility_status=EligibilityStatus.ELIGIBLE).exists()
        top = self.latest.evaluations.filter(rank__lte=3).order_by("rank")
        return ok, "места 1..N без пропусков, баллы не возрастают, стипендии = первые N мест. Топ-3: " + ", ".join(
            f"#{e.rank} {e.student_name} {e.overall_score}" for e in top
        )

    def check_ties(self):
        evs = [self.ev(k) for k in ("T1", "T2", "T3", "T4")]
        scores = {e.overall_score for e in evs}
        order = [e.student_name for e in sorted(evs, key=lambda e: e.rank)]
        expected = [self.ev("T4").student_name] + [self.ev(k).student_name for k in ("T1", "T2", "T3")]
        ok = len(scores) == 1 and order == expected
        return ok, (
            f"у всех {scores.pop() if len(scores) == 1 else scores}; порядок: "
            + " → ".join(f"{e.student_name} #{e.rank}" for e in sorted(evs, key=lambda e: e.rank))
            + " (раньше зачислен → выше, затем меньший id)"
        )

    def check_missing_feedback(self):
        f_statuses = {p.period_start: self.ev("F", p).eligibility_status for p in self.periods}
        f_ok = all(s == EligibilityStatus.INCOMPLETE_DATA for s in f_statuses.values())
        incomplete = self.latest.evaluations.filter(eligibility_status=EligibilityStatus.INCOMPLETE_DATA).count()
        bad = ScholarshipEvaluation.objects.filter(
            period__in=self.periods, eligibility_status=EligibilityStatus.ELIGIBLE,
            subject_scores__aggregation_weight__gt=0, subject_scores__subject__isnull=False,
            subject_scores__feedback_received=0,
        ).count()
        perfect_without = ScholarshipEvaluation.objects.filter(
            period__in=self.periods, subject_scores__feedback_received=0, subject_scores__feedback_score=100,
        ).count()
        return f_ok and bad == 0 and perfect_without == 0, (
            f"F: «Неполные данные» во всех периодах ({self.ev('F').ineligibility_reason}); "
            f"в последнем периоде неполных данных: {incomplete}; допущенных без оценки: {bad}; "
            f"«100 без оценки»: {perfect_without}"
        )

    def check_missing_homework(self):
        d = self.ev("D")
        e = self.ev("E")
        soft = self.latest.evaluations.filter(subject_scores__subject_name="Soft Skills").first()
        soft_row = soft.subject_scores.get(subject_name="Soft Skills") if soft else None
        # Filtered in Python: SQLite stores the JSON list with Cyrillic
        # \u-escaped, so a database-side icontains can't match it there.
        no_result = sum(
            any("без результата" in w for w in warnings)
            for warnings in self.latest.evaluations.values_list("data_warnings", flat=True)
        )
        ok = d.homework_score < Decimal(50) < d.attendance_score and e.attendance_score < Decimal(60) < e.homework_score
        ok = ok and soft_row is not None and soft_row.homework_score is None and no_result > 0
        return ok, (
            f"D: посещ. {d.attendance_score}, ДЗ {d.homework_score}, итог {d.overall_score}; "
            f"E: посещ. {e.attendance_score}, ДЗ {e.homework_score}, итог {e.overall_score}; "
            f"Soft Skills без ДЗ → компонента ДЗ пустая, балл {soft_row.subject_score if soft_row else '—'}; "
            f"оценок с «ДЗ без результата»: {no_result}"
        )

    def check_attendance(self):
        p = self.latest
        sample = list(
            ScholarshipEvaluation.objects.filter(period=p, lessons_count__gt=0).prefetch_related("subject_scores").order_by("id")[:40]
        )
        mismatches = 0
        for ev in sample:
            rows = Attendance.objects.filter(
                student_id=ev.student_id, lesson__date__gte=p.period_start, lesson__date__lte=p.period_end,
            ).exclude(lesson__status="cancelled").values_list("lesson__subject__name", "status")
            per = {}
            for subject, status in rows:
                att, total = per.get(subject, (0, 0))
                if status == "excused":
                    continue
                per[subject] = (att + (status in ("present", "late")), total + 1)
            for s in ev.subject_scores.all():
                if s.subject_name in per and per[s.subject_name][1]:
                    expected = Decimal(per[s.subject_name][0]) / per[s.subject_name][1] * 100
                    if abs(expected - s.attendance_score) > TOLERANCE:
                        mismatches += 1
        return mismatches == 0, f"проверено {len(sample)} студентов независимым пересчётом, расхождений: {mismatches}"

    def check_duplicates(self):
        before = (ScholarshipPeriod.objects.count(), ScholarshipEvaluation.objects.count(), ScholarshipAward.objects.count())
        created = []
        with rolled_back():
            for p in self.periods:
                created.append(generate_period(p.evaluation_date, 1, today=self.report.data_end + dt.timedelta(days=1)).created)
            created += [r.created for r in run_schedule(today=self.report.data_end + dt.timedelta(days=1))]
            after = (ScholarshipPeriod.objects.count(), ScholarshipEvaluation.objects.count(), ScholarshipAward.objects.count())
        dup_evals = ScholarshipEvaluation.objects.values("period", "student").annotate(n=Count("id")).filter(n__gt=1).count()
        dup_awards = ScholarshipAward.objects.values("period", "student").annotate(n=Count("id")).filter(n__gt=1).count()
        ok = not any(created) and before == after and dup_evals == 0 and dup_awards == 0
        return ok, (
            f"повторная генерация {len(created)} раз: новых периодов {sum(created)}; "
            f"периоды/оценки/стипендии до {before}, после {after}; дубликатов оценок {dup_evals}, стипендий {dup_awards}"
        )

    def check_first_day(self):
        p = self.latest
        with rolled_back():
            ScholarshipPeriod.objects.filter(pk=p.pk).delete()
            [result] = run_schedule(today=p.evaluation_date)
            window = (result.period.period_start, result.period.period_end)
            ok = result.created and window == (p.period_start, p.period_end)
            detail = (
                f"запуск {p.evaluation_date:%d.%m}: создан период {window[0]:%d.%m}–{window[1]:%d.%m}, "
                f"оценено {result.period.evaluations.count()}, стипендий {result.period.awards.count()}"
            )
        return ok, detail

    def check_fifteenth(self):
        fifteenth = self.latest.evaluation_date.replace(day=15)
        with rolled_back():
            monthly = run_schedule(today=fifteenth)
            monthly_new = sum(r.created for r in monthly)
            config = ScholarshipConfiguration.objects.active()
            config.award_mode = AwardMode.TWICE_MONTHLY
            config.save()
            twice = run_schedule(today=fifteenth)
            new = [r.period for r in twice if r.created]
            detail_twice = ", ".join(
                f"{p.period_start:%d.%m}–{p.period_end:%d.%m}: стипендий {p.awards.count()}/{p.max_recipients}" for p in new
            )
            ok = monthly_new == 0 and len(new) == 1 and new[0].award_day == 15 and new[0].awards.count() <= new[0].max_recipients
        return ok, (
            f"режим «раз в месяц», {fifteenth:%d.%m}: новых периодов {monthly_new}; "
            f"режим «два цикла»: создан независимый цикл 15-го ({detail_twice})"
        )

    def check_performance(self):
        p = self.latest
        admin = User.objects.get(ns.demo_user_q(), username=ns.ADMIN_USERNAME)
        with rolled_back():
            started = time.perf_counter()
            with count_queries() as ctx:
                recalculate_period(p)
            recalc_seconds = time.perf_counter() - started
            recalc_queries = len(ctx.captured_queries)
        evaluated = p.evaluations.count()

        api = APIClient()
        api.force_authenticate(admin)
        with count_queries() as ctx:
            started = time.perf_counter()
            response = api.get(reverse("scholarship-period-ranking", args=[p.pk]))
            api_seconds = time.perf_counter() - started
        api_queries = len(ctx.captured_queries)

        web = Client()
        web.force_login(admin)
        with count_queries() as ctx:
            started = time.perf_counter()
            page = web.get(reverse("admin:scholarships_scholarshipperiod_change", args=[p.pk]))
            admin_seconds = time.perf_counter() - started
        admin_queries = len(ctx.captured_queries)
        with count_queries() as ctx:
            web.get(reverse("admin:scholarships_scholarshipevaluation_changelist") + f"?period__id__exact={p.pk}")
        list_queries = len(ctx.captured_queries)

        self.perf = {
            "evaluated": evaluated, "recalc_seconds": recalc_seconds, "recalc_queries": recalc_queries,
            "api_seconds": api_seconds, "api_queries": api_queries, "admin_seconds": admin_seconds,
            "admin_queries": admin_queries, "admin_list_queries": list_queries,
        }
        # Constant-per-period budgets: a per-student query pattern (N+1) would
        # blow straight through these with hundreds of students.
        ok = response.status_code == 200 and page.status_code == 200
        ok = ok and recalc_queries < 60 and api_queries < 15 and admin_queries < 40 and list_queries < 25
        return ok, (
            f"пересчёт {evaluated} студентов: {recalc_seconds:.2f}s, {recalc_queries} SQL; "
            f"API ranking: {api_seconds * 1000:.0f}ms, {api_queries} SQL; "
            f"админ-дашборд периода (все {evaluated} строк): {admin_seconds * 1000:.0f}ms, {admin_queries} SQL; "
            f"список оценок в админке: {list_queries} SQL"
        )
