"""Generates a large, realistic, fully-connected mock dataset for the Academy
app — enough Students/Groups/Lessons/Attendance/Homework to exercise every
Admin and Teacher page under production-like volume.

This is `seed_dev_data`'s bigger sibling, not a replacement: it creates
*no new models or parallel architecture* — every row is a real User, Teacher,
Subject, Course, CourseLessonPlan, Room, Student, Group, GroupTeacher,
GroupSchedule, GroupTeacherLessonPlan, Lesson, Attendance, Homework or
HomeworkResult, built through the same services the API itself uses wherever
that's practical at this volume:

- Teachers are created via ``apps.users.services.create_teacher`` (the exact
  User+Teacher construction path the Admin's "create teacher" flow uses).
- Every GroupSchedule slot is checked against
  ``services.group_schedule_conflicts.find_schedule_{teacher,room,group}_conflict``
  *before* it is created — the same conflict rules the API enforces via
  ``GroupSchedule.clean()`` — so the generated schedule is conflict-free by
  construction, not by luck.
- Every Lesson comes from ``services.lesson_generator.generate_lessons_for_group``
  — the same idempotent generator the "Сгенерировать занятия" admin button
  calls. This command never fabricates a Lesson row directly; it only
  back-fills realistic status/attendance/homework *onto* generated lessons.

Refuses to run when DJANGO_ENV=production, exactly like `seed_dev_data` and
`reset_dev_db` — no flag overrides this.

Idempotent in the sense that matters: rerunning never duplicates or corrupts
data — every natural-key lookup (User.username, Subject/Course/Room/Group
.name) uses get_or_create, and Attendance/HomeworkResult generation skips
any Lesson/Homework that already has rows. A bare rerun on top of existing
data will only *add* to it (new students, possibly new groups depending on
random names), which is fine for incrementally growing a dataset; for the
exact same dataset byte-for-byte, pass --clear together with the same
--seed to start from an empty slate each time.
"""
from __future__ import annotations

import datetime as dt
import os
import random
from dataclasses import dataclass, field

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.academy.models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    GroupSchedule,
    GroupTeacher,
    GroupTeacherLessonPlan,
    Homework,
    HomeworkResult,
    Lesson,
    Room,
    Student,
)
from apps.academy.services import lesson_status
from apps.academy.services.group_schedule_conflicts import (
    find_schedule_group_conflict,
    find_schedule_room_conflict,
    find_schedule_teacher_conflict,
)
from apps.academy.services.lesson_generator import LessonGenerationError, generate_lessons_for_group
from apps.users.models import Subject, Teacher, User
from apps.users.services import create_teacher

DEV_PASSWORD = "MockData123!"  # nosec: dev-only fixture password, never used in production (see guard below)

DAY_POOL = ["mon", "tue", "wed", "thu", "fri", "sat"]  # school groups rarely run on Sunday
TIME_SLOTS = [
    (dt.time(9, 0), dt.time(10, 30)),
    (dt.time(10, 45), dt.time(12, 15)),
    (dt.time(12, 30), dt.time(14, 0)),
    (dt.time(14, 15), dt.time(15, 45)),
    (dt.time(16, 0), dt.time(17, 30)),
    (dt.time(17, 45), dt.time(19, 0)),
]

MALE_FIRST_NAMES = [
    "Айбек", "Азамат", "Алмаз", "Арген", "Асан", "Бакыт", "Бекзат", "Данияр", "Дастан", "Ерлан",
    "Эркин", "Замир", "Ислам", "Кубат", "Максат", "Марат", "Мирлан", "Нурбек", "Нурлан", "Омурбек",
    "Руслан", "Санжар", "Тилек", "Тимур", "Улан", "Чынгыз", "Эрлан", "Эмиль", "Адилет", "Бекболот",
    "Талант", "Жаныбек", "Канат", "Бактияр", "Айдар",
]
FEMALE_FIRST_NAMES = [
    "Аида", "Айгуль", "Айжан", "Айнура", "Айсулуу", "Акерке", "Алина", "Амина", "Асель", "Бегим",
    "Гулназ", "Дильноза", "Жаннат", "Жибек", "Зарина", "Индира", "Камила", "Медина", "Мунара",
    "Назгуль", "Нурай", "Перизат", "Салтанат", "Сезим", "Толгонай", "Умут", "Эльвира", "Чолпон",
    "Динара", "Мээрим", "Гулмира", "Сулуу", "Айзада", "Венера", "Назира",
]
MALE_LAST_NAMES = [
    "Тологонов", "Мамытов", "Осмонов", "Жумабеков", "Асанов", "Сатыбалдиев", "Каримов", "Байгазиев",
    "Молдалиев", "Абдиев", "Турсунов", "Кадыров", "Эсенов", "Бекболотов", "Джумалиев", "Ниязов",
    "Раимкулов", "Садыков", "Токтогулов", "Чоюнов", "Шергазиев", "Айтматов", "Джаманкулов", "Исаев",
    "Момунов", "Султанов", "Жусупов",
]
FEMALE_LAST_NAMES = [
    "Тологонова", "Мамытова", "Осмонова", "Жумабекова", "Асанова", "Сатыбалдиева", "Каримова",
    "Байгазиева", "Молдалиева", "Абдиева", "Турсунова", "Кадырова", "Эсенова", "Бекболотова",
    "Джумалиева", "Ниязова", "Раимкулова", "Садыкова", "Токтогулова", "Чоюнова", "Шергазиева",
    "Джаманкулова", "Исаева", "Момунова", "Султанова", "Жусупова",
]

