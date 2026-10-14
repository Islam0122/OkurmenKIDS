"""Demo data for testing the public leaderboard (/leaderboard).

Creates «[DEMO-LB]» courses and groups with students, completed lessons,
attendance, homework results and finished test attempts from 1 January of
the previous year up to today — so every period (year / month / week), the
previous-period comparison (▲ ▼ NEW) and the group ranking have something to
show. One student is marked «скрыт из рейтинга» to check the privacy row.

Everything goes through the real models; the leaderboard computes XP from
these rows exactly as it would from real ones. Deterministic (fixed RNG
seed). Development/testing only — refuses to run with DJANGO_ENV=production.

    python manage.py seed_leaderboard_demo           # create (re-creates if present)
    python manage.py seed_leaderboard_demo --clear   # remove the demo data only
"""
from __future__ import annotations

import datetime as dt
import os
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academy.models import Attendance, Course, Group, Homework, HomeworkResult, Lesson, Student
from apps.leaderboard.services import bump_cache_version
from apps.testing.models import AttemptStatus, SessionType, StudentAttempt, Test, TestSession

MARK = "[DEMO-LB]"
RNG_SEED = 2026
COURSES = {f"{MARK} Программирование": 0, f"{MARK} Робототехника": 1, f"{MARK} Дизайн": 2}
GROUPS = [
    (f"{MARK} Prog SOFT-1", f"{MARK} Программирование", 8),
    (f"{MARK} Prog SOFT-2", f"{MARK} Программирование", 6),
    (f"{MARK} Robo Kids-1", f"{MARK} Робототехника", 5),
    (f"{MARK} Robo Kids-2", f"{MARK} Робототехника", 7),
    (f"{MARK} Design Junior", f"{MARK} Дизайн", 9),
    (f"{MARK} Python Start", f"{MARK} Программирование", 4),
]
FIRST = ["Алия", "Бакыт", "Чынара", "Данияр", "Эрмек", "Айпери", "Нурсултан", "Мээрим", "Тимур", "Айбек", "Жибек",
         "Санжар", "Камила", "Арген", "Элина", "Адилет", "Бегимай", "Нурлан", "Асель", "Улан", "Дастан", "Сезим",
         "Эльдар", "Айдана", "Руслан", "Медина", "Азамат", "Каныкей", "Ислам", "Нурай"]
LAST = ["Садыкова", "Асанов", "Омурова", "Беков", "Токтогулов", "Жумабаева", "Исаков", "Кадырова", "Мамытов",
        "Усенов", "Осмонов", "Турсунова", "Шаршеев", "Алиева", "Бакиров", "Эсенова", "Сыдыков", "Касымова"]
LESSON_DAYS = (0, 2, 4)  # Mon / Wed / Fri


def clear_demo() -> dict:
    groups = Group.objects.filter(name__startswith=MARK)
    students = Student.objects.filter(group__in=groups)
    tests = Test.objects.filter(title__startswith=MARK)
    courses = Course.objects.filter(name__startswith=MARK)
    counts = {"groups": groups.count(), "students": students.count(), "tests": tests.count(), "courses": courses.count()}
    StudentAttempt.objects.filter(student__in=students).delete()
    tests.delete()  # cascades its sessions
    students.delete()
    groups.delete()  # cascades lessons, attendance, homework
    courses.delete()
    bump_cache_version()
    return counts


