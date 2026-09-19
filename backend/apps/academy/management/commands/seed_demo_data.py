"""Populates the database with a realistic, fully-connected DEMO dataset for
developing and testing the Monthly Teacher Reports feature (and everything
it depends on: Groups, Students, Lessons, Attendance, Homework).

Every model used here is a real, existing project model — nothing new is
introduced:

    User, Teacher, Subject, Course, Room, Group, GroupSchedule,
    GroupTeacher (derived automatically by GroupSchedule.save()), Student,
    Lesson, Attendance, Homework, HomeworkResult, MonthlyTeacherReport.

There is no separate "KPI"/"test result" model in this project (KPI and
weekly attendance dynamics are computed on demand by
``apps.academy.services.monthly_report.compute_monthly_stats`` straight from
Lesson/Attendance/Homework/HomeworkResult — see that module), so this
command never writes a kpi/attendance_percent/lessons_count-style field onto
MonthlyTeacherReport. A seeded report has exactly the fields the model
actually has: teacher, year, month, comment. Every number the Reports UI
shows for it is derived live, the same way it would be for a real teacher.

Idempotent — matches existing rows by their natural unique key (username,
email, Subject/Course/Room/Group name, GroupTeacher lesson_number, the
Attendance/HomeworkResult unique-together constraints, the
MonthlyTeacherReport unique-together constraint) and never edits or
duplicates something that's already there. Running it three times in a row
produces the same dataset as running it once.

Random-looking figures (attendance status, homework grading, scores) are
drawn from a fixed-seed RNG consumed in a fixed iteration order, so the
*first* run of this command always produces the same numbers — but nothing
is hand-set to "kpi = 94"; every percentage is a natural side effect of the
generated Attendance/HomeworkResult rows, exactly as spec'd.
"""
from __future__ import annotations

import datetime as dt
import os
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academy.constants import WEEKDAY_CODES
from apps.academy.models import (
    Attendance,
    Course,
    Group,
    GroupSchedule,
    GroupTeacher,
    Homework,
    HomeworkResult,
    Lesson,
    MonthlyTeacherReport,
    Room,
    Student,
)
from apps.users.models import Subject, Teacher, User
from apps.users.services import create_teacher

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin12345"
ADMIN_EMAIL = "admin@okurmenkids.local"

TEACHER_PASSWORD = "teacher123"

# One fixed seed → the same "random" attendance/grades every fresh run.
# Re-running only ever *adds* what's missing (get_or_create/bulk_create
# ignore_conflicts), so this seed only matters for a brand-new database.
RNG_SEED = 2026

# ---------------------------------------------------------------------------
# Demo dataset definition — the single source of truth both this command and
# clear_demo_data.py key off of.
# ---------------------------------------------------------------------------

