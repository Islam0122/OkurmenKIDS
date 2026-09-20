"""Generates a large, realistic, fully-connected MOCK dataset for exercising
the Reports/Analytics/KPI system over June-September 2026.

Every model used here is a real, existing project model — nothing new is
introduced. In particular: **this project has no Payment/Refund/billing
model anywhere** (see the docstring on models.StudentStatusEvent, which
explicitly documents refusing to add a fabricated `refund_amount` field
because "this project has no payment/billing model anywhere ... a
refund_amount field here would just be a fabricated financial record with
nothing real behind it"). This command follows that same rule: it never
invents Payment/Refund/Revenue records or fields. Every "Gross/Net Revenue"
figure a report might show for the generated period is `None`/"—", exactly
as it already is for every other dataset in this project — see
services.academy_monthly_report's own docstring for the same reasoning
about a lesson "reschedule" status.

Scope, deliberately: Students, Teachers, Subjects, Courses,
CourseLessonPlan, Rooms, Groups, GroupSchedule, GroupTeacher (derived
automatically by GroupSchedule.save()), GroupTeacherLessonPlan, Lesson,
Homework, HomeworkResult, Attendance, StudentStatusEvent,
MonthlyTeacherReport, AcademyMonthlyReport. KPI/attendance/revenue-shaped
figures are never written directly onto a report row — every number the
Reports UI shows is computed live from this generated data by the existing
services (services.monthly_report / services.academy_monthly_report), the
same way it would be for a real academy.

Every generated Lesson's date is capped at `--end-date` (2026-09-20 by
default) — this command never creates a Lesson dated after that cutoff, so
every generated Lesson has already "happened" by the report snapshot date
and is always COMPLETED or CANCELLED, never SCHEDULED/IN_PROGRESS (spec:
"не создавай завершённые уроки в будущем" / "не создавай записи в будущем
после 20 сентября 2026 года").

Automatic lesson generation (see academy/signals.py) is deliberately
deferred on every Group/GroupSchedule save here via the same
`_defer_schedule_sync` flag the Group Admin page's own bulk saves use (see
signals.py's module docstring) — this command builds every Lesson itself,
with full control over historical dates/status/attendance, rather than
racing the signal-driven generator (which only knows how to walk forward
from `group.start_date` with no upper cutoff).

Idempotent by construction: every catalogue object (Subject/Course/Room/
Teacher/Group/GroupSchedule) is matched by its natural unique key before
being created, and every high-volume table (Lesson/Attendance/Homework/
HomeworkResult) is written with `bulk_create(ignore_conflicts=True)` against
the model's own unique constraints — so re-running this command never
duplicates data. A fixed-seed RNG (`--seed`) makes a fresh run's "random"
figures reproducible.

Every mock object is tagged so `--clear` can remove *only* what this
command created, never real data: Room/Course/Group names are prefixed
"[MOCK]" and teacher usernames/emails live under the mock.* namespace — the
same convention `seed_demo_data.py` already uses with "[DEMO]"/demo.*.
Subjects are shared catalogue data (spec: reuse an existing Subject rather
than duplicating it) and are never deleted by `--clear`, matching
`clear_demo_data.py`'s own reasoning.
"""
from __future__ import annotations

import datetime as dt
import os
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academy.models import (
    AcademyMonthlyReport,
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
    MonthlyTeacherReport,
    Room,
    Student,
    StudentStatusEvent,
)
from apps.academy.services.academy_monthly_report import compute_academy_monthly_stats
from apps.users.models import Subject, User
from apps.users.services import create_teacher

MOCK_ADMIN_USERNAME = "mock_admin"
MOCK_ADMIN_EMAIL = "mock_admin@mock.okurmenkids.local"
MOCK_TEACHER_PASSWORD = "MockTeacher123!"  # nosec: mock-data fixture password, never used in production
MOCK_NAME_PREFIX = "[MOCK]"
MOCK_TEACHER_USERNAME_PREFIX = "mock_teacher_"
MOCK_TEACHER_EMAIL_DOMAIN = "mock.okurmenkids.local"

DEFAULT_SEED = 2026
DEFAULT_STUDENTS = 250
DEFAULT_TEACHERS = 20
DEFAULT_GROUPS = 30
DEFAULT_LESSONS_TARGET = 500
DEFAULT_START_DATE = dt.date(2026, 6, 1)
DEFAULT_END_DATE = dt.date(2026, 9, 20)

# ---------------------------------------------------------------------------
# Static catalogue data
# ---------------------------------------------------------------------------

SUBJECT_NAMES = [
    "Python", "HTML/CSS/JS", "React", "FastAPI",
    "CyberSecurity", "English", "Soft Skills", "Scratch",
]

# Which second subject pairs naturally with a teacher's primary one, for a
# realistic "this teacher also covers a related subject" ~40% of the time.
SUBJECT_PAIRS = {
    "Python": "FastAPI",
    "FastAPI": "Python",
    "HTML/CSS/JS": "React",
    "React": "HTML/CSS/JS",
    "English": "Soft Skills",
    "Soft Skills": "English",
    "Scratch": "Soft Skills",
    "CyberSecurity": "Python",
}

# name -> (subjects it covers, template lesson count = CourseLessonPlan rows)
COURSE_DEFS = [
    ("Python Junior", ["Python"], 20),
    ("Python PRO", ["Python", "FastAPI"], 28),
    ("FastAPI Backend", ["FastAPI", "Python"], 24),
    ("Frontend Beginner (HTML/CSS/JS)", ["HTML/CSS/JS"], 20),
    ("Frontend PRO (React)", ["HTML/CSS/JS", "React"], 28),
    ("CyberSecurity Basics", ["CyberSecurity"], 18),
    ("English Starter", ["English"], 24),
    ("English Advanced", ["English", "Soft Skills"], 24),
    ("Soft Skills for Teens", ["Soft Skills"], 16),
    ("Scratch for Kids", ["Scratch"], 18),
]