SUBJECT_DEFS = [
    ("Python для детей", "Основы программирования на Python: синтаксис, логика, первые проекты."),
    ("JavaScript", "Программирование в браузере и на сервере на JavaScript."),
    ("Веб-дизайн", "Верстка, UI/UX-основы, адаптивная вёрстка."),
    ("Робототехника", "Конструирование и программирование учебных роботов."),
    ("Scratch программирование", "Визуальное программирование для начинающих."),
    ("Java", "Объектно-ориентированное программирование на Java."),
    ("C++ для детей", "Основы алгоритмов и структур данных на C++."),
    ("Кибербезопасность", "Основы информационной безопасности и защиты данных."),
    ("Разработка игр", "Создание 2D-игр на игровых движках."),
    ("Анализ данных", "Работа с данными, таблицами и визуализацией."),
    ("Мобильная разработка", "Создание мобильных приложений."),
    ("Разработка на Go", "Основы серверного программирования на Go."),
]

# (course name, short group-name code, [subject names], count_lesson range)
# Ranges are deliberately generous (not the leaner 20-30ish a single group
# would need) because groups sharing a course also share its lesson-plan
# cursor (see lesson_generator's "legacy/shared path") — this is what
# ultimately drives the dataset well past the 1000+ lessons / 10,000+
# attendance / 5,000+ homework-result targets at the requested group/student
# counts, while course.lesson_plans total still stays close to the
# suggested 100-300 range.
COURSE_DEFS = [
    ("Python для детей — полный курс", "PY", ["Python для детей", "Анализ данных"], (30, 50)),
    ("Frontend-разработка", "FE", ["JavaScript", "Веб-дизайн", "Мобильная разработка"], (28, 46)),
    ("Робототехника: старт", "ROBO", ["Робототехника", "Scratch программирование"], (24, 40)),
    ("Java для начинающих", "JAVA", ["Java", "Разработка на Go"], (26, 42)),
    ("Кибербезопасность: базовый уровень", "CYBER", ["Кибербезопасность", "Python для детей"], (24, 38)),
    ("Разработка игр на C++", "GAME", ["Разработка игр", "C++ для детей"], (28, 46)),
]

TOPIC_FRAGMENTS = [
    "Введение и знакомство с инструментами", "Переменные и типы данных", "Условные конструкции",
    "Циклы", "Функции и их параметры", "Работа со списками", "Работа со словарями/объектами",
    "Отладка и поиск ошибок", "Мини-проект: часть 1", "Мини-проект: часть 2", "Работа с файлами",
    "Введение в ООП", "Классы и объекты", "Наследование", "Работа с API", "Тестирование кода",
    "Оптимизация и рефакторинг", "Командная работа над проектом", "Презентация проекта",
    "Повторение и практика", "Работа с базой данных", "Обработка ошибок и исключений",
    "Пользовательский интерфейс", "Алгоритмы сортировки", "Структуры данных",
]
HOMEWORK_TITLE_TEMPLATES = [
    "Практическое задание: {topic}",
    "Закрепление темы «{topic}»",
    "Мини-проект по теме «{topic}»",
    "Самостоятельная работа: {topic}",
]
HOMEWORK_DESCRIPTION = (
    "Выполните практические задачи по теме занятия, оформите решение и будьте готовы "
    "объяснить ход рассуждений на следующем занятии. При возникновении сложностей "
    "используйте материалы занятия и не стесняйтесь задавать вопросы преподавателю."
)
CANCELLATION_REASONS = [
    "Тренер заболел", "Праздничный день", "Перенос по договорённости с группой",
    "Технические работы в учебном центре", "Отмена по погодным условиям",
]
HOMEWORK_COMMENTS = [
    "Хорошая работа, так держать!", "Есть небольшие недочёты, разберём на занятии.",
    "Отличное решение, видно понимание темы.", "Нужно доработать — обсудим индивидуально.",
    "Сдано с опозданием, но качественно выполнено.", "",
]


@dataclass
class SeedCounts:
    admins: int = 0
    teachers: int = 0
    subjects: int = 0
    courses: int = 0
    lesson_plans: int = 0
    rooms: int = 0
    students: int = 0
    groups: int = 0
    programs: int = 0
    schedules: int = 0
    lessons: int = 0
    attendance: int = 0
    homework: int = 0
    homework_results: int = 0
    edge_cases: list[str] = field(default_factory=list)