DEMO_TEACHERS = [
    {
        "username": "islam_it",
        "email": "islam_it@okurmenkids.local",
        "first_name": "Islam",
        "last_name": "Duishobaev",
        "position": "Тренер по IT",
        "experience_years": 5,
        "hire_date": dt.date(2022, 3, 1),
        "bio": "[DEMO] Ведёт направления IT и Backend, фокус на практических проектах.",
        "subjects": ["IT", "Backend"],
        # attendance / homework / score weights this teacher's demo data is generated with
        "attendance_weights": {"present": 88, "late": 7, "absent": 4, "excused": 1},
        "homework_weights": {"checked": 80, "submitted": 8, "late": 4, "not_submitted": 8},
        "score_weights": {7: 10, 8: 30, 9: 40, 10: 20},
    },
    {
        "username": "khadizha_soft",
        "email": "khadizha_soft@okurmenkids.local",
        "first_name": "Khadizha",
        "last_name": "",
        "position": "Тренер по Soft Skills",
        "experience_years": 4,
        "hire_date": dt.date(2023, 6, 15),
        "bio": "[DEMO] Развивает коммуникативные навыки и командную работу студентов.",
        "subjects": ["Soft Skills"],
        "attendance_weights": {"present": 85, "late": 8, "absent": 5, "excused": 2},
        "homework_weights": {"checked": 75, "submitted": 9, "late": 6, "not_submitted": 10},
        "score_weights": {6: 10, 7: 25, 8: 35, 9: 20, 10: 10},
    },
    {
        "username": "azamat_python",
        "email": "azamat_python@okurmenkids.local",
        "first_name": "Azamat",
        "last_name": "",
        "position": "Тренер по Python",
        "experience_years": 6,
        "hire_date": dt.date(2021, 9, 1),
        "bio": "[DEMO] Ведёт Python и CyberSecurity, готовит студентов к реальным проектам.",
        "subjects": ["Python", "CyberSecurity"],
        "attendance_weights": {"present": 80, "late": 11, "absent": 7, "excused": 2},
        "homework_weights": {"checked": 70, "submitted": 10, "late": 8, "not_submitted": 12},
        "score_weights": {6: 15, 7: 30, 8: 30, 9: 15, 10: 10},
    },
    {
        "username": "aizada_frontend",
        "email": "aizada_frontend@okurmenkids.local",
        "first_name": "Aizada",
        "last_name": "",
        "position": "Тренер по Frontend",
        "experience_years": 3,
        "hire_date": dt.date(2024, 2, 1),
        "bio": "[DEMO] Ведёт Frontend Development, акцент на современных интерфейсах.",
        "subjects": ["Frontend"],
        "attendance_weights": {"present": 90, "late": 6, "absent": 3, "excused": 1},
        "homework_weights": {"checked": 82, "submitted": 8, "late": 4, "not_submitted": 6},
        "score_weights": {7: 10, 8: 25, 9: 40, 10: 25},
    },
]

SUBJECT_NAMES = [
    "Python",
    "Frontend",
    "Backend",
    "HTML/CSS/JS",
    "IT",
    "Soft Skills",
    "English",
    "CyberSecurity",
]

# name -> (subjects it covers, count_lesson)
COURSE_DEFS = {
    "[DEMO] Python Development": (["Python"], 40),
    "[DEMO] Frontend Development": (["Frontend", "HTML/CSS/JS"], 36),
    "[DEMO] IT Basics": (["IT"], 30),
    "[DEMO] Soft Skills": (["Soft Skills"], 24),
    "[DEMO] Backend Development": (["Backend"], 36),
    "[DEMO] CyberSecurity": (["CyberSecurity"], 28),
}

DEMO_ROOM_NAMES = ["[DEMO] Кабинет 201", "[DEMO] Кабинет 202", "[DEMO] Кабинет 203"]