TOPIC_PHRASES = {
    "Python": [
        "Введение в Python и установка окружения", "Переменные, типы данных и операторы",
        "Условные конструкции if/elif/else", "Циклы for и while", "Списки и работа с ними",
        "Кортежи и множества", "Словари и работа с данными", "Функции и аргументы",
        "Рекурсия", "Работа со строками", "Файлы: чтение и запись", "Обработка исключений",
        "Модули и пакеты", "Введение в ООП: классы и объекты", "Наследование и полиморфизм",
        "Работа с библиотекой requests", "Основы работы с базами данных",
        "Мини-проект: консольное приложение", "Тестирование кода", "Итоговый проект",
    ],
    "FastAPI": [
        "Введение в FastAPI и ASGI", "Роутинг и path-параметры", "Query-параметры и валидация",
        "Pydantic-модели", "Работа с базой данных (ORM)", "Аутентификация и JWT",
        "Middleware и CORS", "Асинхронные обработчики", "Загрузка файлов", "Обработка ошибок",
        "Тестирование API", "Документация Swagger/OpenAPI", "Деплой FastAPI-приложения",
        "Итоговый проект: REST API",
    ],
    "HTML/CSS/JS": [
        "Структура HTML-документа", "Семантическая вёрстка", "Основы CSS: селекторы и свойства",
        "Flexbox", "CSS Grid", "Адаптивная вёрстка", "Основы JavaScript: переменные и типы",
        "Функции и события", "Работа с DOM", "Формы и валидация",
        "Fetch API и работа с сервером", "Анимации на CSS/JS", "Мини-проект: лендинг",
        "Итоговый проект: интерактивная страница",
    ],
    "React": [
        "Введение в React и JSX", "Компоненты и props", "State и хуки useState",
        "useEffect и жизненный цикл", "Обработка событий", "Списки и ключи", "Формы в React",
        "React Router", "Работа с API (fetch/axios)", "Context API", "Управление состоянием",
        "Оптимизация рендеринга", "Итоговый проект: SPA-приложение",
    ],
    "CyberSecurity": [
        "Введение в кибербезопасность", "Основы сетевой безопасности", "Пароли и аутентификация",
        "Фишинг и социальная инженерия", "Вредоносное ПО: виды и защита", "Шифрование данных",
        "Безопасность веб-приложений (OWASP)", "VPN и защищённые соединения",
        "Резервное копирование данных", "Практикум: анализ уязвимостей",
        "Итоговый проект: план защиты системы",
    ],
    "English": [
        "Greetings and introductions", "Family and friends", "Daily routines", "Food and drinks",
        "Hobbies and free time", "Travel and places", "Grammar: Present Simple",
        "Grammar: Past Simple", "Grammar: Future forms", "Speaking practice: dialogues",
        "Listening comprehension", "Writing a short story", "Reading comprehension",
        "Vocabulary building", "Final review and speaking test",
    ],
    "Soft Skills": [
        "Эффективная коммуникация", "Работа в команде", "Тайм-менеджмент",
        "Публичные выступления", "Постановка целей", "Решение конфликтов",
        "Критическое мышление", "Эмоциональный интеллект", "Лидерство", "Обратная связь",
        "Презентационные навыки", "Итоговый проект: групповая презентация",
    ],
    "Scratch": [
        "Знакомство со Scratch", "Спрайты и костюмы", "Движение и координаты",
        "Циклы в Scratch", "Условия и события", "Переменные в Scratch", "Звук и музыка",
        "Создание простой игры", "Анимация персонажа", "Взаимодействие объектов",
        "Итоговый проект: своя игра",
    ],
}

CANCELLATION_REASONS = [
    "Тренер заболел", "Праздничный день", "Технические проблемы в аудитории",
    "Низкая явка группы", "Форс-мажор у тренера",
]

FIRST_NAMES_KG = [
    "Алихан", "Азамат", "Айжан", "Мээрим", "Нурбек", "Эльдар", "Алина", "Данияр",
    "Айгерим", "Бекзат", "Нурайым", "Жаныл", "Максат", "Аида", "Тимур", "Гулназ",
    "Эрлан", "Салтанат", "Уланбек", "Динара", "Марат", "Асель", "Руслан", "Жамиля",
    "Канат", "Айпери", "Бакыт", "Нурсултан", "Замира", "Абдылда", "Медер", "Нургуль",
    "Талант", "Айдана", "Бекболот", "Чолпон", "Сезим", "Арген", "Гулайым", "Омурбек",
    "Бекнур", "Айсулуу", "Нурлан", "Кундуз", "Максатбек", "Жибек", "Айбек", "Сымбат",
]

LAST_NAMES_KG = [
    "Асанов", "Асанова", "Осмонов", "Осмонова", "Тологонов", "Тологонова",
    "Жумабеков", "Жумабекова", "Мамытов", "Мамытова", "Каримов", "Каримова",
    "Сыдыков", "Сыдыкова", "Абдыракманов", "Абдыракманова", "Нурматов", "Нурматова",
    "Сатыбалдиев", "Сатыбалдиева", "Токтогулов", "Токтогулова", "Бекова", "Беков",
    "Исаков", "Исакова", "Молдалиев", "Молдалиева", "Турсунов", "Турсунова",
    "Кадыров", "Кадырова", "Байгазиев", "Байгазиева", "Эсенов", "Эсенова",
]

FIRST_NAMES_INTL = [
    "Alexander", "Maria", "John", "Elizabeth", "David", "Anna", "Kevin", "Sophia",
    "Michael", "Victoria", "Daniel", "Ekaterina", "Nikita", "Olga", "Ivan", "Elena",
    "Andrei", "Maxim", "Polina", "Kristina", "Arthur", "Vlad", "Sergey", "Natalia",
    "Denis", "Alina", "Roman", "Yulia", "Pavel", "Veronika",
]

LAST_NAMES_INTL = [
    "Petrov", "Petrova", "Ivanov", "Ivanova", "Sokolov", "Sokolova", "Volkov", "Volkova",
    "Smirnov", "Smirnova", "Kuznetsov", "Kuznetsova", "Popov", "Popova",
    "Vasiliev", "Vasilieva", "Smith", "Johnson", "Brown", "Clark", "Miller", "Davis",
    "Wilson", "Moore", "Taylor", "Anderson",
]

REASON_WEIGHTS = {
    StudentStatusEvent.Reason.NO_INTEREST: 15,
    StudentStatusEvent.Reason.DISLIKED_TEACHER: 5,
    StudentStatusEvent.Reason.FAMILY_CIRCUMSTANCES: 15,
    StudentStatusEvent.Reason.WILL_CONTINUE_LATER: 10,
    StudentStatusEvent.Reason.FINANCIAL_ISSUES: 15,
    StudentStatusEvent.Reason.NOT_ENOUGH_TIME: 15,
    StudentStatusEvent.Reason.RELOCATION: 8,
    StudentStatusEvent.Reason.HEALTH: 7,
    StudentStatusEvent.Reason.CHANGED_PLANS: 8,
    StudentStatusEvent.Reason.OTHER: 2,
}