class Command(BaseCommand):
    help = "Demo data for the public leaderboard (dev/testing only). --clear removes it."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Only remove the «[DEMO-LB]» data.")

    def handle(self, *args, **options):
        if os.environ.get("DJANGO_ENV", "development") == "production":
            raise CommandError("Refusing to run: DJANGO_ENV=production. Demo data is never created in production.")
        with transaction.atomic():
            removed = clear_demo()
            if options["clear"]:
                self.stdout.write(self.style.SUCCESS(f"Removed leaderboard demo data: {removed}"))
                return
            summary = self._seed(random.Random(RNG_SEED), timezone.localdate())
        bump_cache_version()
        self.stdout.write(self.style.SUCCESS(
            "Leaderboard demo data: {students} students, {groups} groups, {lessons} lessons, "
            "{attendance} attendance marks, {homework} homework results, {attempts} test attempts "
            "({start} … {end}).".format(**summary)
        ))
        self.stdout.write("Open /leaderboard (frontend) or GET /api/v1/public/leaderboard/students/ to check.")

    def _seed(self, rng: random.Random, today: dt.date) -> dict:
        courses = {name: Course.objects.create(name=name, count_lesson=48, description=f"{MARK} демо-курс")
                   for name in COURSES}
        start = dt.date(today.year - 1, 1, 1)
        groups, students, skill = [], [], {}
        for name, course, size in GROUPS:
            group = Group.objects.create(name=name, course=courses[course], start_date=start, description=f"{MARK} демо-группа")
            groups.append(group)
            for _ in range(size):
                student = Student.objects.create(
                    first_name=rng.choice(FIRST), last_name=rng.choice(LAST), group=group, enrollment_date=start,
                )
                students.append(student)
                skill[student.pk] = rng.uniform(0.45, 0.97)
        # Privacy check: one student is listed anonymously.
        Student.objects.filter(pk=students[3].pk).update(show_in_leaderboard=False)
        # A student who joins late shows up as «NEW» in the current period.
        latecomer = students[-1]
        joined = today - dt.timedelta(days=today.weekday())

        test = Test.objects.create(title=f"{MARK} Проверочный тест")
        counts = {"lessons": 0, "attendance": 0, "homework": 0, "attempts": 0}
        numbers = {group.pk: 0 for group in groups}
        members = {group.pk: [s for s in students if s.group_id == group.pk] for group in groups}
        day = start
        while day <= today:
            if day.weekday() in LESSON_DAYS:
                for group in groups:
                    numbers[group.pk] += 1
                    lesson = Lesson.objects.create(
                        group=group, lesson_number=numbers[group.pk], date=day, start_time=dt.time(14),
                        end_time=dt.time(15, 30), status=Lesson.Status.COMPLETED, topic=f"{MARK} Занятие {numbers[group.pk]}",
                    )
                    counts["lessons"] += 1
                    homework = Homework.objects.create(lesson=lesson, title=f"{MARK} ДЗ") if day.weekday() == 0 else None
                    session = None
                    if day.weekday() == 4 and day.day <= 7:
                        session = TestSession.objects.create(test=test, group=group, session_type=SessionType.TRAINING)
                    for student in members[group.pk]:
                        if student.pk == latecomer.pk and day < joined:
                            continue
                        p = skill[student.pk]
                        roll = rng.random()
                        status = (Attendance.Status.PRESENT if roll < p
                                  else Attendance.Status.LATE if roll < p + 0.07 else Attendance.Status.ABSENT)
                        Attendance.objects.create(student=student, lesson=lesson, status=status)
                        counts["attendance"] += 1
                        if homework and status != Attendance.Status.ABSENT:
                            hw_status = (HomeworkResult.Status.CHECKED if rng.random() < p
                                         else HomeworkResult.Status.LATE if rng.random() < 0.5
                                         else HomeworkResult.Status.NOT_SUBMITTED)
                            HomeworkResult.objects.create(
                                homework=homework, student=student, status=hw_status,
                                score=rng.randint(5, 10) if hw_status == HomeworkResult.Status.CHECKED else None,
                            )
                            counts["homework"] += 1
                        if session and status != Attendance.Status.ABSENT:
                            StudentAttempt.objects.create(
                                session=session, student=student, student_name=str(student),
                                status=AttemptStatus.FINISHED,
                                score=round(max(0.0, min(100.0, rng.gauss(p * 100, 10))), 1),
                                finished_at=timezone.make_aware(dt.datetime.combine(day, dt.time(16))),
                            )
                            counts["attempts"] += 1
            day += dt.timedelta(days=1)
        return {**counts, "students": len(students), "groups": len(groups), "start": start, "end": today}