class Command(BaseCommand):
    help = (
        "Generates a large, realistic, fully-connected mock dataset (400+ students "
        "and all related academic data) using the existing Academy models and "
        "services only. Development/testing only — refuses to run when "
        "DJANGO_ENV=production. See the module docstring for details."
    )

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=400, help="Number of students to create (default 400).")
        parser.add_argument("--teachers", type=int, default=25, help="Number of teachers to create (default 25).")
        parser.add_argument("--groups", type=int, default=38, help="Number of groups to create (default 38).")
        parser.add_argument("--admins", type=int, default=4, help="Number of admin users to create (default 4).")
        parser.add_argument("--rooms", type=int, default=12, help="Number of rooms to create (default 12).")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing Academy data (Students/Groups/Lessons/.../Teachers) before seeding. "
            "Development only — refused in production like everything else in this command.",
        )
        parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible generation.")

    def handle(self, *args, **options):
        # Checked before anything touches the database — same reasoning as
        # seed_dev_data/reset_dev_db: entering a transaction against a
        # production DATABASES config means dialling out to production
        # before this guard would ever get a chance to refuse.
        env = os.environ.get("DJANGO_ENV", "development")
        if env == "production":
            raise CommandError(
                "Refusing to run: DJANGO_ENV=production. seed_mock_data never creates "
                "mock data in production, and never opens a production database connection."
            )

        self.rng = random.Random(options["seed"])
        self.stdout.write(self.style.WARNING(
            f"=== MOCK DATA GENERATOR (DJANGO_ENV={env}) — development/testing only ==="
        ))
        if options["seed"] is not None:
            self.stdout.write(
                f"Random seed: {options['seed']} (combine with --clear for the exact same dataset on rerun)."
            )

        with transaction.atomic():
            if options["clear"]:
                self._clear()
            counts, credentials = self._seed(options)

        self._verify(counts)
        self._print_summary(counts, credentials)

    # -- clearing ------------------------------------------------------

    def _clear(self) -> None:
        """Wipes every Academy-domain row plus non-admin (Teacher) Users, in
        FK-safe order (children before PROTECT-guarded parents). Admin Users
        are left untouched so whoever is logged in as admin locally never
        gets locked out by re-running this command."""
        self.stdout.write(self.style.WARNING("Clearing existing Academy data..."))
        HomeworkResult.objects.all().delete()
        Homework.objects.all().delete()
        Attendance.objects.all().delete()
        Lesson.objects.all().delete()
        GroupSchedule.objects.all().delete()
        GroupTeacherLessonPlan.objects.all().delete()
        GroupTeacher.objects.all().delete()
        Student.objects.all().delete()
        Group.objects.all().delete()
        CourseLessonPlan.objects.all().delete()
        Course.objects.all().delete()
        Room.objects.all().delete()
        # Deleting the User cascades to its Teacher profile (OneToOne CASCADE).
        User.objects.filter(role=User.Role.TEACHER).delete()
        Subject.objects.all().delete()
        self.stdout.write("Cleared.")

    # -- orchestration ---------------------------------------------------

    def _seed(self, options: dict) -> tuple[SeedCounts, dict]:
        counts = SeedCounts()
        credentials: dict = {}

        admins = self._create_admins(options["admins"], counts)
        credentials["admins"] = [a.username for a in admins]

        subjects = self._create_subjects(counts)
        teachers = self._create_teachers(options["teachers"], subjects, counts)
        credentials["teachers_sample"] = [t.user.username for t in teachers[:5]]
        credentials["teachers_total"] = len(teachers)

        courses = self._create_courses(subjects, counts)
        rooms = self._create_rooms(options["rooms"], counts)

        groups = self._create_groups(courses, options["groups"], counts)
        self._create_students(groups, options["students"], counts)
        self._create_programs_and_schedules(groups, teachers, courses, counts)

        all_new_lessons = self._generate_lessons(groups, counts)
        self._assign_lesson_statuses(all_new_lessons, counts)
        self._generate_attendance(counts)
        self._generate_homework_results(counts)

        return counts, credentials

    # -- 1. admins ---------------------------------------------------------

    def _create_admins(self, n: int, counts: SeedCounts) -> list[User]:
        admins = []
        for i in range(1, n + 1):
            username = f"admin{i:02d}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@okurmenkids.dev",
                    "first_name": "Admin",
                    "last_name": str(i),
                    "role": User.Role.ADMIN,
                    "is_verified": True,
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            if created:
                user.set_password(DEV_PASSWORD)
                user.save(update_fields=["password"])
                counts.admins += 1
            admins.append(user)
        return admins

    # -- 2. subjects ---------------------------------------------------------

    def _create_subjects(self, counts: SeedCounts) -> list[Subject]:
        subjects = []
        for name, description in SUBJECT_DEFS:
            subject, created = Subject.objects.get_or_create(name=name, defaults={"description": description})
            if created:
                counts.subjects += 1
            subjects.append(subject)
        return subjects

    # -- 3. teachers ---------------------------------------------------------

    def _create_teachers(self, n: int, subjects: list[Subject], counts: SeedCounts) -> list[Teacher]:
        teachers: list[Teacher] = []
        for i in range(1, n + 1):
            username = f"teacher{i:03d}"
            existing = User.objects.filter(username=username).first()
            if existing is not None:
                teachers.append(existing.teacher_profile)
                continue

            is_male = self.rng.random() < 0.5
            first = self.rng.choice(MALE_FIRST_NAMES if is_male else FEMALE_FIRST_NAMES)
            last = self.rng.choice(MALE_LAST_NAMES if is_male else FEMALE_LAST_NAMES)
            # 1-2 subjects per teacher, so every subject ends up with several
            # qualified teachers to pick from when building group programs.
            own_subjects = self.rng.sample(subjects, k=self.rng.choice([1, 1, 2]))

            result = create_teacher(
                username=username,
                email=f"{username}@okurmenkids.dev",
                first_name=first,
                last_name=last,
                password=DEV_PASSWORD,
                phone=self._phone(700_000_000 + i),
                position=self.rng.choice(["Тренер", "Старший тренер", "Ведущий тренер"]),
                experience_years=self.rng.randint(0, 12),
                subjects=own_subjects,
                is_active=self.rng.random() > 0.05,  # a few inactive teachers, for realism
                send_email=False,
            )
            counts.teachers += 1
            teachers.append(result.teacher)
        return teachers

    # -- 4. courses + lesson plans ------------------------------------------

    def _create_courses(self, subjects: list[Subject], counts: SeedCounts) -> list[Course]:
        by_name = {s.name: s for s in subjects}
        courses = []
        for name, code, subject_names, lesson_range in COURSE_DEFS:
            course_subjects = [by_name[n] for n in subject_names]
            count_lesson = self.rng.randint(*lesson_range)
            course, created = Course.objects.get_or_create(
                name=name,
                defaults={
                    "count_lesson": count_lesson,
                    "description": f"Курс «{name}» — {count_lesson} занятий.",
                },
            )
            course.code = code  # not a model field — stashed for this run's group naming only
            if created:
                course.subjects.add(*course_subjects)
                for n in range(1, course.count_lesson + 1):
                    subject = course_subjects[n % len(course_subjects)]
                    topic_text = TOPIC_FRAGMENTS[(n - 1) % len(TOPIC_FRAGMENTS)]
                    has_homework = self.rng.random() < 0.6
                    CourseLessonPlan.objects.create(
                        course=course,
                        lesson_number=n,
                        subject=subject,
                        topic=f"Занятие {n}: {topic_text}",
                        description="" if self.rng.random() < 0.3 else f"Разбираем: {topic_text.lower()}.",
                        homework_title=(
                            HOMEWORK_TITLE_TEMPLATES[n % len(HOMEWORK_TITLE_TEMPLATES)].format(topic=topic_text)
                            if has_homework
                            else ""
                        ),
                        homework_description=HOMEWORK_DESCRIPTION if has_homework else "",
                    )
                    counts.lesson_plans += 1
                counts.courses += 1
            courses.append(course)
        return courses

    # -- 5. rooms --------------------------------------------------------

    def _create_rooms(self, n: int, counts: SeedCounts) -> list[Room]:
        themed = ["Кабинет робототехники", "Компьютерный класс", "IT-лаборатория", "Лекционный зал"]
        rooms = []
        for i in range(1, n + 1):
            name = f"{themed[i % len(themed)]} {100 + i}" if i % 3 == 0 else f"Кабинет {100 + i}"
            room, created = Room.objects.get_or_create(
                name=name,
                defaults={"capacity": self.rng.choice([10, 12, 15, 18, 20]), "description": ""},
            )
            if created:
                counts.rooms += 1
            rooms.append(room)
        return rooms

    # -- 6. groups ---------------------------------------------------------

    def _create_groups(self, courses: list[Course], n: int, counts: SeedCounts) -> list[Group]:
        today = timezone.localdate()
        code_counters: dict[str, int] = {}
        groups = []
        for i in range(n):
            course = self.rng.choice(courses)
            code = getattr(course, "code", "GRP")
            code_counters[code] = code_counters.get(code, 0) + 1
            name = f"{code}-{code_counters[code]:02d}"
            status = self.rng.choices(
                [Group.Status.ACTIVE, Group.Status.PAUSED, Group.Status.COMPLETED, Group.Status.CANCELLED],
                weights=[55, 15, 20, 10],
            )[0]

            if status == Group.Status.COMPLETED:
                start_date = today - dt.timedelta(days=self.rng.randint(220, 340))
            elif status == Group.Status.CANCELLED:
                start_date = today - dt.timedelta(days=self.rng.randint(10, 200))
            else:
                start_date = today - dt.timedelta(days=self.rng.randint(20, 230))

            end_date = None
            if status in (Group.Status.COMPLETED, Group.Status.CANCELLED):
                end_date = start_date + dt.timedelta(days=self.rng.randint(90, 220))

            max_students = self.rng.choice([8, 10, 12, 12, 14, 15, 16])

            group, created = Group.objects.get_or_create(
                name=name,
                defaults={
                    "course": course,
                    "start_date": start_date,
                    "end_date": end_date,
                    "max_students": max_students,
                    "status": status,
                    "description": f"Группа «{name}» по курсу «{course.name}».",
                },
            )
            if created:
                counts.groups += 1
            groups.append(group)
        return groups

    # -- 7. students ---------------------------------------------------------

    def _create_students(self, groups: list[Group], n: int, counts: SeedCounts) -> None:
        assignable_groups = [g for g in groups if g.status != Group.Status.CANCELLED]
        # Edge case: one deliberately empty group — excluded from assignment
        # for the whole run, never just its first few students.
        empty_group = assignable_groups[0] if assignable_groups else None
        # Edge case: one group pushed to a low capacity so the natural random
        # fill below reaches (and stops at) "near/at full" on its own.
        near_capacity_group = assignable_groups[1] if len(assignable_groups) > 1 else None
        if near_capacity_group is not None:
            near_capacity_group.max_students = 8
            near_capacity_group.save(update_fields=["max_students"])

        fillable_groups = [g for g in assignable_groups if g is not empty_group] or assignable_groups
        occupancy = {g.id: g.students_count for g in groups}
        unassigned_count = 0

        for i in range(1, n + 1):
            is_male = self.rng.random() < 0.5
            first = self.rng.choice(MALE_FIRST_NAMES if is_male else FEMALE_FIRST_NAMES)
            last = self.rng.choice(MALE_LAST_NAMES if is_male else FEMALE_LAST_NAMES)

            if i == 1:
                # Long-name edge case, for UI truncation/wrapping testing.
                first = "Александра-Виктория-Умутайым"
                last = "Абдирахманова-Константинопольская"

            candidates = [
                g for g in fillable_groups
                if g.max_students is None or occupancy.get(g.id, 0) < g.max_students
            ]
            group = self.rng.choice(candidates) if candidates else None
            if group is None:
                unassigned_count += 1

            phone = self._phone(500_000_000 + i)
            has_parent_phone = self.rng.random() > 0.15  # ~15% missing parent phone, by design
            is_active = self.rng.random() > 0.06  # ~6% inactive students, by design

            student, created = Student.objects.get_or_create(
                phone=phone,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "parent_phone": self._phone(600_000_000 + i) if has_parent_phone else "",
                    "group": group,
                    "is_active": is_active,
                },
            )
            if created:
                counts.students += 1
                if group is not None:
                    occupancy[group.id] = occupancy.get(group.id, 0) + 1

        if empty_group is not None:
            counts.edge_cases.append(f"Group with no students: {empty_group.name}")
        if near_capacity_group is not None:
            counts.edge_cases.append(
                f"Group near full capacity: {near_capacity_group.name} "
                f"({occupancy.get(near_capacity_group.id, 0)}/{near_capacity_group.max_students})"
            )
        if unassigned_count:
            counts.edge_cases.append(
                f"Students intentionally left unassigned (all groups full): {unassigned_count}"
            )
        counts.edge_cases.append(
            "Student with a long name: Александра-Виктория-Умутайым Абдирахманова-Константинопольская"
        )

    # -- 8. GroupTeacher programs + GroupSchedule ---------------------------

    def _create_programs_and_schedules(
        self, groups: list[Group], teachers: list[Teacher], courses: list[Course], counts: SeedCounts,
    ) -> None:
        by_subject: dict[int, list[Teacher]] = {}
        for teacher in teachers:
            if not teacher.is_active:
                continue
            for subject in teacher.subjects.all():
                by_subject.setdefault(subject.id, []).append(teacher)

        teacher_program_counts: dict[int, int] = {}
        # "Teacher with many programs" edge case: pick a teacher who teaches
        # the one subject shared by the most courses (rather than an
        # arbitrary teacher who might not match any group's course at all —
        # that left this edge case at 0 programs in practice), so every
        # group whose course includes that subject deterministically uses
        # them, never left to random luck.
        star_teacher: Teacher | None = None
        anchor_subject_id: int | None = None
        if courses:
            subject_course_counts: dict[int, int] = {}
            for course in courses:
                for subject in course.subjects.all():
                    subject_course_counts[subject.id] = subject_course_counts.get(subject.id, 0) + 1
            if subject_course_counts:
                anchor_subject_id = max(subject_course_counts, key=subject_course_counts.get)
                anchor_candidates = by_subject.get(anchor_subject_id)
                if anchor_candidates:
                    star_teacher = anchor_candidates[0]

        for gi, group in enumerate(groups):
            if group.status == Group.Status.CANCELLED:
                continue  # a cancelled group legitimately gets no programs/schedule

            course_subjects = list(group.course.subjects.all())
            if not course_subjects:
                continue

            if star_teacher is not None and any(s.id == anchor_subject_id for s in course_subjects):
                primary_subject = next(s for s in course_subjects if s.id == anchor_subject_id)
                primary_teacher = star_teacher
            else:
                primary_subject = self.rng.choice(course_subjects)
                candidates = by_subject.get(primary_subject.id) or teachers
                primary_teacher = self.rng.choice(candidates)
            assignments = [(primary_teacher, primary_subject)]

            if len(course_subjects) > 1 and self.rng.random() < 0.85:
                secondary_subject = self.rng.choice([s for s in course_subjects if s.id != primary_subject.id])
                secondary_candidates = by_subject.get(secondary_subject.id) or teachers
                secondary_teacher = self.rng.choice(
                    [t for t in secondary_candidates if t.id != primary_teacher.id] or secondary_candidates
                )
                assignments.append((secondary_teacher, secondary_subject))

            group_teachers_for_group: list[GroupTeacher] = []
            for teacher, subject in assignments:
                slots_needed = self.rng.choice([1, 2, 2, 3])
                group_teacher = self._create_schedule_slots(group, teacher, subject, slots_needed, counts)
                if group_teacher is not None:
                    group_teachers_for_group.append(group_teacher)
                    teacher_program_counts[teacher.id] = teacher_program_counts.get(teacher.id, 0) + 1

            # A handful of groups' secondary program uses its own individual
            # lesson plan instead of the shared course plan — exercises
            # GroupTeacherLessonPlan / the generator's "individual path" too.
            if len(group_teachers_for_group) > 1 and gi % 3 == 0:
                self._create_individual_plan(group_teachers_for_group[1], counts)

        if star_teacher is not None:
            counts.edge_cases.append(
                f"Teacher with many programs: {star_teacher.user.get_full_name()} "
                f"({teacher_program_counts.get(star_teacher.id, 0)} programs)"
            )

    def _create_schedule_slots(
        self, group: Group, teacher: Teacher, subject: Subject, slots_needed: int, counts: SeedCounts,
    ) -> GroupTeacher | None:
        group_teacher: GroupTeacher | None = None
        created_slots = 0
        attempts = 0
        while created_slots < slots_needed and attempts < 40:
            attempts += 1
            day = self.rng.choice(DAY_POOL)
            start_time, end_time = self.rng.choice(TIME_SLOTS)
            room = self.rng.choice(self._rooms_cache)

            if find_schedule_teacher_conflict(teacher=teacher, day_of_week=day, start_time=start_time, end_time=end_time):
                continue
            if find_schedule_room_conflict(room=room, day_of_week=day, start_time=start_time, end_time=end_time):
                continue
            if find_schedule_group_conflict(group=group, day_of_week=day, start_time=start_time, end_time=end_time):
                continue

            schedule = GroupSchedule.objects.filter(
                group=group, teacher=teacher, subject=subject, day_of_week=day,
                start_time=start_time, end_time=end_time,
            ).first()
            created = schedule is None
            if created:
                # Building + saving manually (not get_or_create) so we can set
                # `_defer_schedule_sync` first — without it, GroupSchedule's own
                # post_save signal would auto-generate this group's lessons
                # *per slot* (see signals.py), meaning by the time this
                # method's caller explicitly calls generate_lessons_for_group()
                # once for the whole group, almost everything would already
                # exist and its return value (and our own lesson count) would
                # silently undercount. One explicit generation call per group,
                # after every slot is in place, mirrors exactly how the Admin's
                # own Group page defers this (see GroupAdmin / signals.py).
                schedule = GroupSchedule(
                    group=group, teacher=teacher, subject=subject, day_of_week=day,
                    start_time=start_time, end_time=end_time, room=room,
                )
                schedule._defer_schedule_sync = True
                schedule.save()
            group_teacher = schedule.group_teacher
            if created:
                created_slots += 1
                counts.schedules += 1
        return group_teacher

    def _create_individual_plan(self, group_teacher: GroupTeacher, counts: SeedCounts) -> None:
        if group_teacher.lesson_plans.exists():
            return
        n_lessons = self.rng.randint(6, 12)
        for n in range(1, n_lessons + 1):
            topic_text = TOPIC_FRAGMENTS[(n - 1) % len(TOPIC_FRAGMENTS)]
            has_homework = self.rng.random() < 0.6
            GroupTeacherLessonPlan.objects.get_or_create(
                group_teacher=group_teacher,
                lesson_number=n,
                defaults={
                    "topic": f"Занятие {n}: {topic_text}",
                    "homework_title": (
                        HOMEWORK_TITLE_TEMPLATES[n % len(HOMEWORK_TITLE_TEMPLATES)].format(topic=topic_text)
                        if has_homework else ""
                    ),
                    "homework_description": HOMEWORK_DESCRIPTION if has_homework else "",
                },
            )
            counts.lesson_plans += 1

    # -- 9. lesson generation (existing service) ----------------------------

    def _generate_lessons(self, groups: list[Group], counts: SeedCounts) -> list[Lesson]:
        all_new: list[Lesson] = []
        for group in groups:
            try:
                created = generate_lessons_for_group(group)
            except LessonGenerationError:
                created = []  # e.g. a cancelled group, or one with no active program — expected
            all_new.extend(created)
        counts.lessons += len(all_new)

        cancelled_groups = [g.name for g in groups if g.status == Group.Status.CANCELLED]
        if cancelled_groups:
            counts.edge_cases.append(
                f"Cancelled group with correctly zero lessons: {cancelled_groups[0]}"
            )
        return all_new

    # -- 10. lesson status backfill ------------------------------------------

    def _assign_lesson_statuses(self, lessons: list[Lesson], counts: SeedCounts) -> None:
        """The generator only ever produces `status=SCHEDULED` lessons —
        this back-fills a realistic status mix (~60% completed / ~10%
        cancelled / ~25% scheduled / ~5% in_progress overall) correlated
        with each lesson's own date, since a genuinely future lesson should
        essentially never already be "completed"."""
        today = timezone.localdate()
        to_update: list[Lesson] = []

        for lesson in lessons:
            if lesson.date < today:
                status = self.rng.choices(
                    [Lesson.Status.COMPLETED, Lesson.Status.CANCELLED, Lesson.Status.SCHEDULED, Lesson.Status.IN_PROGRESS],
                    weights=[85, 8, 5, 2],
                )[0]
            elif lesson.date == today:
                status = self.rng.choices(
                    [Lesson.Status.IN_PROGRESS, Lesson.Status.COMPLETED, Lesson.Status.SCHEDULED, Lesson.Status.CANCELLED],
                    weights=[35, 25, 30, 10],
                )[0]
            else:
                status = self.rng.choices(
                    [Lesson.Status.SCHEDULED, Lesson.Status.CANCELLED], weights=[90, 10],
                )[0]

            lesson.status = status
            teacher_user = lesson.effective_teacher.user if lesson.effective_teacher else None
            start_dt = timezone.make_aware(dt.datetime.combine(lesson.date, lesson.start_time))
            end_dt = timezone.make_aware(dt.datetime.combine(lesson.date, lesson.end_time))

            if status == Lesson.Status.COMPLETED:
                lesson.started_at = start_dt
                lesson.completed_at = end_dt
                lesson.completed_by = teacher_user
            elif status == Lesson.Status.IN_PROGRESS:
                lesson.started_at = start_dt
            elif status == Lesson.Status.CANCELLED:
                lesson.cancellation_reason = self.rng.choice(CANCELLATION_REASONS)

            to_update.append(lesson)

        Lesson.objects.bulk_update(
            to_update, ["status", "started_at", "completed_at", "completed_by", "cancellation_reason"],
            batch_size=500,
        )

        counts_by_status = lesson_status.lesson_status_counts(Lesson.objects.filter(id__in=[l.id for l in lessons]))
        counts.edge_cases.append(
            f"Lesson status mix (this run): completed={counts_by_status['completed']}, "
            f"cancelled={counts_by_status['cancelled']}, scheduled={counts_by_status['scheduled']}, "
            f"in_progress={counts_by_status['in_progress']}, attention={counts_by_status['attention']}"
        )

    # -- 11. attendance -------------------------------------------------------

    def _generate_attendance(self, counts: SeedCounts) -> None:
        completed_lessons = (
            Lesson.objects.filter(status=Lesson.Status.COMPLETED)
            .select_related("group")
            .order_by("group_id", "date")
        )
        students_by_group: dict[int, list[Student]] = {}
        forced_full_group: set[int] = set()
        forced_mixed_group: set[int] = set()
        to_create: list[Attendance] = []

        for lesson in completed_lessons:
            if Attendance.objects.filter(lesson=lesson).exists():
                continue  # idempotent: never re-generate attendance for an already-marked lesson

            roster = students_by_group.get(lesson.group_id)
            if roster is None:
                roster = list(Student.objects.filter(group_id=lesson.group_id, is_active=True))
                students_by_group[lesson.group_id] = roster
            if not roster:
                continue

            present_p = self.rng.uniform(0.75, 0.90)
            remaining = 1 - present_p
            absent_p = remaining * self.rng.uniform(0.5, 0.75)
            late_p = remaining * self.rng.uniform(0.15, 0.35)
            excused_p = max(remaining - absent_p - late_p, 0.0)
            weights = [present_p, absent_p, late_p, excused_p]
            statuses = [Attendance.Status.PRESENT, Attendance.Status.ABSENT, Attendance.Status.LATE, Attendance.Status.EXCUSED]

            force_full = lesson.group_id not in forced_full_group
            force_mixed = lesson.group_id not in forced_mixed_group and not force_full

            for student in roster:
                if force_full:
                    status = Attendance.Status.PRESENT
                elif force_mixed:
                    status = statuses[len(to_create) % len(statuses)]  # cycle so every status appears
                else:
                    status = self.rng.choices(statuses, weights=weights)[0]
                to_create.append(Attendance(student=student, lesson=lesson, status=status))

            if force_full:
                forced_full_group.add(lesson.group_id)
            elif force_mixed:
                forced_mixed_group.add(lesson.group_id)

        Attendance.objects.bulk_create(to_create, batch_size=500)
        counts.attendance += len(to_create)
        if forced_full_group:
            counts.edge_cases.append(f"Lessons with 100% attendance forced for {len(forced_full_group)} group(s)")
        if forced_mixed_group:
            counts.edge_cases.append(f"Lessons with mixed attendance forced for {len(forced_mixed_group)} group(s)")

    # -- 12. homework results -------------------------------------------------

    def _generate_homework_results(self, counts: SeedCounts) -> None:
        counts.homework = Homework.objects.count()

        # One deliberately very long description, for UI overflow testing.
        long_homework = Homework.objects.order_by("id").first()
        if long_homework is not None:
            long_homework.description = (HOMEWORK_DESCRIPTION + " ") * 40
            long_homework.save(update_fields=["description"])
            counts.edge_cases.append(f"Homework with a very long description: id={long_homework.id}")

        homeworks = (
            Homework.objects.filter(lesson__status=Lesson.Status.COMPLETED)
            .select_related("lesson")
            .order_by("lesson__group_id")
        )
        students_by_group: dict[int, list[Student]] = {}
        to_create: list[HomeworkResult] = []
        now = timezone.now()
        statuses = [
            HomeworkResult.Status.NOT_SUBMITTED, HomeworkResult.Status.SUBMITTED,
            HomeworkResult.Status.LATE, HomeworkResult.Status.CHECKED,
        ]
        weights = [15, 25, 10, 50]

        for homework in homeworks:
            if HomeworkResult.objects.filter(homework=homework).exists():
                continue  # idempotent: never re-grade an already-populated homework

            group_id = homework.lesson.group_id
            roster = students_by_group.get(group_id)
            if roster is None:
                roster = list(Student.objects.filter(group_id=group_id, is_active=True))
                students_by_group[group_id] = roster
            if not roster:
                continue

            for student in roster:
                status = self.rng.choices(statuses, weights=weights)[0]
                score = None
                comment = ""
                submitted_at = None
                checked_at = None
                if status in (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.LATE, HomeworkResult.Status.CHECKED):
                    submitted_at = now - dt.timedelta(days=self.rng.randint(0, 5))
                if status == HomeworkResult.Status.CHECKED:
                    score = self.rng.randint(4, 10)
                    comment = self.rng.choice(HOMEWORK_COMMENTS)
                    checked_at = submitted_at + dt.timedelta(hours=self.rng.randint(1, 48)) if submitted_at else now
                to_create.append(HomeworkResult(
                    homework=homework, student=student, status=status, score=score,
                    comment=comment, submitted_at=submitted_at, checked_at=checked_at,
                ))

        HomeworkResult.objects.bulk_create(to_create, batch_size=500)
        counts.homework_results += len(to_create)
        pending = sum(1 for r in to_create if r.status in (HomeworkResult.Status.NOT_SUBMITTED, HomeworkResult.Status.SUBMITTED))
        if pending:
            counts.edge_cases.append(f"Homework results still pending review: {pending}")

    # -- verification ---------------------------------------------------------

    def _verify(self, counts: SeedCounts) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Verifying..."))
        try:
            call_command("check")
            self.stdout.write("  Django system checks: OK")
        except SystemExit:
            self.stdout.write(self.style.ERROR("  Django system checks: FAILED"))

        dup_lessons = (
            Lesson.objects.values("group_teacher", "lesson_number")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .count()
        )
        dup_attendance = (
            Attendance.objects.values("student", "lesson")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .count()
        )
        self.stdout.write(f"  Duplicate (group_teacher, lesson_number) lessons: {dup_lessons}")
        self.stdout.write(f"  Duplicate (student, lesson) attendance rows: {dup_attendance}")

        conflicts = 0
        for schedule in GroupSchedule.objects.filter(is_active=True).select_related("teacher", "room", "group"):
            if find_schedule_teacher_conflict(
                teacher=schedule.teacher, day_of_week=schedule.day_of_week,
                start_time=schedule.start_time, end_time=schedule.end_time, exclude_schedule_id=schedule.pk,
            ):
                conflicts += 1
        self.stdout.write(f"  Teacher schedule conflicts detected: {conflicts}")

        status_counts = lesson_status.lesson_status_counts(Lesson.objects.all())
        self.stdout.write(
            f"  Lesson KPI totals — total={status_counts['total']}, completed={status_counts['completed']}, "
            f"cancelled={status_counts['cancelled']}, scheduled={status_counts['scheduled']}, "
            f"in_progress={status_counts['in_progress']}, attention={status_counts['attention']}"
        )

    # -- output ---------------------------------------------------------------

    def _print_summary(self, counts: SeedCounts, credentials: dict) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Created:"))
        self.stdout.write(f"  - Admins: {counts.admins}")
        self.stdout.write(f"  - Teachers: {counts.teachers}")
        self.stdout.write(f"  - Subjects: {counts.subjects}")
        self.stdout.write(f"  - Courses: {counts.courses}")
        self.stdout.write(f"  - CourseLessonPlans: {counts.lesson_plans}")
        self.stdout.write(f"  - Rooms: {counts.rooms}")
        self.stdout.write(f"  - Students: {counts.students}")
        self.stdout.write(f"  - Groups: {counts.groups}")
        self.stdout.write(f"  - Programs (GroupTeacher): {GroupTeacher.objects.count()}")
        self.stdout.write(f"  - Schedules (GroupSchedule): {counts.schedules}")
        self.stdout.write(f"  - Lessons: {counts.lessons}")
        self.stdout.write(f"  - Attendance: {counts.attendance}")
        self.stdout.write(f"  - Homework: {counts.homework}")
        self.stdout.write(f"  - HomeworkResults: {counts.homework_results}")

        if counts.edge_cases:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Edge cases seeded for UI testing:"))
            for case in counts.edge_cases:
                self.stdout.write(f"  - {case}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Development-only login credentials:"))
        self.stdout.write(f"  Password for every seeded account: {DEV_PASSWORD}")
        self.stdout.write(f"  Admin usernames: {', '.join(credentials['admins'])}")
        self.stdout.write(
            f"  Teacher usernames (first 5 of {credentials['teachers_total']}): "
            f"{', '.join(credentials['teachers_sample'])}"
        )
        self.stdout.write(
            self.style.WARNING(
                "These are development-only fixtures — never used or reused in production."
            )
        )

    # -- small helpers ---------------------------------------------------------

    @property
    def _rooms_cache(self) -> list[Room]:
        if not hasattr(self, "_rooms_cache_value"):
            self._rooms_cache_value = list(Room.objects.filter(is_active=True))
        return self._rooms_cache_value

    @staticmethod
    def _phone(seed_number: int) -> str:
        return f"+996{seed_number % 1_000_000_000:09d}"
