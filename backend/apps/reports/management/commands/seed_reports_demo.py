"""Demo data for the parent reports demo video (scripts/demo_reports.py).

    python manage.py seed_reports_demo                # password from $REPORTS_DEMO_PASSWORD or generated
    python manage.py seed_reports_demo --password …   # explicit password

Creates one demo trainer (`demo_trainer`), one group «PY-KIDS-07» with 12
fictional students, lessons, attendance, homework and test results for the
current month and the two months before it — so «Прошлый месяц» has a full
month of data and a previous month to compare with.

Every name is fictional; no phone numbers or other personal data. Running it
again replaces the previous demo data (only rows it created itself). Refuses
to run with production settings.
"""
from __future__ import annotations

import datetime as dt
import os
import random
import secrets

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academy.models import Attendance, Course, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Student
from apps.reports.models import ParentReport
from apps.testing.models import AttemptStatus, StudentAttempt, Test, TestSession
from apps.users.models import Subject, Teacher, User

DEMO_USERNAME = "demo_trainer"
DEMO_GROUP = "PY-KIDS-07"
DEMO_MARKER = "[demo:parent-reports]"
DEMO_COURSE = "Python для детей"
DEMO_TEST = "Python: переменные и циклы"

# (first name, last name, skill 0..1, attendance bias) — fictional demo students.
STUDENTS = [
    ("Айдана", "Демонова", 0.97, 0.03),
    ("Бекзат", "Учебный", 0.90, 0.02),
    ("Нурислам", "Примеров уулу", 0.55, -0.20),
    ("Элиза", "Тестова", 0.62, -0.05),
    ("Тимур", "Образцов", 0.82, 0.05),
    ("Алтынай", "Пробная", 0.93, 0.04),
    ("Эрлан", "Демо", 0.74, 0.00),
    ("Самира", "Учебная", 0.86, 0.03),
    ("Адилет", "Примеров", 0.45, -0.25),
    ("Мээрим", "Образцова", 0.78, -0.02),
    ("Данияр", "Тестов", 0.88, 0.05),
    ("Аружан", "Демонова-Примерова", 0.68, -0.10),
]
LESSON_DAYS = (0, 2, 4)  # Mon, Wed, Fri


def _month_start(day: dt.date, back: int) -> dt.date:
    year, month = day.year, day.month - back
    while month <= 0:
        month += 12
        year -= 1
    return dt.date(year, month, 1)