# Every group this command owns — the exact registry clear_demo_data.py
# deletes by name. teacher/course/subject are matched by name against the
# dicts built above; weekdays are actual GroupSchedule.day_of_week codes,
# and also drive how many Lessons/week are generated (len(weekdays)).
GROUP_DEFS = [
    {
        "name": "IT-15", "teacher": "islam_it", "course": "[DEMO] IT Basics", "subject": "IT",
        "students": 8, "weekdays": ["mon", "wed", "fri"], "start_time": dt.time(9, 0), "end_time": dt.time(10, 30),
        "room": 0,
    },
    {
        "name": "IT-16", "teacher": "islam_it", "course": "[DEMO] IT Basics", "subject": "IT",
        "students": 9, "weekdays": ["tue", "thu"], "start_time": dt.time(9, 0), "end_time": dt.time(10, 30),
        "room": 0,
    },
    {
        "name": "Backend-7", "teacher": "islam_it", "course": "[DEMO] Backend Development", "subject": "Backend",
        "students": 7, "weekdays": ["sat"], "start_time": dt.time(9, 0), "end_time": dt.time(10, 30),
        "room": 0,
    },
    {
        "name": "Soft-10", "teacher": "khadizha_soft", "course": "[DEMO] Soft Skills", "subject": "Soft Skills",
        "students": 12, "weekdays": ["mon", "wed", "fri"], "start_time": dt.time(11, 0), "end_time": dt.time(12, 30),
        "room": 1,
    },
    {
        "name": "Soft-11", "teacher": "khadizha_soft", "course": "[DEMO] Soft Skills", "subject": "Soft Skills",
        "students": 10, "weekdays": ["tue", "thu"], "start_time": dt.time(11, 0), "end_time": dt.time(12, 30),
        "room": 1,
    },
    {
        "name": "Python-12", "teacher": "azamat_python", "course": "[DEMO] Python Development", "subject": "Python",
        "students": 14, "weekdays": ["mon", "wed", "fri"], "start_time": dt.time(14, 0), "end_time": dt.time(15, 30),
        "room": 2,
    },
    {
        "name": "Python-13", "teacher": "azamat_python", "course": "[DEMO] Python Development", "subject": "Python",
        "students": 12, "weekdays": ["tue", "thu"], "start_time": dt.time(14, 0), "end_time": dt.time(15, 30),
        "room": 2,
    },
    {
        "name": "Cyber-5", "teacher": "azamat_python", "course": "[DEMO] CyberSecurity", "subject": "CyberSecurity",
        "students": 8, "weekdays": ["sat"], "start_time": dt.time(14, 0), "end_time": dt.time(15, 30),
        "room": 2,
    },
    {
        "name": "Frontend-8", "teacher": "aizada_frontend", "course": "[DEMO] Frontend Development", "subject": "Frontend",
        "students": 10, "weekdays": ["mon", "wed", "fri"], "start_time": dt.time(14, 0), "end_time": dt.time(15, 30),
        "room": 0,
    },
    {
        "name": "Frontend-9", "teacher": "aizada_frontend", "course": "[DEMO] Frontend Development", "subject": "Frontend",
        "students": 10, "weekdays": ["tue", "thu"], "start_time": dt.time(14, 0), "end_time": dt.time(15, 30),
        "room": 0,
    },
]

DEMO_GROUP_NAMES = [g["name"] for g in GROUP_DEFS]

# The 3 test months (July/August/September 2026 — September is the primary
# one). Lessons are placed only in days 1-28 of each month, in four
# consecutive 7-day windows — matching exactly how
# services.monthly_report._week_buckets slices a month into "Week 1..4", so
# every seeded month always yields exactly 4 weekly-dynamics points.
DEMO_MONTHS = [(2026, 7), (2026, 8), (2026, 9)]
WEEK_STARTS = [1, 8, 15, 22]

# Which (teacher, year, month) MonthlyTeacherReport rows to create.
# Deliberately partial — Azamat/Aizada only ever get a September report,
# so their Groups list (and their August/July, in Aizada's case) has real
# underlying lesson data but no report yet: a real "create report / empty
# report list" case to test against, not a fabricated empty dataset.
REPORT_PLAN = [
    ("islam_it", 2026, 9, (
        "В течение месяца занятия проводились стабильно. Основной фокус был направлен "
        "на практическую работу студентов и закрепление материала."
    )),
    ("islam_it", 2026, 8, (
        "Август прошёл в спокойном темпе — повторение пройденного материала и "
        "подготовка групп к новому учебному потоку в сентябре."
    )),
    ("islam_it", 2026, 7, (
        "В июле группы работали над летними проектами, посещаемость оставалась на "
        "хорошем уровне несмотря на каникулярный период."
    )),
    ("khadizha_soft", 2026, 9, (
        "В этом месяце основной акцент был сделан на коммуникацию, командную работу "
        "и развитие soft skills."
    )),
    ("khadizha_soft", 2026, 8, (
        "Продолжили работу над навыками публичных выступлений — студенты подготовили "
        "и провели несколько мини-презентаций."
    )),
    ("azamat_python", 2026, 9, (
        "Студенты закрепляли навыки работы с реальными Python-проектами, домашние "
        "задания сдавались стабильно."
    )),
    ("aizada_frontend", 2026, 9, (
        "Группы активно осваивали вёрстку и основы интерфейсов, средний балл за "
        "домашние задания вырос по сравнению с прошлым месяцем."
    )),
]

