"""Populates the DEVELOPMENT/TESTING database with realistic demo data.

Every object created here is clearly a demo: names are prefixed "[DEMO]",
teacher usernames/emails are under the demo.* namespace, and every command
run prints an explicit "DEVELOPMENT DEMO DATA" banner. Refuses to run in
production, the same way `reset_dev_db` does.

Idempotent: reruns reuse existing rows (matched by unique natural keys —
username, email, course/room/group name) instead of duplicating them. Lesson
generation itself is idempotent by construction (see
services.lesson_generator), so calling this repeatedly is safe.
"""
from __future__ import annotations

import datetime as dt
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academy.models import (
    Course,
    CourseLessonPlan,
    Group,
    GroupSchedule,
    GroupTeacher,
    GroupTeacherLessonPlan,
    Room,
    Student,
)
from apps.academy.services.lesson_generator import LessonGenerationError, generate_lessons_for_group
from apps.users.models import Subject, Teacher, User
from apps.users.services import create_teacher

DEMO_PASSWORD = "DemoPass123!"  # nosec: dev-only fixture password, never used in production (see guard below)


class Command(BaseCommand):
    help = (
        "Creates demo teachers/subjects/courses/groups/students for local "
        "development. Development/testing only — refuses to run when "
        "DJANGO_ENV=production. Idempotent: safe to run more than once."
    )

    def handle(self, *args, **options):
        # Deliberately checked *before* anything touches the database (no
        # @transaction.atomic on this method) — entering a transaction
        # forces Django to open a real connection first, which against a
        # production DATABASES config means dialling out to production
        # before this guard ever gets a chance to refuse. The actual work
        # happens in `_seed`, wrapped in its own atomic block, only once
        # we're certain we're not in production.
        env = os.environ.get("DJANGO_ENV", "development")
        if env == "production":
            raise CommandError(
                "Refusing to run: DJANGO_ENV=production. seed_dev_data never creates "
                "demo data in production, and never opens a production database connection."
            )

        self.stdout.write(self.style.WARNING(
            "=== DEVELOPMENT DEMO DATA (DJANGO_ENV=%s) — not for production use ===" % env
        ))

        self._seed()

    @transaction.atomic
    def _seed(self) -> None:
        admin = self._get_or_create_admin()
        py_subject, robo_subject = self._get_or_create_subjects()
        teacher1 = self._get_or_create_teacher("demo.teacher1", "Айгуль", "Сатыбалдиева", [py_subject])
        teacher2 = self._get_or_create_teacher("demo.teacher2", "Данияр", "Ос­монов", [robo_subject])
        course = self._get_or_create_course(py_subject)
        room = self._get_or_create_room()
        group = self._get_or_create_group(course)
        students = self._get_or_create_students(group)

        self._get_or_create_schedule(group, teacher1, py_subject, room)
        gt2 = self._get_or_create_schedule(group, teacher2, robo_subject, room)
        self._get_or_create_individual_plan(gt2)

        try:
            created_lessons = generate_lessons_for_group(group)
        except LessonGenerationError as exc:
            created_lessons = []
            self.stdout.write(self.style.WARNING(f"Lesson generation: {exc}"))
        self.stdout.write(f"Lesson generation: {len(created_lessons)} lesson(s) created.")

        self.stdout.write(self.style.SUCCESS("Demo data ready:"))
        self.stdout.write(f"  Admin login:    {admin.username} / {DEMO_PASSWORD}")
        self.stdout.write(f"  Teacher logins: {teacher1.user.username} / {DEMO_PASSWORD}")
        self.stdout.write(f"                  {teacher2.user.username} / {DEMO_PASSWORD}")
        self.stdout.write(f"  Group:          {group.name} ({len(students)} students, 2 independent programs)")

    # -- helpers -----------------------------------------------------------

    def _get_or_create_admin(self) -> User:
        user, created = User.objects.get_or_create(
            username="demo_admin",
            defaults={
                "email": "demo.admin@okurmenkids.local",
                "first_name": "Demo",
                "last_name": "Admin",
                "role": User.Role.ADMIN,
                "is_verified": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
            self.stdout.write("Created demo admin user.")
        return user

    def _get_or_create_subjects(self) -> tuple[Subject, Subject]:
        py, _ = Subject.objects.get_or_create(
            name="Python для детей",
            defaults={"description": "[DEMO] Основы программирования на Python."},
        )
        robo, _ = Subject.objects.get_or_create(
            name="Робототехника",
            defaults={"description": "[DEMO] Конструирование и программирование роботов."},
        )
        return py, robo

    def _get_or_create_teacher(self, username: str, first_name: str, last_name: str, subjects: list[Subject]) -> Teacher:
        existing = User.objects.filter(username=username).first()
        if existing is not None:
            return existing.teacher_profile

        result = create_teacher(
            username=username,
            email=f"{username}@okurmenkids.local",
            first_name=first_name,
            last_name=last_name,
            password=DEMO_PASSWORD,
            position="Тренер",
            experience_years=3,
            subjects=subjects,
            send_email=False,
        )
        self.stdout.write(f"Created demo teacher: {username}")
        return result.teacher

    def _get_or_create_course(self, subject: Subject) -> Course:
        course, created = Course.objects.get_or_create(
            name="[DEMO] Python для детей — базовый курс",
            defaults={"count_lesson": 8, "description": "[DEMO] Демонстрационный учебный план."},
        )
        if created:
            course.subjects.add(subject)
            for n in range(1, 9):
                CourseLessonPlan.objects.get_or_create(
                    course=course,
                    lesson_number=n,
                    defaults={
                        "subject": subject,
                        "topic": f"[DEMO] Занятие {n}: тема курса Python",
                        "homework_title": f"[DEMO] Домашнее задание {n}" if n < 8 else "",
                    },
                )
            self.stdout.write("Created demo course + 8 lesson-plan rows.")
        return course

    def _get_or_create_room(self) -> Room:
        room, _ = Room.objects.get_or_create(
            name="[DEMO] Кабинет 101",
            defaults={"capacity": 15, "description": "[DEMO] Демонстрационная аудитория."},
        )
        return room

    def _get_or_create_group(self, course: Course) -> Group:
        group, created = Group.objects.get_or_create(
            name="[DEMO] Группа A1",
            defaults={
                "course": course,
                "start_date": dt.date.today() - dt.timedelta(days=7),
                "max_students": 12,
                "status": Group.Status.ACTIVE,
                "description": "[DEMO] Демонстрационная группа с двумя независимыми программами.",
            },
        )
        if created:
            self.stdout.write("Created demo group.")
        return group

    def _get_or_create_students(self, group: Group) -> list[Student]:
        names = [
            ("Амина", "Жумабекова"),
            ("Бекзат", "Тологонов"),
            ("Сезим", "Асанова"),
            ("Эрлан", "Мамытов"),
            ("Дильноза", "Каримова"),
        ]
        students = []
        for first_name, last_name in names:
            student, _ = Student.objects.get_or_create(
                first_name=first_name,
                last_name=last_name,
                group=group,
                defaults={"is_active": True},
            )
            students.append(student)
        return students

    def _get_or_create_schedule(self, group: Group, teacher: Teacher, subject: Subject, room: Room) -> GroupTeacher:
        day = "mon" if subject.name == "Python для детей" else "wed"
        schedule, _ = GroupSchedule.objects.get_or_create(
            group=group,
            teacher=teacher,
            subject=subject,
            day_of_week=day,
            defaults={
                "start_time": dt.time(10, 0),
                "end_time": dt.time(11, 30),
                "room": room,
            },
        )
        return schedule.group_teacher

    def _get_or_create_individual_plan(self, group_teacher: GroupTeacher) -> None:
        if group_teacher.lesson_plans.exists():
            return
        for n in range(1, 6):
            GroupTeacherLessonPlan.objects.get_or_create(
                group_teacher=group_teacher,
                lesson_number=n,
                defaults={
                    "topic": f"[DEMO] Занятие {n}: тема робототехники",
                    "homework_title": f"[DEMO] Домашнее задание по робототехнике {n}" if n < 5 else "",
                },
            )
        self.stdout.write("Created demo individual lesson plan for the robotics program.")