TIME_SLOTS = [
    (dt.time(9, 0), dt.time(10, 30)),
    (dt.time(10, 45), dt.time(12, 15)),
    (dt.time(13, 0), dt.time(14, 30)),
    (dt.time(14, 45), dt.time(16, 15)),
    (dt.time(16, 30), dt.time(18, 0)),
    (dt.time(18, 15), dt.time(19, 45)),
]

WEEKDAY_POOL = ["mon", "tue", "wed", "thu", "fri", "sat"]


def _weighted_choice(rng: random.Random, weights: dict):
    keys = list(weights.keys())
    values = list(weights.values())
    return rng.choices(keys, weights=values, k=1)[0]


def _random_date_between(rng: random.Random, start: dt.date, end: dt.date) -> dt.date:
    if end <= start:
        return start
    offset = rng.randint(0, (end - start).days)
    return start + dt.timedelta(days=offset)


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def _aware(date: dt.date, time_: dt.time = dt.time(12, 0)):
    return timezone.make_aware(dt.datetime.combine(date, time_))


def _month_iter(start: dt.date, end: dt.date) -> list[tuple[int, int]]:
    months = []
    cursor = start.replace(day=1)
    while cursor <= end:
        months.append((cursor.year, cursor.month))
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return months


class Command(BaseCommand):
    help = (
        "Generates a large, realistic, fully-connected MOCK dataset (teachers, "
        "subjects, courses, groups, students, lessons, attendance, homework, "
        "student lifecycle events, monthly reports) for testing the Reports/"
        "Analytics/KPI system over a date range (June-September 2026 by "
        "default). This project has no Payment/Refund model, so none is "
        "fabricated here (see module docstring). Development/testing only — "
        "refuses to run when DJANGO_ENV=production. Idempotent: safe to run "
        "more than once."
    )

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete the MOCK dataset this command owns.")
        parser.add_argument("--confirm", action="store_true", help="Required together with --clear.")
        parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RNG seed for reproducible data.")
        parser.add_argument("--students", type=int, default=DEFAULT_STUDENTS, help="Total students to generate.")
        parser.add_argument("--teachers", type=int, default=DEFAULT_TEACHERS, help="Total teachers to generate.")
        parser.add_argument("--groups", type=int, default=DEFAULT_GROUPS, help="Total groups to generate.")
        parser.add_argument(
            "--lessons", type=int, default=DEFAULT_LESSONS_TARGET,
            help="Soft target for total lessons — influences weekly session frequency.",
        )
        parser.add_argument("--start-date", type=str, default=DEFAULT_START_DATE.isoformat())
        parser.add_argument("--end-date", type=str, default=DEFAULT_END_DATE.isoformat())

    def handle(self, *args, **options):
        env = os.environ.get("DJANGO_ENV", "development")
        if env == "production":
            raise CommandError(
                "Refusing to run: DJANGO_ENV=production. generate_mock_data never "
                "creates mock data in production, and never opens a production database connection."
            )

        if options["clear"]:
            if not options["confirm"]:
                raise CommandError(
                    "This deletes the OkurmenKIDS MOCK dataset (mock teachers, groups, "
                    "students, lessons, attendance, homework, reports). Re-run with --confirm to proceed."
                )
            self._clear()
            return

        try:
            start_date = dt.date.fromisoformat(options["start_date"])
            end_date = dt.date.fromisoformat(options["end_date"])
        except ValueError as exc:
            raise CommandError(f"Invalid --start-date/--end-date: {exc}") from exc
        if end_date <= start_date:
            raise CommandError("--end-date must be after --start-date.")

        self.stdout.write(self.style.WARNING(
            f"=== OKURMENKIDS MOCK DATA GENERATOR (DJANGO_ENV={env}) — not for production use ==="
        ))

        self.rng = random.Random(options["seed"])
        self._generate(options, start_date, end_date)

    # ------------------------------------------------------------------
    # --clear
    # ------------------------------------------------------------------

    @transaction.atomic
    def _clear(self) -> None:
        w = self.stdout.write
        mock_teacher_usernames = list(
            User.objects.filter(username__startswith=MOCK_TEACHER_USERNAME_PREFIX).values_list("username", flat=True)
        )

        lesson_qs = Lesson.objects.filter(group__name__startswith=MOCK_NAME_PREFIX)
        counts = {
            "monthly teacher reports": MonthlyTeacherReport.objects.filter(
                teacher__user__username__in=mock_teacher_usernames
            ).count(),
            "students": Student.objects.filter(group__name__startswith=MOCK_NAME_PREFIX).count(),
            "attendance": Attendance.objects.filter(lesson__in=lesson_qs).count(),
            "homework results": HomeworkResult.objects.filter(homework__lesson__in=lesson_qs).count(),
            "homework": Homework.objects.filter(lesson__in=lesson_qs).count(),
            "lessons": lesson_qs.count(),
            "groups": Group.objects.filter(name__startswith=MOCK_NAME_PREFIX).count(),
            "rooms": Room.objects.filter(name__startswith=MOCK_NAME_PREFIX).count(),
            "courses": Course.objects.filter(name__startswith=MOCK_NAME_PREFIX).count(),
            "teacher users": len(mock_teacher_usernames),
        }

        MonthlyTeacherReport.objects.filter(teacher__user__username__in=mock_teacher_usernames).delete()
        # Student.group is SET_NULL, so mock Students must be deleted explicitly
        # before their Group (cascades StudentStatusEvent too).
        Student.objects.filter(group__name__startswith=MOCK_NAME_PREFIX).delete()
        # Cascades GroupSchedule, GroupTeacher, GroupTeacherLessonPlan, Lesson,
        # Attendance, Homework, HomeworkResult.
        Group.objects.filter(name__startswith=MOCK_NAME_PREFIX).delete()
        Room.objects.filter(name__startswith=MOCK_NAME_PREFIX).delete()
        # Safe now — every GroupTeacher (PROTECTs Teacher) referencing a mock
        # teacher was already removed via the Group cascade above.
        Course.objects.filter(name__startswith=MOCK_NAME_PREFIX).delete()
        User.objects.filter(username__in=mock_teacher_usernames).delete()

        admin_qs = User.objects.filter(username=MOCK_ADMIN_USERNAME, email=MOCK_ADMIN_EMAIL)
        admin_deleted = admin_qs.count()
        admin_qs.delete()

        for label, count in counts.items():
            w(f"Deleted {label}: {count}")
        w(f"Deleted mock admin user: {admin_deleted}")
        w(self.style.SUCCESS(
            "MOCK dataset cleared. Subjects and AcademyMonthlyReport rows were left "
            "untouched (shared catalogue / whole-academy reporting data)."
        ))

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    @transaction.atomic
    def _generate(self, options: dict, start_date: dt.date, end_date: dt.date) -> None:
        admin = self._get_or_create_admin()
        subjects = self._get_or_create_subjects()
        courses = self._get_or_create_courses(subjects)
        rooms = self._get_or_create_rooms()
        teachers = self._create_teachers(options["teachers"], subjects)

        frequency_bias = min(2.0, max(0.5, options["lessons"] / DEFAULT_LESSONS_TARGET))

        groups = self._create_groups(options["groups"], courses, start_date, end_date)
        programs = self._create_teaching_programs(groups, teachers, subjects, rooms, frequency_bias, end_date, admin)
        students_by_group = self._create_students(groups, options["students"], start_date, end_date)
        attendance_count, homework_result_count = self._create_attendance_and_homework(groups, students_by_group)

        months = _month_iter(start_date, end_date)
        teacher_reports = self._create_teacher_reports(teachers, months)
        academy_reports = self._create_academy_reports(months)

        self._print_summary(
            admin=admin, subjects=subjects, courses=courses, rooms=rooms, teachers=teachers,
            groups=groups, programs=programs, students_by_group=students_by_group,
            attendance_count=attendance_count, homework_result_count=homework_result_count,
            teacher_reports=teacher_reports, academy_reports=academy_reports, months=months,
        )

    # -- Admin / catalogue -------------------------------------------------

    def _get_or_create_admin(self) -> User:
        user, _ = User.objects.get_or_create(
            username=MOCK_ADMIN_USERNAME,
            defaults={
                "email": MOCK_ADMIN_EMAIL,
                "first_name": "Mock",
                "last_name": "Admin",
                "role": User.Role.ADMIN,
                "is_verified": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        return user

    def _get_or_create_subjects(self) -> dict[str, Subject]:
        result = {}
        for name in SUBJECT_NAMES:
            subject, _ = Subject.objects.get_or_create(
                name=name, defaults={"description": f"Направление «{name}».", "is_active": True}
            )
            result[name] = subject
        return result

    def _get_or_create_courses(self, subjects: dict[str, Subject]) -> list[dict]:
        courses = []
        for name, subject_names, lesson_count in COURSE_DEFS:
            full_name = f"{MOCK_NAME_PREFIX} {name}"
            course, created = Course.objects.get_or_create(
                name=full_name,
                defaults={"count_lesson": lesson_count, "description": f"Учебный курс «{name}»."},
            )
            if created:
                course.subjects.set([subjects[s] for s in subject_names])
                plans = []
                phrases_by_subject = {s: TOPIC_PHRASES[s] for s in subject_names}
                for n in range(1, lesson_count + 1):
                    subject_name = subject_names[(n - 1) % len(subject_names)]
                    phrases = phrases_by_subject[subject_name]
                    topic = f"Занятие {n}: {phrases[(n - 1) % len(phrases)]}"
                    plans.append(CourseLessonPlan(
                        course=course, lesson_number=n, subject=subjects[subject_name], topic=topic,
                        homework_title=f"Домашнее задание к занятию {n}" if self.rng.random() < 0.8 else "",
                        homework_description="Практическое задание по теме занятия." if self.rng.random() < 0.8 else "",
                    ))
                CourseLessonPlan.objects.bulk_create(plans, ignore_conflicts=True)
            courses.append({"course": course, "subject_names": subject_names})
        return courses

    def _get_or_create_rooms(self) -> list[Room]:
        rooms = []
        for n in range(1, 7):
            room, _ = Room.objects.get_or_create(
                name=f"{MOCK_NAME_PREFIX} Кабинет {n}",
                defaults={"capacity": 16, "description": "Учебная аудитория."},
            )
            rooms.append(room)
        return rooms

    # -- Teachers ------------------------------------------------------

    def _create_teachers(self, count: int, subjects: dict[str, Subject]) -> list[dict]:
        name_pairs = [(f, l) for f in FIRST_NAMES_KG for l in LAST_NAMES_KG]
        name_pairs += [(f, l) for f in FIRST_NAMES_INTL for l in LAST_NAMES_INTL]
        self.rng.shuffle(name_pairs)
        names = name_pairs[:count]

        teachers = []
        for index in range(count):
            first_name, last_name = names[index % len(names)]
            username = f"{MOCK_TEACHER_USERNAME_PREFIX}{index + 1:02d}"
            primary_subject = SUBJECT_NAMES[index % len(SUBJECT_NAMES)]
            subject_list = [primary_subject]
            secondary = SUBJECT_PAIRS.get(primary_subject)
            if secondary and self.rng.random() < 0.4:
                subject_list.append(secondary)

            attendance_weights = {
                "present": self.rng.randint(78, 93),
                "late": self.rng.randint(3, 9),
                "absent": self.rng.randint(3, 12),
                "excused": self.rng.randint(1, 3),
            }
            homework_weights = {
                "checked": self.rng.randint(65, 85),
                "submitted": self.rng.randint(5, 10),
                "late": self.rng.randint(4, 10),
                "not_submitted": self.rng.randint(6, 14),
            }
            score_weights = {n: w for n, w in zip(range(6, 11), self.rng.sample(range(10, 41), 5))}
            cancel_rate = self.rng.uniform(0.02, 0.12)

            existing = User.objects.filter(username=username).first()
            if existing is not None:
                teacher = existing.teacher_profile
            else:
                result = create_teacher(
                    username=username,
                    email=f"{username}@{MOCK_TEACHER_EMAIL_DOMAIN}",
                    first_name=first_name,
                    last_name=last_name,
                    password=MOCK_TEACHER_PASSWORD,
                    position=f"Тренер по направлению {primary_subject}",
                    experience_years=self.rng.randint(1, 12),
                    hire_date=_random_date_between(self.rng, dt.date(2019, 1, 1), dt.date(2026, 5, 1)),
                    bio=f"Ведёт направление «{primary_subject}» в OkurmenKIDS.",
                    send_email=False,
                )
                teacher = result.teacher
            teacher.subjects.set([subjects[s] for s in subject_list])

            teachers.append({
                "teacher": teacher, "subjects": subject_list,
                "attendance_weights": attendance_weights, "homework_weights": homework_weights,
                "score_weights": score_weights, "cancel_rate": cancel_rate,
            })

        self._teacher_profiles = {entry["teacher"].id: entry for entry in teachers}
        return teachers

    # -- Groups ----------------------------------------------------------

    def _pick_group_start_date(self, start_cap: dt.date, end_cap: dt.date) -> dt.date:
        buckets = [
            ("early", 0.35, dt.date(2026, 1, 15), start_cap - dt.timedelta(days=3)),
            ("first_month", 0.20, start_cap, start_cap + dt.timedelta(days=24)),
            ("second_month", 0.15, start_cap + dt.timedelta(days=30), start_cap + dt.timedelta(days=54)),
            ("third_month", 0.20, start_cap + dt.timedelta(days=61), start_cap + dt.timedelta(days=85)),
            ("late", 0.10, end_cap - dt.timedelta(days=18), end_cap - dt.timedelta(days=8)),
        ]
        keys = [b[0] for b in buckets]
        weights = [b[1] for b in buckets]
        chosen = buckets[keys.index(self.rng.choices(keys, weights=weights, k=1)[0])]
        low, high = chosen[2], chosen[3]
        if high < low:
            low, high = high, low
        low = max(low, dt.date(2026, 1, 1))
        high = min(high, end_cap - dt.timedelta(days=1))
        if high < low:
            high = low
        return _random_date_between(self.rng, low, high)

    def _create_groups(self, count: int, courses: list[dict], start_cap: dt.date, end_cap: dt.date) -> list[dict]:
        status_pool = (
            [Group.Status.ACTIVE] * 70 + [Group.Status.COMPLETED] * 12
            + [Group.Status.PAUSED] * 10 + [Group.Status.CANCELLED] * 8
        )
        groups = []
        for index in range(count):
            course_entry = courses[index % len(courses)]
            course = course_entry["course"]
            name = f"{MOCK_NAME_PREFIX} {course.name.replace(MOCK_NAME_PREFIX, '').strip()} — Группа {index + 1:02d}"

            existing = Group.objects.filter(name=name).first()
            if existing is not None:
                groups.append({"group": existing, "course_entry": course_entry, "status": existing.status})
                continue

            group_start = self._pick_group_start_date(start_cap, end_cap)
            status = self.rng.choice(status_pool)

            group_end = None
            effective_end = end_cap
            if status == Group.Status.COMPLETED:
                min_end = group_start + dt.timedelta(days=45)
                if min_end >= end_cap:
                    status = Group.Status.ACTIVE
                else:
                    group_end = _random_date_between(self.rng, min_end, end_cap - dt.timedelta(days=1))
                    effective_end = group_end
            elif status == Group.Status.CANCELLED:
                max_end = min(group_start + dt.timedelta(days=20), end_cap - dt.timedelta(days=1))
                if max_end <= group_start:
                    status = Group.Status.ACTIVE
                else:
                    group_end = _random_date_between(self.rng, group_start + dt.timedelta(days=3), max_end)
                    effective_end = group_end
            elif status == Group.Status.PAUSED:
                min_pause = group_start + dt.timedelta(days=21)
                if min_pause >= end_cap:
                    status = Group.Status.ACTIVE
                else:
                    effective_end = _random_date_between(self.rng, min_pause, end_cap - dt.timedelta(days=1))
                    # group.end_date stays None: a paused group's real end is unknown.

            student_target = self.rng.randint(6, 13)
            group = Group(
                name=name, course=course, start_date=group_start, end_date=group_end,
                max_students=student_target + self.rng.randint(1, 3), status=status,
                description=f"Группа курса «{course.name}».",
            )
            group._defer_schedule_sync = True
            group.save()

            groups.append({
                "group": group, "course_entry": course_entry, "status": status,
                "effective_end": effective_end, "student_target": student_target,
            })
        return groups

    # -- Teaching programs (GroupSchedule/GroupTeacher/plans/lessons/homework) --

    def _find_free_slot(self, day_pool, teacher_id, room_id, group_id, busy):
        days = list(day_pool)
        self.rng.shuffle(days)
        for day in days:
            slots = list(TIME_SLOTS)
            self.rng.shuffle(slots)
            for start, end in slots:
                if any(_overlaps(start, end, s, e) for s, e in busy["teacher"].get((teacher_id, day), [])):
                    continue
                if any(_overlaps(start, end, s, e) for s, e in busy["room"].get((room_id, day), [])):
                    continue
                if any(_overlaps(start, end, s, e) for s, e in busy["group"].get((group_id, day), [])):
                    continue
                return day, start, end
        return None

    def _mark_busy(self, busy, teacher_id, room_id, group_id, day, start, end):
        busy["teacher"].setdefault((teacher_id, day), []).append((start, end))
        busy["room"].setdefault((room_id, day), []).append((start, end))
        busy["group"].setdefault((group_id, day), []).append((start, end))

    def _create_teaching_programs(
        self, groups: list[dict], teachers: list[dict], subjects: dict[str, Subject],
        rooms: list[Room], frequency_bias: float, cap: dt.date, admin: User,
    ) -> list[dict]:
        teachers_by_subject: dict[str, list[dict]] = {name: [] for name in SUBJECT_NAMES}
        for entry in teachers:
            for subject_name in entry["subjects"]:
                teachers_by_subject[subject_name].append(entry)
        rotation = {name: 0 for name in SUBJECT_NAMES}
        room_rotation = 0

        busy = {"teacher": {}, "room": {}, "group": {}}
        programs: list[dict] = []

        for group_entry in groups:
            group = group_entry["group"]
            if "effective_end" not in group_entry:
                # Pre-existing group from a previous run — nothing new to generate.
                continue
            effective_end = group_entry["effective_end"]
            subject_names = group_entry["course_entry"]["subject_names"]

            for subject_name in subject_names:
                candidates = teachers_by_subject.get(subject_name) or teachers
                teacher_entry = candidates[rotation[subject_name] % len(candidates)]
                rotation[subject_name] += 1
                teacher = teacher_entry["teacher"]
                subject = subjects[subject_name]

                room = rooms[room_rotation % len(rooms)]
                room_rotation += 1

                weekday_count = 3 if frequency_bias >= 1.3 else (2 if frequency_bias >= 0.8 else 1)
                weekday_count = min(weekday_count + (1 if len(subject_names) == 1 else 0), 3)

                chosen_days = []
                for _ in range(weekday_count):
                    slot = self._find_free_slot(WEEKDAY_POOL, teacher.id, room.id, group.id, busy)
                    if slot is None:
                        break
                    day, start, end = slot
                    self._mark_busy(busy, teacher.id, room.id, group.id, day, start, end)
                    chosen_days.append((day, start, end))

                if not chosen_days:
                    continue

                group_teacher = None
                for day, start, end in chosen_days:
                    existing_schedule = GroupSchedule.objects.filter(
                        group=group, teacher=teacher, subject=subject, day_of_week=day,
                    ).first()
                    if existing_schedule is not None:
                        group_teacher = existing_schedule.group_teacher
                        continue
                    schedule = GroupSchedule(
                        group=group, teacher=teacher, subject=subject, day_of_week=day,
                        start_time=start, end_time=end, room=room, is_active=True,
                    )
                    schedule._defer_schedule_sync = True
                    schedule.save()
                    group_teacher = schedule.group_teacher

                if group_teacher is None:
                    continue

                allowed_weekday_indices = {_weekday_index(d) for d, _, _ in chosen_days}
                dates = sorted(
                    group.start_date + dt.timedelta(days=offset)
                    for offset in range((effective_end - group.start_date).days + 1)
                    if (group.start_date + dt.timedelta(days=offset)).weekday() in allowed_weekday_indices
                )

                if not dates:
                    continue

                existing_plan_count = group_teacher.lesson_plans.count()
                plan_rows = []
                phrases = TOPIC_PHRASES[subject_name]
                for n in range(existing_plan_count + 1, len(dates) + 1):
                    topic = f"Занятие {n}: {phrases[(n - 1) % len(phrases)]}"
                    plan_rows.append(GroupTeacherLessonPlan(
                        group_teacher=group_teacher, lesson_number=n, topic=topic,
                        homework_title=f"Домашнее задание к занятию {n}" if self.rng.random() < 0.8 else "",
                        homework_description="Практическое задание по теме занятия." if self.rng.random() < 0.8 else "",
                    ))
                if plan_rows:
                    GroupTeacherLessonPlan.objects.bulk_create(plan_rows, ignore_conflicts=True)

                plans = list(group_teacher.lesson_plans.order_by("lesson_number"))
                schedule_for_lesson = GroupSchedule.objects.filter(group_teacher=group_teacher).first()

                lessons = []
                cancel_rate = teacher_entry["cancel_rate"]
                for n, date in enumerate(dates[:len(plans)], start=1):
                    plan = plans[n - 1]
                    is_cancelled = date < cap and self.rng.random() < cancel_rate
                    status = Lesson.Status.CANCELLED if is_cancelled else Lesson.Status.COMPLETED
                    day_slot = next((s for d, s, e in chosen_days if _weekday_index(d) == date.weekday()), None)
                    end_slot = next((e for d, s, e in chosen_days if _weekday_index(d) == date.weekday()), None)
                    start_time = day_slot or dt.time(9, 0)
                    end_time = end_slot or dt.time(10, 30)
                    lesson = Lesson(
                        group=group, group_teacher=group_teacher, individual_plan=plan,
                        schedule=schedule_for_lesson, teacher=teacher, subject=subject,
                        lesson_number=plan.lesson_number, date=date, start_time=start_time, end_time=end_time,
                        room=room, topic=plan.topic, description=plan.description,
                        status=status,
                        cancellation_reason=self.rng.choice(CANCELLATION_REASONS) if is_cancelled else "",
                        homework_not_required=not bool(plan.homework_title) or is_cancelled,
                        started_at=None if is_cancelled else _aware(date, start_time),
                        completed_at=None if is_cancelled else _aware(date, end_time),
                        completed_by=None if is_cancelled else admin,
                    )
                    lessons.append(lesson)

                if lessons:
                    Lesson.objects.bulk_create(lessons, ignore_conflicts=True)

                saved_lessons = list(
                    Lesson.objects.filter(group_teacher=group_teacher).order_by("lesson_number")
                )
                homeworks = []
                for lesson in saved_lessons:
                    if lesson.status == Lesson.Status.COMPLETED and not lesson.homework_not_required:
                        plan = next((p for p in plans if p.lesson_number == lesson.lesson_number), None)
                        if plan and plan.homework_title:
                            homeworks.append(Homework(
                                lesson=lesson, title=plan.homework_title,
                                description=plan.homework_description,
                                deadline=lesson.date + dt.timedelta(days=5),
                            ))
                if homeworks:
                    Homework.objects.bulk_create(homeworks, ignore_conflicts=True)

                programs.append({
                    "group": group, "group_teacher": group_teacher, "teacher_entry": teacher_entry,
                    "subject_name": subject_name, "lesson_count": len(lessons),
                })

        return programs

    # -- Students ------------------------------------------------------

    def _sample_names(self, count: int):
        kg_ratio = 0.7
        kg_count = round(count * kg_ratio)
        intl_count = count - kg_count
        kg_pool = [(f, l) for f in FIRST_NAMES_KG for l in LAST_NAMES_KG]
        intl_pool = [(f, l) for f in FIRST_NAMES_INTL for l in LAST_NAMES_INTL]
        self.rng.shuffle(kg_pool)
        self.rng.shuffle(intl_pool)
        names = kg_pool[:kg_count] + intl_pool[:intl_count]
        self.rng.shuffle(names)
        return names

    def _random_phone(self) -> str:
        prefix = self.rng.choice(["550", "555", "700", "770", "990", "500"])
        return f"+996 {prefix} {self.rng.randint(100, 999)} {self.rng.randint(100, 999)}"

    def _status_weights_for_group(self, status: str) -> dict:
        if status == Group.Status.COMPLETED:
            return {"active": 0, "completed": 70, "withdrawn": 20, "paused": 10}
        if status == Group.Status.CANCELLED:
            return {"active": 0, "completed": 0, "withdrawn": 90, "paused": 10}
        if status == Group.Status.PAUSED:
            return {"active": 30, "completed": 0, "withdrawn": 20, "paused": 50}
        return {"active": 78, "completed": 8, "withdrawn": 9, "paused": 5}

    def _create_students(
        self, groups: list[dict], total_target: int, start_cap: dt.date, end_cap: dt.date,
    ) -> dict[int, list[dict]]:
        # Distribute the requested total across groups, weighted by each
        # group's own target size, then nudge the last group so the grand
        # total matches exactly what was requested.
        new_groups = [g for g in groups if "student_target" in g]
        if not new_groups:
            # Every group already existed from a previous run — its students,
            # lessons and attendance were already generated then; nothing new
            # to do (see the matching skip in _create_teaching_programs).
            return {}

        raw_targets = [g["student_target"] for g in new_groups]
        total_raw = sum(raw_targets) or 1
        counts = [max(1, round(total_target * t / total_raw)) for t in raw_targets]
        diff = total_target - sum(counts)
        counts[-1] = max(1, counts[-1] + diff)

        students_by_group: dict[int, list[dict]] = {}
        ghost_ids: set[int] = set()

        for group_entry, count in zip(new_groups, counts):
            group = group_entry["group"]
            status = group_entry["status"]
            effective_end = group_entry["effective_end"]
            weights = self._status_weights_for_group(status)
            names = self._sample_names(count)

            created_students = []
            for first_name, last_name in names:
                student = Student.objects.filter(first_name=first_name, last_name=last_name, group=group).first()
                if student is not None:
                    created_students.append(student)
                    continue
                student = Student.objects.create(
                    first_name=first_name, last_name=last_name, group=group,
                    phone=self._random_phone(),
                    parent_phone=self._random_phone() if self.rng.random() < 0.9 else "",
                    is_active=True, status=Student.Status.ACTIVE,
                )
                created_students.append(student)

            window_span = max((effective_end - group.start_date).days, 1)
            for student in created_students:
                enroll_offset = int(self.rng.triangular(0, window_span * 0.7, 0))
                enroll_date = min(group.start_date + dt.timedelta(days=enroll_offset), effective_end)

                final_status = _weighted_choice(self.rng, {
                    Student.Status.ACTIVE: weights["active"],
                    Student.Status.COMPLETED: weights["completed"],
                    Student.Status.WITHDRAWN: weights["withdrawn"],
                    Student.Status.PAUSED: weights["paused"],
                } if sum(weights.values()) else {Student.Status.ACTIVE: 1})

                departure_date = None
                if final_status != Student.Status.ACTIVE:
                    low = min(enroll_date + dt.timedelta(days=7), effective_end)
                    departure_date = _random_date_between(self.rng, low, effective_end)
                    event_type = {
                        Student.Status.WITHDRAWN: StudentStatusEvent.EventType.DEACTIVATED,
                        Student.Status.PAUSED: StudentStatusEvent.EventType.PAUSED,
                        Student.Status.COMPLETED: StudentStatusEvent.EventType.COMPLETED,
                    }[final_status]
                    reason = "" if event_type == StudentStatusEvent.EventType.COMPLETED else _weighted_choice(self.rng, REASON_WEIGHTS)
                    comment = ""
                    if reason == StudentStatusEvent.Reason.OTHER:
                        comment = "Причина уточняется администрацией."
                    elif self.rng.random() < 0.3:
                        comment = "Отмечено администратором."
                    expected_return = None
                    if event_type == StudentStatusEvent.EventType.PAUSED and self.rng.random() < 0.5:
                        expected_return = departure_date + dt.timedelta(days=self.rng.randint(14, 60))

                    event = StudentStatusEvent(
                        student=student, event_type=event_type, reason=reason, comment=comment,
                        group=group, event_date=departure_date, expected_return_date=expected_return,
                        previous_status=Student.Status.ACTIVE,
                    )
                    event.save()

                    student.status = final_status
                    student.is_active = False
                    student.save(update_fields=["status", "is_active", "updated_at"])
                    Student.objects.filter(pk=student.pk).update(updated_at=_aware(departure_date))
                else:
                    if self.rng.random() < 0.08:
                        ghost_ids.add(student.id)

                Student.objects.filter(pk=student.pk).update(created_at=_aware(enroll_date, dt.time(10, 0)))

                students_by_group.setdefault(group.id, []).append({
                    "id": student.id, "enroll_date": enroll_date,
                    "departure_date": departure_date, "ghost": student.id in ghost_ids,
                })

        return students_by_group

    # -- Attendance & homework results ---------------------------------

    def _create_attendance_and_homework(self, groups: list[dict], students_by_group: dict[int, list[dict]]):
        attendance_total = 0
        homework_result_total = 0

        for group_entry in groups:
            group = group_entry["group"]
            windows = students_by_group.get(group.id, [])
            if not windows:
                continue

            lessons = list(
                Lesson.objects.filter(group=group)
                .select_related("teacher", "group_teacher__teacher")
                .order_by("date")
            )
            if not lessons:
                continue

            attendance_rows = []
            homework_results_by_homework: dict[int, list] = {}
            homeworks = {h.lesson_id: h for h in Homework.objects.filter(lesson__group=group)}

            first_date = lessons[0].date
            last_date = lessons[-1].date
            span = max((last_date - first_date).days, 1)

            for lesson in lessons:
                if lesson.status != Lesson.Status.COMPLETED:
                    continue
                homework = homeworks.get(lesson.id)

                for window in windows:
                    if window["enroll_date"] > lesson.date:
                        continue
                    if window["departure_date"] is not None and lesson.date > window["departure_date"]:
                        continue

                    weights = self._teacher_attendance_weights(lesson, window, first_date, span)
                    status = _weighted_choice(self.rng, weights)
                    attendance_rows.append(Attendance(
                        student_id=window["id"], lesson=lesson, status=status,
                    ))

                    if homework is not None:
                        hw_weights = self._teacher_homework_weights(lesson)
                        hw_status = _weighted_choice(self.rng, hw_weights)
                        score = None
                        submitted_at = None
                        checked_at = None
                        if hw_status in (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE):
                            submitted_at = _aware(lesson.date + dt.timedelta(days=1))
                        if hw_status == HomeworkResult.Status.CHECKED:
                            checked_at = _aware(lesson.date + dt.timedelta(days=2))
                            score = _weighted_choice(self.rng, self._teacher_score_weights(lesson))
                        homework_results_by_homework.setdefault(homework.id, []).append(
                            HomeworkResult(
                                homework=homework, student_id=window["id"], status=hw_status,
                                score=score, submitted_at=submitted_at, checked_at=checked_at,
                            )
                        )

            if attendance_rows:
                Attendance.objects.bulk_create(attendance_rows, ignore_conflicts=True, batch_size=500)
                attendance_total += len(attendance_rows)

            all_hw_results = [r for rows in homework_results_by_homework.values() for r in rows]
            if all_hw_results:
                HomeworkResult.objects.bulk_create(all_hw_results, ignore_conflicts=True, batch_size=500)
                homework_result_total += len(all_hw_results)

        return attendance_total, homework_result_total

    def _teacher_profile_for(self, lesson: Lesson) -> dict | None:
        teacher = lesson.effective_teacher
        if teacher is None:
            return None
        return self._teacher_profiles.get(teacher.id)

    def _teacher_attendance_weights(self, lesson: Lesson, window: dict, first_date: dt.date, span: int) -> dict:
        profile = self._teacher_profile_for(lesson)
        base = profile["attendance_weights"] if profile else {"present": 85, "late": 6, "absent": 7, "excused": 2}
        weights = dict(base)
        if window.get("ghost"):
            progress = (lesson.date - first_date).days / span
            if progress > 0.55:
                weights = {"present": 12, "late": 5, "absent": 78, "excused": 5}
        return weights

    def _teacher_homework_weights(self, lesson: Lesson) -> dict:
        profile = self._teacher_profile_for(lesson)
        return profile["homework_weights"] if profile else {"checked": 72, "submitted": 8, "late": 6, "not_submitted": 14}

    def _teacher_score_weights(self, lesson: Lesson) -> dict:
        profile = self._teacher_profile_for(lesson)
        return profile["score_weights"] if profile else {6: 10, 7: 20, 8: 30, 9: 25, 10: 15}

    # -- Reports -----------------------------------------------------

    def _create_teacher_reports(self, teachers: list[dict], months: list[tuple[int, int]]) -> int:
        created = 0
        comments = [
            "Занятия проводились стабильно, посещаемость на хорошем уровне.",
            "Основной фокус был направлен на практическую работу студентов.",
            "Продолжили закрепление пройденного материала, домашние задания сдавались стабильно.",
            "Месяц прошёл в спокойном темпе, часть групп была на каникулах.",
            "Средний балл за домашние задания вырос по сравнению с прошлым месяцем.",
        ]
        for entry in teachers:
            teacher = entry["teacher"]
            for year, month in months:
                if self.rng.random() < 0.7:
                    _, was_created = MonthlyTeacherReport.objects.get_or_create(
                        teacher=teacher, year=year, month=month,
                        defaults={"comment": self.rng.choice(comments)},
                    )
                    created += 1 if was_created else 0
        return created

    def _create_academy_reports(self, months: list[tuple[int, int]]) -> int:
        created = 0
        comments = {
            6: "Июнь — стабильный месяц, часть групп завершила набор новых студентов.",
            7: "Июль прошёл в летнем темпе, посещаемость оставалась на хорошем уровне.",
            8: "Август — подготовка групп к новому учебному потоку в сентябре.",
            9: "Сентябрь: активный набор новых студентов, отчёт за неполный период (1–20 число).",
        }
        for year, month in months:
            _, was_created = AcademyMonthlyReport.objects.get_or_create(
                year=year, month=month,
                defaults={"comment": comments.get(month, f"Отчёт академии за {month:02d}.{year}.")},
            )
            created += 1 if was_created else 0
        return created

    # -- Summary -----------------------------------------------------

    def _print_summary(self, **ctx) -> None:
        w = self.stdout.write
        line = "=" * 60
        groups = ctx["groups"]

        group_ids = [g["group"].id for g in groups]
        total_students = Student.objects.filter(group_id__in=group_ids).count()
        total_lessons = Lesson.objects.filter(group_id__in=group_ids).count()
        completed_lessons = Lesson.objects.filter(group_id__in=group_ids, status=Lesson.Status.COMPLETED).count()
        cancelled_lessons = Lesson.objects.filter(group_id__in=group_ids, status=Lesson.Status.CANCELLED).count()

        w("")
        w(self.style.SUCCESS(line))
        w(self.style.SUCCESS("   OKURMENKIDS MOCK DATA — GENERATION SUMMARY"))
        w(self.style.SUCCESS(line))
        w(f"Subjects:              {len(ctx['subjects'])}")
        w(f"Courses:               {len(ctx['courses'])}")
        w(f"Rooms:                 {len(ctx['rooms'])}")
        w(f"Teachers:              {len(ctx['teachers'])}")
        w(f"Groups:                {len(groups)}")
        w(f"Teaching programs:     {GroupTeacher.objects.filter(group_id__in=group_ids).count()} (GroupTeacher rows)")
        w(f"Students:              {total_students}")
        w(f"Lessons total:         {total_lessons}")
        w(f"  Completed:           {completed_lessons}")
        w(f"  Cancelled:           {cancelled_lessons}")
        w(f"Attendance records:    {Attendance.objects.filter(lesson__group_id__in=group_ids).count()} "
          f"({ctx['attendance_count']} created this run)")
        w(f"Homework results:      {HomeworkResult.objects.filter(homework__lesson__group_id__in=group_ids).count()} "
          f"({ctx['homework_result_count']} created this run)")
        w(f"Monthly teacher reports created this run: {ctx['teacher_reports']}")
        w(f"Academy monthly reports created this run: {ctx['academy_reports']}")
        w("")
        w(self.style.WARNING(
            "Payments / Refunds / Revenue: NOT GENERATED — this project has no "
            "Payment/Refund model (see module docstring). Every revenue figure a "
            "report shows for this data will read as \"—\"/None, exactly as it "
            "already does for all existing data in this project."
        ))
        w("")
        w("Live report figures for the generated months:")
        for year, month in ctx["months"]:
            stats = compute_academy_monthly_stats(year, month)
            w(
                f"  {month:02d}.{year}: students={stats['students']['active']} "
                f"new={stats['students']['new']} left={stats['students']['left']} "
                f"completed={stats['students']['completed']} "
                f"lessons_completed={stats['lessons_completed']} "
                f"attendance_rate={stats['attendance']['rate']}% "
                f"kpi_total={stats['kpi']['total']}"
            )
        w("")
        w(self.style.SUCCESS(line))
        w(self.style.SUCCESS("   MOCK DATA READY"))
        w(self.style.SUCCESS(line))
        w("")
        w(f"Admin login:   {MOCK_ADMIN_USERNAME}")
        w(f"Teacher login: {MOCK_TEACHER_USERNAME_PREFIX}01 / password: {MOCK_TEACHER_PASSWORD}")
        w(line)


def _weekday_index(code: str) -> int:
    return WEEKDAY_POOL.index(code)