class Command(BaseCommand):
    help = "Демо-данные для видео «Отчёты для родителей» (вымышленные студенты)."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Пароль demo_trainer (по умолчанию $REPORTS_DEMO_PASSWORD или случайный).")
        parser.add_argument("--seed", type=int, default=7, help="Зерно генератора — одинаковые данные при повторе.")

    def handle(self, *args, **options):
        if "production" in (settings.SETTINGS_MODULE or "") or os.environ.get("DJANGO_ENV") == "production":
            raise CommandError("Демо-данные не создаются в production.")
        password = options["password"] or os.environ.get("REPORTS_DEMO_PASSWORD")
        generated = password is None
        password = password or secrets.token_urlsafe(12)
        rng = random.Random(options["seed"])
        today = timezone.localdate()

        with transaction.atomic():
            self._clear()
            trainer = self._trainer(password)
            group, program, python = self._group(trainer)
            students = [
                Student.objects.create(first_name=first, last_name=last, group=group, enrollment_date=_month_start(today, 3))
                for first, last, _, _ in STUDENTS
            ]
            lessons = self._lessons(group, program, trainer, python, today)
            self._records(lessons, students, rng, today)
            self._tests(group, trainer, python, students, rng, today)

        held = sum(1 for lesson in lessons if lesson.status == Lesson.Status.COMPLETED)
        self.stdout.write(self.style.SUCCESS(
            f"Демо-группа «{DEMO_GROUP}» (id={group.pk}): {len(students)} студентов, {held} проведённых занятий."
        ))
        self.stdout.write(f"Вход: {DEMO_USERNAME}" + (f" / пароль: {password}" if generated else " (пароль из параметров)"))

    # ------------------------------------------------------------------
    def _clear(self):
        groups = Group.objects.filter(name=DEMO_GROUP, description=DEMO_MARKER)
        ParentReport.objects.filter(group__in=groups).delete()
        StudentAttempt.objects.filter(group__in=groups).delete()
        TestSession.objects.filter(group__in=groups).delete()
        Student.objects.filter(group__in=groups).delete()
        groups.delete()  # lessons, attendance, homework cascade
        Course.objects.filter(name=DEMO_COURSE, description=DEMO_MARKER).delete()

    def _trainer(self, password: str) -> Teacher:
        user, _ = User.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={"email": "demo_trainer@example.com", "role": User.Role.TEACHER},
        )
        user.first_name, user.last_name = "Демо", "Тренер"
        user.role = User.Role.TEACHER
        user.is_verified = True
        user.is_active = True
        user.set_password(password)
        user.save()
        teacher, _ = Teacher.objects.get_or_create(user=user)
        return teacher

    def _group(self, trainer: Teacher):
        python, _ = Subject.objects.get_or_create(name="Python")
        course = Course.objects.create(name=DEMO_COURSE, count_lesson=48, description=DEMO_MARKER)
        course.subjects.set([python])
        group = Group.objects.create(
            name=DEMO_GROUP, course=course, teacher=trainer, start_date=_month_start(timezone.localdate(), 3),
            description=DEMO_MARKER, max_students=14,
        )
        program = GroupTeacher.objects.create(group=group, teacher=trainer, subject=python)
        return group, program, python

    def _lessons(self, group, program, trainer, python, today) -> list[Lesson]:
        lessons = []
        day = _month_start(today, 2)
        last_month = _month_start(today, 1)
        cancelled_once = False
        number = 0
        while day <= today + dt.timedelta(days=10):
            if day.weekday() in LESSON_DAYS:
                number += 1
                status = Lesson.Status.COMPLETED if day < today else Lesson.Status.SCHEDULED
                if not cancelled_once and day >= last_month + dt.timedelta(days=14) and status == Lesson.Status.COMPLETED:
                    status, cancelled_once = Lesson.Status.CANCELLED, True
                lessons.append(Lesson.objects.create(
                    group=group, group_teacher=program, teacher=trainer, subject=python, lesson_number=number,
                    date=day, start_time=dt.time(15), end_time=dt.time(16, 30), status=status,
                    topic=f"Урок {number}: Python",
                ))
            day += dt.timedelta(days=1)
        return lessons

    def _records(self, lessons, students, rng: random.Random, today):
        profile = {student.pk: STUDENTS[index] for index, student in enumerate(students)}
        previous_month = _month_start(today, 2)
        for lesson in lessons:
            if lesson.status != Lesson.Status.COMPLETED:
                continue
            homework = Homework.objects.create(lesson=lesson, title=f"ДЗ к уроку {lesson.lesson_number}")
            # The month before last is a bit weaker — the report shows progress.
            earlier = lesson.date < _month_start(today, 1) and lesson.date >= previous_month
            for student in students:
                _, _, skill, bias = profile[student.pk]
                skill_now = max(0.2, skill - (0.08 if earlier else 0))
                attended = rng.random() < min(0.99, skill_now + 0.12 + bias)
                status = "present" if attended else rng.choice(["absent", "absent", "excused"])
                if attended and rng.random() < 0.06:
                    status = "late"
                Attendance.objects.create(lesson=lesson, student=student, status=status)
                done = rng.random() < skill_now
                score = max(1, min(10, round(skill_now * 10 + rng.uniform(-1.4, 1.0)))) if done else None
                HomeworkResult.objects.create(
                    homework=homework, student=student, status="checked" if done else "not_submitted", score=score,
                )

    def _tests(self, group, trainer, python, students, rng: random.Random, today):
        test, _ = Test.objects.get_or_create(title=DEMO_TEST, defaults={"passing_score": 60})
        session = TestSession.objects.create(test=test, group=group, teacher=trainer)
        for back, day in ((1, 24), (2, 22)):
            when = _month_start(today, back).replace(day=day)
            for index, student in enumerate(students):
                if index in (6, 9):  # two students skipped the test — «Нет данных»
                    continue
                skill = STUDENTS[index][2] - (0.08 if back == 2 else 0)
                attempt = StudentAttempt.objects.create(
                    session=session, student=student, group=group, teacher=trainer, subject=python,
                    student_name=str(student), test_title=test.title,
                )
                StudentAttempt.objects.filter(pk=attempt.pk).update(
                    status=AttemptStatus.FINISHED,
                    score=round(max(5.0, min(100.0, skill * 100 + rng.uniform(-12, 4))), 1),
                    finished_at=timezone.make_aware(dt.datetime.combine(when, dt.time(16))),
                )