FIRST_NAMES = [
    "Алихан", "Азамат", "Айжан", "Мээрим", "Нурбек", "Эльдар", "Алина", "Данияр",
    "Айгерим", "Бекзат", "Нурайым", "Жаныл", "Максат", "Аида", "Тимур", "Гулназ",
    "Эрлан", "Салтанат", "Уланбек", "Динара", "Марат", "Асель", "Руслан", "Жамиля",
    "Канат", "Айпери", "Бакыт", "Нурсултан", "Замира", "Абдылда", "Медер", "Нургуль",
    "Талант", "Айдана", "Бекболот", "Чолпон", "Сезим", "Арген", "Гүлайым", "Омурбек",
]

LAST_NAMES = [
    "Асанов", "Асанова", "Осмонов", "Осмонова", "Тологонов", "Тологонова",
    "Жумабеков", "Жумабекова", "Мамытов", "Мамытова", "Каримов", "Каримова",
    "Сыдыков", "Сыдыкова", "Абдыракманов", "Абдыракманова", "Нурматов", "Нурматова",
    "Сатыбалдиев", "Сатыбалдиева", "Токтогулов", "Токтогулова", "Бекова", "Беков",
    "Исаков", "Исакова", "Молдалиев", "Молдалиева", "Турсунов", "Турсунова",
    "Кадыров", "Кадырова", "Байгазиев", "Байгазиева", "Эсенов", "Эсенова",
]


def _weighted_choice(rng: random.Random, weights: dict):
    keys = list(weights.keys())
    values = list(weights.values())
    return rng.choices(keys, weights=values, k=1)[0]


