"""Large, deterministic DEMO dataset for testing the scholarship system.

    python manage.py seed_scholarship_demo                    # 400 students
    python manage.py seed_scholarship_demo --students 1000 --seed 7
    python manage.py seed_scholarship_demo --reset            # clear demo data, then seed
    python manage.py seed_scholarship_demo --clear            # delete ONLY demo data
    python manage.py seed_scholarship_demo --no-checks        # skip the automatic checks

Development/test databases only: refuses to run when DJANGO_ENV=production.
Every row it creates is tagged (see apps/scholarships/demo/namespace.py),
and --clear deletes only tagged rows. Scholarship periods evaluate *every*
student in the database, so they are only generated when the database has
no non-demo students (otherwise the LMS data is still created and the
reason is printed).
"""
from __future__ import annotations

import datetime as dt
import os
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone

from apps.academy.models import Attendance, Course, Group, Homework, HomeworkResult, Lesson, Student
from apps.scholarships.demo import namespace as ns
from apps.scholarships.demo.builder import DemoBuilder, clear_demo_data, demo_data_exists
from apps.scholarships.demo.checks import ScholarshipChecks
from apps.scholarships.models import EligibilityStatus, ScholarshipAward, ScholarshipEvaluation, TrainerFeedback
from apps.users.models import Teacher

LINE = "=" * 44


class Command(BaseCommand):
    help = "Создать (или удалить через --clear) демо-данные для проверки стипендиальной системы."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=400, help="Количество студентов (по умолчанию 400).")
        parser.add_argument("--seed", type=int, default=42, help="Seed генератора (по умолчанию 42).")
        parser.add_argument(
            "--today", type=dt.date.fromisoformat, default=None,
            help="Опорная дата YYYY-MM-DD (по умолчанию сегодня). Та же дата + тот же seed = те же данные.",
        )
        parser.add_argument("--clear", action="store_true", help="Удалить только демо-данные и выйти.")
        parser.add_argument("--reset", action="store_true", help="Удалить демо-данные и создать заново.")
        parser.add_argument("--no-checks", action="store_true", help="Не запускать автоматические проверки.")

    def handle(self, *args, **options):
        if os.environ.get("DJANGO_ENV", "development") == "production":
            raise CommandError("DJANGO_ENV=production — демо-данные в production не создаются и не удаляются.")

        if options["clear"] or options["reset"]:
            try:
                counts = clear_demo_data()
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write("Удалено (только демо-данные):")
            for label, count in counts.items():
                self.stdout.write(f"  {label:<26}{count:>8}")
            if options["clear"]:
                return

        if demo_data_exists():
            raise CommandError("Демо-данные уже есть. Используйте --reset (пересоздать) или --clear.")
        if options["students"] < 20:
            raise CommandError("--students должно быть не меньше 20 (нужны группы для всех сценариев).")

        today = options["today"] or timezone.localdate()
        self.stdout.write(f"Генерация: {options['students']} студентов, seed={options['seed']}, дата={today}")
        builder = DemoBuilder(students=options["students"], seed=options["seed"], today=today, stdout=self.stdout)
        report = builder.build()

        self._summary(report)
        if report.periods and not options["no_checks"]:
            self._checks(report)
        for reason in report.skipped_periods:
            self.stdout.write(self.style.WARNING(f"Периоды: {reason}"))

    # ------------------------------------------------------------------------

    def _summary(self, report):
        groups = Group.objects.filter(ns.demo_group_q())
        lessons = Lesson.objects.filter(group__in=groups)
        periods = report.periods
        latest = periods[-1] if periods else None
        evaluations = ScholarshipEvaluation.objects.filter(period__in=periods)
        rows = [
            ("Students", Student.objects.filter(ns.demo_student_q()).count()),
            ("Programs", Course.objects.filter(ns.demo_group_q()).count()),
            ("Subjects", lessons.values("subject").distinct().count()),
            ("Groups", groups.count()),
            ("Teachers", Teacher.objects.filter(user__username__startswith=ns.USERNAME_PREFIX).count()),
            None,
            ("Lessons", lessons.count()),
            ("Attendance", Attendance.objects.filter(lesson__in=lessons).count()),
            ("Homework", Homework.objects.filter(lesson__in=lessons).count()),
            ("Homework Results", HomeworkResult.objects.filter(homework__lesson__in=lessons).count()),
            ("Trainer Feedback", TrainerFeedback.objects.filter(period__in=periods).count()),
            None,
            ("Scholarship Periods", len(periods)),
            ("Evaluations", evaluations.count()),
            ("Awards", ScholarshipAward.objects.filter(period__in=periods).count()),
        ]
        if latest:
            rows += [
                None,
                ("Latest period", f"{latest.period_start:%d.%m}–{latest.period_end:%d.%m.%Y}"),
                ("Eligible students", latest.evaluations.filter(eligibility_status=EligibilityStatus.ELIGIBLE).count()),
                ("Scholarship limit", latest.max_recipients),
                ("Recipients", latest.awards.count()),
            ]
        w = self.stdout.write
        w("")
        w(LINE)
        w("SCHOLARSHIP DEMO DATA")
        w(LINE)
        w(f"Data: {report.data_start:%d.%m.%Y} – {report.data_end:%d.%m.%Y}")
        for row in rows:
            w("" if row is None else f"{row[0] + ':':<22}{row[1]:>18}")
        w("")
        subjects_per_student = Counter(
            n for n in Counter(
                student_id for student_id, _ in Attendance.objects.filter(student__phone__startswith=ns.PHONE_PREFIX)
                .order_by().values_list("student_id", "lesson__subject_id").distinct()
            ).values()
        )
        w("Students by number of subjects: " + ", ".join(f"{n} → {c}" for n, c in sorted(subjects_per_student.items())))
        for p in periods:
            by_status = dict(p.evaluations.values_list("eligibility_status").annotate(c=Count("id")))
            w(
                f"  {p.evaluation_date:%d.%m} → {p.period_start:%m.%Y} [{p.get_status_display()}]: "
                f"оценено {sum(by_status.values())}, допущено {by_status.get('eligible', 0)}, "
                f"неполные {by_status.get('incomplete_data', 0)}, не весь период {by_status.get('not_full_period', 0)}, "
                f"неактивны {by_status.get('inactive', 0)}, стипендий {p.awards.count()}"
            )
        w("Scenario students:")
        for key, (student, text) in sorted(report.scenarios.items()):
            w(f"  {key:<3} id={student.id:<6} {student.first_name} {student.last_name} — {text}")
        w(LINE)

    def _checks(self, report):
        checks = ScholarshipChecks(report)
        results = checks.run()
        w = self.stdout.write
        w("")
        w("SCHOLARSHIP CHECKS")
        w(LINE)
        for r in results:
            mark = self.style.SUCCESS("PASS") if r.passed else self.style.ERROR("FAIL")
            w(f"{r.number:>2}. [{mark}] {r.title}")
            w(f"      {r.details}")
        passed = sum(r.passed for r in results)
        w(LINE)
        w(f"{passed}/{len(results)} checks passed")
        if passed != len(results):
            raise CommandError("Some scholarship checks failed — see above.")