class Command(BaseCommand):
    help = (
        "Creates a realistic, fully-connected DEMO dataset (teachers, groups, "
        "students, lessons, attendance, homework, monthly reports) for developing "
        "and testing the Monthly Teacher Reports feature. Development/testing "
        "only — refuses to run when DJANGO_ENV=production. Idempotent: safe to "
        "run more than once."
    )

    def handle(self, *args, **options):
        # Checked before any DB work, same reasoning as seed_dev_data.py: no
        # @transaction.atomic here so a production DATABASES config is never
        # even connected to before this guard can refuse.
        env = os.environ.get("DJANGO_ENV", "development")
        if env == "production":
            raise CommandError(
                "Refusing to run: DJANGO_ENV=production. seed_demo_data never "
                "creates demo data in production, and never opens a production "
                "database connection."
            )

        self.stdout.write(self.style.WARNING(
            "=== OKURMENKIDS DEMO DATA SEED (DJANGO_ENV=%s) — not for production use ===" % env
        ))

        self.rng = random.Random(RNG_SEED)
        self._seed()

    @transaction.atomic
    def _seed(self) -> None:
        admin = self._get_or_create_admin()
        subjects = self._get_or_create_subjects()
        courses = self._get_or_create_courses(subjects)
        rooms = self._get_or_create_rooms()
        teachers = self._get_or_create_teachers(subjects)
        groups = self._get_or_create_groups(teachers, courses, subjects, rooms)
        self._get_or_create_students(groups)
        self._generate_teaching_data(groups, teachers, admin)
        reports_created = self._get_or_create_reports(teachers)

        self._print_summary(admin, teachers, subjects, courses, groups, reports_created)

    # -- Users ---------------------------------------------------------

    def _get_or_create_admin(self) -> User:
        user, _ = User.objects.get_or_create(
            username=ADMIN_USERNAME,
            defaults={
                "email": ADMIN_EMAIL,
                "first_name": "Admin",
                "last_name": "OkurmenKIDS",
                "role": User.Role.ADMIN,
                "is_verified": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        # Demo credentials must always work, even if someone changed the
        # password while testing — a reseed restores it.
        user.set_password(ADMIN_PASSWORD)
        user.is_staff = True
        user.is_superuser = True
        user.role = User.Role.ADMIN
        user.is_active = True
        user.save()
        return user

    def _get_or_create_teachers(self, subjects: dict[str, Subject]) -> dict[str, Teacher]:
        teachers: dict[str, Teacher] = {}
        for cfg in DEMO_TEACHERS:
            existing = User.objects.filter(username=cfg["username"]).first()
            if existing is not None:
                teacher = existing.teacher_profile
                existing.set_password(TEACHER_PASSWORD)
                existing.is_active = True
                existing.is_verified = True
                existing.save()
            else:
                result = create_teacher(
                    username=cfg["username"],
                    email=cfg["email"],
                    first_name=cfg["first_name"],
                    last_name=cfg["last_name"],
                    password=TEACHER_PASSWORD,
                    position=cfg["position"],
                    experience_years=cfg["experience_years"],
                    hire_date=cfg["hire_date"],
                    bio=cfg["bio"],
                    send_email=False,
                )
                teacher = result.teacher
                self.stdout.write(f"Created demo teacher: {cfg['username']}")

            teacher.subjects.set([subjects[name] for name in cfg["subjects"]])
            teachers[cfg["username"]] = teacher
        return teachers

    # -- Catalogue -------------------------------------------------------

    def _get_or_create_subjects(self) -> dict[str, Subject]:
        result = {}
        for name in SUBJECT_NAMES:
            subject, _ = Subject.objects.get_or_create(
                name=name, defaults={"description": f"[DEMO] Направление «{name}».", "is_active": True}
            )
            result[name] = subject
        return result

    def _get_or_create_courses(self, subjects: dict[str, Subject]) -> dict[str, Course]:
        result = {}
        for name, (subject_names, count_lesson) in COURSE_DEFS.items():
            course, created = Course.objects.get_or_create(
                name=name,
                defaults={"count_lesson": count_lesson, "description": f"[DEMO] Демонстрационный курс «{name}»."},
            )
            if created:
                course.subjects.set([subjects[s] for s in subject_names])
            result[name] = course
        return result

    def _get_or_create_rooms(self) -> list[Room]:
        rooms = []
        for name in DEMO_ROOM_NAMES:
            room, _ = Room.objects.get_or_create(name=name, defaults={"capacity": 16, "description": "[DEMO] Демонстрационная аудитория."})
            rooms.append(room)
        return rooms

    # -- Groups / Students -------------------------------------------------

    def _get_or_create_groups(
        self,
        teachers: dict[str, Teacher],
        courses: dict[str, Course],
        subjects: dict[str, Subject],
        rooms: list[Room],
    ) -> dict[str, dict]:
        """Returns {group_name: {"group": Group, "group_teacher": GroupTeacher, "config": dict}}."""
        groups: dict[str, dict] = {}
        for cfg in GROUP_DEFS:
            course = courses[cfg["course"]]
            group, created = Group.objects.get_or_create(
                name=cfg["name"],
                defaults={
                    "course": course,
                    "start_date": dt.date(2026, 1, 12),
                    "max_students": cfg["students"] + 2,
                    "status": Group.Status.ACTIVE,
                    "description": f"[DEMO] Демонстрационная группа «{cfg['name']}».",
                },
            )
            if created:
                self.stdout.write(f"Created demo group: {group.name}")

            teacher = teachers[cfg["teacher"]]
            subject = subjects[cfg["subject"]]
            room = rooms[cfg["room"]]
            group_teacher = None
            for day in cfg["weekdays"]:
                schedule, _ = GroupSchedule.objects.get_or_create(
                    group=group,
                    teacher=teacher,
                    subject=subject,
                    day_of_week=day,
                    defaults={"start_time": cfg["start_time"], "end_time": cfg["end_time"], "room": room},
                )
                group_teacher = schedule.group_teacher

            groups[cfg["name"]] = {"group": group, "group_teacher": group_teacher, "config": cfg}
        return groups

    def _get_or_create_students(self, groups: dict[str, dict]) -> None:
        for entry in groups.values():
            group = entry["group"]
            count = entry["config"]["students"]
            pool = [(f, l) for f in FIRST_NAMES for l in LAST_NAMES]
            names = self.rng.sample(pool, k=count)
            for first_name, last_name in names:
                Student.objects.get_or_create(
                    first_name=first_name,
                    last_name=last_name,
                    group=group,
                    defaults={"is_active": True},
                )

    # -- Lessons / Attendance / Homework -----------------------------------

    def _lesson_dates(self, weekdays: list[str]) -> list[dt.date]:
        """Every date in DEMO_MONTHS (days 1-28 only, 4 clean weekly buckets
        per month) that falls on one of `weekdays` — chronologically sorted,
        so enumerating it 1..N gives a stable, rerun-safe lesson_number."""
        weekday_indexes = [WEEKDAY_CODES.index(code) for code in weekdays]
        dates = []
        for year, month in DEMO_MONTHS:
            for week_start_day in WEEK_STARTS:
                bucket_start = dt.date(year, month, week_start_day)
                for widx in weekday_indexes:
                    offset = (widx - bucket_start.weekday()) % 7
                    dates.append(bucket_start + dt.timedelta(days=offset))
        return sorted(dates)

    def _generate_teaching_data(self, groups: dict[str, dict], teachers: dict[str, Teacher], admin: User) -> None:
        for entry in groups.values():
            group = entry["group"]
            group_teacher = entry["group_teacher"]
            cfg = entry["config"]
            teacher_cfg = next(t for t in DEMO_TEACHERS if t["username"] == cfg["teacher"])
            teacher = teachers[cfg["teacher"]]
            subject_name = cfg["subject"]

            students = list(group.students.filter(is_active=True).order_by("id"))
            dates = self._lesson_dates(cfg["weekdays"])

            for lesson_number, date in enumerate(dates, start=1):
                has_homework = self.rng.random() < 0.85
                lesson, _ = Lesson.objects.get_or_create(
                    group_teacher=group_teacher,
                    lesson_number=lesson_number,
                    defaults={
                        "group": group,
                        "teacher": teacher,
                        "subject": Subject.objects.get(name=subject_name),
                        "date": date,
                        "start_time": cfg["start_time"],
                        "end_time": cfg["end_time"],
                        "topic": f"[DEMO] Занятие {lesson_number}: {subject_name}",
                        "status": Lesson.Status.COMPLETED,
                        "homework_not_required": not has_homework,
                        "started_at": timezone.make_aware(dt.datetime.combine(date, cfg["start_time"])),
                        "completed_at": timezone.make_aware(dt.datetime.combine(date, cfg["end_time"])),
                        "completed_by": admin,
                    },
                )

                self._seed_attendance(lesson, students, teacher_cfg)
                if has_homework:
                    self._seed_homework(lesson, students, teacher_cfg)

    def _seed_attendance(self, lesson: Lesson, students: list[Student], teacher_cfg: dict) -> None:
        records = [
            Attendance(student=student, lesson=lesson, status=_weighted_choice(self.rng, teacher_cfg["attendance_weights"]))
            for student in students
        ]
        Attendance.objects.bulk_create(records, ignore_conflicts=True)

    def _seed_homework(self, lesson: Lesson, students: list[Student], teacher_cfg: dict) -> None:
        homework, _ = Homework.objects.get_or_create(
            lesson=lesson,
            title=f"[DEMO] ДЗ к занятию {lesson.lesson_number}",
            defaults={
                "description": "[DEMO] Практическое задание по теме занятия.",
                "deadline": lesson.date + dt.timedelta(days=5),
            },
        )

        now = timezone.now()
        results = []
        for student in students:
            status = _weighted_choice(self.rng, teacher_cfg["homework_weights"])
            score = None
            submitted_at = None
            checked_at = None
            if status in (HomeworkResult.Status.CHECKED, HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.LATE):
                submitted_at = now
            if status in (HomeworkResult.Status.CHECKED,):
                checked_at = now
                score = _weighted_choice(self.rng, teacher_cfg["score_weights"])
            results.append(
                HomeworkResult(
                    homework=homework, student=student, status=status, score=score,
                    submitted_at=submitted_at, checked_at=checked_at,
                )
            )
        HomeworkResult.objects.bulk_create(results, ignore_conflicts=True)

    # -- Monthly Reports -----------------------------------------------

    def _get_or_create_reports(self, teachers: dict[str, Teacher]) -> int:
        created = 0
        for username, year, month, comment in REPORT_PLAN:
            _, was_created = MonthlyTeacherReport.objects.get_or_create(
                teacher=teachers[username], year=year, month=month, defaults={"comment": comment},
            )
            if was_created:
                created += 1
        return created

    # -- Summary -----------------------------------------------------------

    def _print_summary(self, admin, teachers, subjects, courses, groups, reports_created) -> None:
        group_qs = Group.objects.filter(name__in=DEMO_GROUP_NAMES)
        student_count = Student.objects.filter(group__name__in=DEMO_GROUP_NAMES).count()
        lesson_qs = Lesson.objects.filter(group__name__in=DEMO_GROUP_NAMES)
        attendance_count = Attendance.objects.filter(lesson__in=lesson_qs).count()
        homework_qs = Homework.objects.filter(lesson__in=lesson_qs)
        result_count = HomeworkResult.objects.filter(homework__in=homework_qs).count()
        report_count = MonthlyTeacherReport.objects.filter(teacher__in=teachers.values()).count()

        w = self.stdout.write
        line = "=" * 40
        w("")
        w(self.style.SUCCESS(line))
        w(self.style.SUCCESS("      OKURMENKIDS DEMO DATA"))
        w(self.style.SUCCESS(line))
        w("")
        w("Users:")
        w(f"  ✓ {admin.username}")
        for cfg in DEMO_TEACHERS:
            w(f"  ✓ {cfg['username']}")
        w("")
        w(f"Subjects:\n  ✓ {len(subjects)}")
        w("")
        w(f"Courses:\n  ✓ {len(courses)}")
        w("")
        w(f"Teachers:\n  ✓ {len(teachers)}")
        w("")
        w(f"Groups:\n  ✓ {group_qs.count()}")
        w("")
        w(f"Students:\n  ✓ {student_count}")
        w("")
        w(f"Lessons:\n  ✓ {lesson_qs.count()}")
        w("")
        w(f"Attendance:\n  ✓ {attendance_count}")
        w("")
        w(f"Homework:\n  ✓ {homework_qs.count()}")
        w("")
        w(f"Homework Results:\n  ✓ {result_count}")
        w("")
        w(f"Monthly Reports:\n  ✓ {report_count} (of which {reports_created} newly created this run)")
        w("")
        w(self.style.SUCCESS(line))
        w(self.style.SUCCESS("       DEMO DATA READY \U0001F680"))
        w(self.style.SUCCESS(line))
        w("")
        w("Login:")
        w("")
        w("ADMIN")
        w(f"username: {admin.username}")
        w(f"password: {ADMIN_PASSWORD}")
        w("")
        for cfg in DEMO_TEACHERS:
            w("TEACHER")
            w(f"username: {cfg['username']}")
            w(f"password: {TEACHER_PASSWORD}")
            w("")
        w(line)
