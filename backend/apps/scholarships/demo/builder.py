"""Builds a large, deterministic scholarship DEMO dataset from real LMS models.

Timeline (relative to ``today``, default = today in Asia/Bishkek):

    month 1..4  = the four full calendar months before the current one
    current     = the running month, lessons up to *yesterday* only

With today = 2026-09-26 that is May–August (+ September 1–25), and the
scholarship cycles are generated exactly as production would:

    Jun 1 → May,  Jul 1 → June,  Aug 1 → July,  Sep 1 → August
    Oct 1 → September is *not* generated: September is not finished.

The three oldest periods are approved, the latest one is left as a draft so
an admin can still recalculate/approve it by hand.

Nothing here is a model or migration — only rows of existing models, all
tagged via ``demo.namespace``. Every "random" choice comes from one
``random.Random(seed)``, consumed in a fixed order, so the same
``--seed``/``--students``/``--today`` always produce identical data.
"""
from __future__ import annotations

import datetime as dt
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.academy.models import (
    Attendance,
    Course,
    Group,
    GroupSchedule,
    GroupTeacher,
    Homework,
    HomeworkResult,
    Lesson,
    Student,
    StudentStatusEvent,
)
from apps.scholarships.models import ScholarshipConfiguration, ScholarshipPeriod, TrainerFeedback
from apps.scholarships.services.generation import approve_period, generate_period, recalculate_period
from apps.users.models import Subject, Teacher, User

from . import namespace as ns

BATCH = 2000

SUBJECTS = ["Python", "HTML/CSS/JS", "CyberSecurity", "English", "Soft Skills"]
NO_HOMEWORK_SUBJECTS = {"Soft Skills"}

# Program → its subjects, primary first. A group with k subjects studies the
# first k — so groups of the same program differ in how many subjects they have.
PROGRAMS = {
    "PY": ("Python Development", ["Python", "English", "Soft Skills", "HTML/CSS/JS", "CyberSecurity"]),
    "WEB": ("Web Development", ["HTML/CSS/JS", "Python", "English", "Soft Skills", "CyberSecurity"]),
    "CS": ("Cyber Security", ["CyberSecurity", "Python", "English", "Soft Skills", "HTML/CSS/JS"]),
    "KIDS": ("IT Kids", ["Python", "HTML/CSS/JS", "English", "Soft Skills", "CyberSecurity"]),
}

# (program, number of subjects) per group, cycled. The first seven entries
# guarantee the groups the special scenarios need (CS×2, CS×3, 5 subjects).
GROUP_PLAN = [
    ("PY", 1), ("WEB", 2), ("CS", 2), ("KIDS", 5), ("PY", 3), ("WEB", 4), ("CS", 3),
    ("KIDS", 4), ("PY", 2), ("WEB", 5), ("CS", 5), ("KIDS", 3), ("PY", 4), ("WEB", 1),
    ("CS", 4), ("KIDS", 2), ("PY", 5), ("WEB", 3), ("CS", 1), ("KIDS", 5), ("PY", 3),
    ("WEB", 2), ("CS", 3), ("KIDS", 4), ("PY", 2),
]
MIN_GROUPS = 7

WEEKDAY_PATTERNS = [(0, 2, 4), (1, 3), (1, 3, 5), (0, 3), (2, 4), (0, 2), (1, 4, 5)]
WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Generation-only performance profiles (never used by the scholarship logic).
# (share of students, attendance range, homework range, feedback range 0–100)
PROFILES = {
    "top": (0.10, (0.95, 1.00), (0.90, 1.00), (90, 100)),
    "strong": (0.20, (0.85, 0.95), (0.80, 0.95), (80, 95)),
    "average": (0.30, (0.70, 0.85), (0.65, 0.85), (70, 85)),
    "weak": (0.25, (0.50, 0.70), (0.40, 0.70), (50, 70)),
    "very_weak": (0.15, (0.25, 0.50), (0.15, 0.50), (35, 60)),
}

FIRST_NAMES = [
    "Айбек", "Нурлан", "Эмир", "Тимур", "Бекзат", "Арслан", "Данияр", "Азамат", "Мирлан", "Эрлан",
    "Руслан", "Адилет", "Нурсултан", "Бакыт", "Искендер", "Самат", "Алихан", "Жоомарт", "Улан", "Кубаныч",
    "Айгерим", "Айдана", "Нурай", "Сезим", "Асель", "Мээрим", "Жибек", "Айпери", "Бермет", "Динара",
    "Алина", "Камила", "Амина", "Салтанат", "Айжан", "Элиза", "Самира", "Томирис", "Нуриза", "Гулзат",
]
LAST_NAMES = [
    "Асанов", "Бекмуратов", "Токтосунов", "Жумабаев", "Орозбеков", "Сыдыков", "Абдыкадыров", "Касымов",
    "Мамытов", "Садыков", "Турдубаев", "Алымкулов", "Эсенов", "Кадыров", "Омуралиев", "Иманалиев",
    "Бакиров", "Молдоев", "Шаршеев", "Токтогулов", "Исаков", "Жолдошев", "Мукашев", "Сатаров",
]


@dataclass
class StudentPlan:
    key: str
    first_name: str
    last_name: str
    group_index: int
    profile: str
    attendance: float
    homework: float
    feedback: float
    enrollment_date: dt.date
    per_subject: dict = field(default_factory=dict)  # subject -> (att, hw, fb)
    scenario: str = ""
    feedback_rule: str = ""  # "", "missing_one", "none", "only_one"
    deterministic: bool = False  # ties: no randomness at all
    withdrawn_on: dt.date | None = None
    paused: tuple[dt.date, dt.date] | None = None
    student: Student | None = None
    missing_homework_rows: bool = False  # misses become *no result row* instead of «Не сдано»
    _acc: dict = field(default_factory=dict)

    def hit(self, key: tuple, rate: float) -> bool:
        """Exact-proportion outcome for scenario students: over n calls with
        the same key, exactly round(n·rate) return True, spread evenly —
        so a scenario's intended rate holds even in a tiny dataset."""
        acc = self._acc.get(key, 0.5) + rate
        self._acc[key] = acc - int(acc)
        return acc >= 1

    def rates(self, subject: str) -> tuple[float, float, float]:
        return self.per_subject.get(subject, (self.attendance, self.homework, self.feedback))

    def active_on(self, day: dt.date) -> bool:
        if day < self.enrollment_date:
            return False
        if self.withdrawn_on and day >= self.withdrawn_on:
            return False
        if self.paused and self.paused[0] <= day < self.paused[1]:
            return False
        return True


@dataclass
class BuildReport:
    timings: dict = field(default_factory=dict)
    scenarios: dict = field(default_factory=dict)  # key -> student
    periods: list = field(default_factory=list)
    skipped_periods: list = field(default_factory=list)
    award_dates: list = field(default_factory=list)
    data_start: dt.date | None = None
    data_end: dt.date | None = None


def _add_months(day: dt.date, months: int) -> dt.date:
    index = day.year * 12 + day.month - 1 + months
    return dt.date(index // 12, index % 12 + 1, 1)


class DemoBuilder:
    def __init__(self, *, students: int, seed: int, today: dt.date, stdout=None):
        self.n_students = students
        self.rng = random.Random(seed)
        self.today = today
        self.out = stdout
        self.report = BuildReport()
        self.current_month = today.replace(day=1)
        self.data_start = _add_months(self.current_month, -4)
        self.data_end = today - dt.timedelta(days=1)
        self.award_dates = [_add_months(self.data_start, i) for i in range(1, 5)]
        self.report.data_start, self.report.data_end = self.data_start, self.data_end
        self.report.award_dates = self.award_dates

    def log(self, message: str) -> None:
        if self.out:
            self.out.write(message)

    def _timed(self, label, fn, *args):
        started = time.perf_counter()
        result = fn(*args)
        self.report.timings[label] = time.perf_counter() - started
        self.log(f"  {label}: {self.report.timings[label]:.1f}s")
        return result

    # ------------------------------------------------------------------ build

    def build(self) -> BuildReport:
        with transaction.atomic():
            self._timed("catalogue (subjects, programs, teachers, groups)", self._catalogue)
            self._timed("students", self._students)
            self._timed("lessons + schedules", self._lessons)
            self._timed("attendance", self._attendance)
            self._timed("homework + results", self._homework)
        self._timed("scholarship periods + trainer feedback", self._periods)
        return self.report

    # -- catalogue -------------------------------------------------------------

    def _catalogue(self) -> None:
        rng = self.rng
        self.subjects = {name: Subject.objects.get_or_create(name=name)[0] for name in SUBJECTS}

        self.courses = {}
        for code, (title, subjects) in PROGRAMS.items():
            course = Course.objects.create(
                name=f"{ns.PREFIX}{title}", count_lesson=96, description="Демо-программа для проверки стипендий.",
            )
            course.subjects.set([self.subjects[s] for s in subjects])
            self.courses[code] = course

        n_groups = max(MIN_GROUPS, round(self.n_students / 16))
        self.n_teachers = max(len(SUBJECTS), n_groups)

        password = make_password(None)  # unusable: demo trainers can't log in unless an admin sets a password
        admin = User(
            username=ns.ADMIN_USERNAME, email=f"admin{ns.EMAIL_DOMAIN}", first_name="Demo", last_name="Admin",
            role=User.Role.ADMIN, is_verified=True, password=password, is_staff=True, is_superuser=True,
        )
        users = [admin]
        teacher_subjects = []
        for i in range(self.n_teachers):
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            users.append(User(
                username=f"{ns.USERNAME_PREFIX}trainer{i + 1:02d}", email=f"trainer{i + 1:02d}{ns.EMAIL_DOMAIN}",
                first_name=first, last_name=last, role=User.Role.TEACHER, is_verified=True, password=password,
            ))
            primary = SUBJECTS[i % len(SUBJECTS)]
            extra = [SUBJECTS[(i + 2) % len(SUBJECTS)]] if i % 3 == 0 else []
            teacher_subjects.append([primary, *extra])
        User.objects.bulk_create(users, batch_size=BATCH)
        users = {u.username: u for u in User.objects.filter(ns.demo_user_q())}
        self.demo_admin = users[ns.ADMIN_USERNAME]

        teachers = Teacher.objects.bulk_create([
            Teacher(user=users[f"{ns.USERNAME_PREFIX}trainer{i + 1:02d}"], position="Тренер (демо)",
                    experience_years=rng.randint(1, 10), hire_date=dt.date(2024, 9, 1))
            for i in range(self.n_teachers)
        ])
        through = Teacher.subjects.through
        through.objects.bulk_create([
            through(teacher_id=t.id, subject_id=self.subjects[s].id)
            for t, subs in zip(teachers, teacher_subjects) for s in subs
        ])
        self.teachers_by_subject = defaultdict(list)
        for t, subs in zip(teachers, teacher_subjects):
            for s in subs:
                self.teachers_by_subject[s].append(t)
        self.teachers = teachers

        # Groups
        load = defaultdict(int)
        self.group_plans = []  # (group, program, [subject names])
        counters = defaultdict(int)
        groups = []
        for index in range(n_groups):
            program, k = GROUP_PLAN[index % len(GROUP_PLAN)]
            counters[program] += 1
            groups.append(Group(
                name=f"{ns.PREFIX}{program}-{counters[program]:02d}", course=self.courses[program],
                start_date=self.data_start, status=Group.Status.ACTIVE, max_students=25,
                description=f"Демо-группа: {k} предм.",
            ))
            self.group_plans.append((program, PROGRAMS[program][1][:k]))
        self.groups = Group.objects.bulk_create(groups)

        # GroupTeacher: least-loaded trainer of the subject; every 6th group
        # gets a second trainer for its primary subject (multiple trainers).
        gts = []
        self.group_programs = []  # per group: list of (subject, [GroupTeacher, ...])
        for index, (group, (_, subject_names)) in enumerate(zip(self.groups, self.group_plans)):
            programs = []
            for position, subject in enumerate(subject_names):
                candidates = sorted(self.teachers_by_subject[subject], key=lambda t: (load[t.id], t.id))
                chosen = candidates[:2] if (position == 0 and index % 6 == 5 and len(candidates) > 1) else candidates[:1]
                row = []
                for teacher in chosen:
                    load[teacher.id] += 1
                    gt = GroupTeacher(group=group, teacher=teacher, subject=self.subjects[subject])
                    gts.append(gt)
                    row.append(gt)
                programs.append((subject, row))
            self.group_programs.append(programs)
        GroupTeacher.objects.bulk_create(gts)

    # -- students --------------------------------------------------------------

    def _group_sizes(self) -> list[int]:
        weights = [self.rng.uniform(0.7, 1.3) for _ in self.groups]
        total = sum(weights)
        sizes = [max(1, int(self.n_students * w / total)) for w in weights]
        i = 0
        while sum(sizes) < self.n_students:
            sizes[i % len(sizes)] += 1
            i += 1
        while sum(sizes) > self.n_students:
            j = max(range(len(sizes)), key=lambda k: sizes[k])
            sizes[j] -= 1
        return sizes

    def _find_group(self, program: str, k: int) -> int:
        for index, (p, subjects) in enumerate(self.group_plans):
            if p == program and len(subjects) == k:
                return index
        raise RuntimeError(f"no {program} group with {k} subjects")

    def _pick_profile(self) -> str:
        r = self.rng.random()
        acc = 0.0
        for name, (share, *_rest) in PROFILES.items():
            acc += share
            if r < acc:
                return name
        return "very_weak"

    def _plan_from_profile(self, key, group_index, profile, enrolled) -> StudentPlan:
        _, att, hw, fb = PROFILES[profile]
        rng = self.rng
        plan = StudentPlan(
            key=key, first_name=rng.choice(FIRST_NAMES), last_name=rng.choice(LAST_NAMES), group_index=group_index,
            profile=profile, attendance=rng.uniform(*att), homework=rng.uniform(*hw), feedback=rng.uniform(*fb),
            enrollment_date=enrolled,
        )
        for subject in self.group_plans[group_index][1]:
            jitter = lambda value, spread, lo, hi: min(hi, max(lo, value + rng.uniform(-spread, spread)))
            plan.per_subject[subject] = (
                jitter(plan.attendance, 0.04, 0.05, 1.0),
                jitter(plan.homework, 0.05, 0.0, 1.0),
                jitter(plan.feedback, 5, 25, 100),
            )
        return plan

    def _scenario_plans(self) -> list[StudentPlan]:
        start = self.data_start
        month = lambda n, day=1: _add_months(start, n).replace(day=day)
        cs2, cs3 = self._find_group("CS", 2), self._find_group("CS", 3)
        five = self._find_group("KIDS", 5)
        py3 = self._find_group("PY", 3)
        web4 = self._find_group("WEB", 4)

        def plan(key, first, last, group, *, att=0.9, hw=0.9, fb=90, per_subject=None, **extra):
            p = StudentPlan(key=key, first_name=first, last_name=last, group_index=group, profile="scenario",
                            attendance=att, homework=hw, feedback=fb, enrollment_date=extra.pop("enrolled", start),
                            scenario=extra.pop("scenario"), **extra)
            p.per_subject = per_subject or {}
            return p

        plans = [
            plan("A", "Арген", "Сценарий-A", cs2, scenario="A: Python высокий, CyberSecurity низкий",
                 per_subject={"Python": (1.0, 1.0, 97), "CyberSecurity": (0.55, 0.45, 55)}),
            plan("B", "Бекмырза", "Сценарий-B", cs3, scenario="B: 3 предмета, разные результаты",
                 per_subject={"Python": (0.98, 0.95, 95), "English": (0.8, 0.75, 78), "CyberSecurity": (0.6, 0.55, 60)}),
            plan("C", "Чолпон", "Сценарий-C", five, scenario="C: 5 предметов",
                 per_subject={"Python": (1.0, 1.0, 98), "HTML/CSS/JS": (0.9, 0.85, 88), "English": (0.8, 0.7, 75),
                              "Soft Skills": (0.7, 0.0, 70), "CyberSecurity": (0.55, 0.5, 58)}),
            plan("D", "Данияр", "Сценарий-D", web4, att=0.98, hw=0.25, fb=80, missing_homework_rows=True,
                 scenario="D: высокая посещаемость, слабое ДЗ (часть ДЗ без результата)"),
            plan("E", "Эльмира", "Сценарий-E", web4, att=0.45, hw=0.98, fb=85,
                 scenario="E: сильное ДЗ, слабая посещаемость"),
            plan("F", "Фарида", "Сценарий-F", py3, att=0.95, hw=0.95, fb=92, feedback_rule="missing_one",
                 scenario="F: нет оценки тренера по одному предмету"),
            plan("G", "Гулжан", "Сценарий-G", py3, att=0.95, hw=0.92, fb=92, enrolled=month(2, 15),
                 scenario=f"G: начал(а) обучение в середине месяца ({month(2, 15):%d.%m})"),
            plan("H", "Хасан", "Сценарий-H", py3, att=1.0, hw=1.0, fb=95, enrolled=month(4, 10),
                 scenario=f"H: начал(а) недавно ({month(4, 10):%d.%m}) — незавершённый период"),
        ]
        # Ties: identical data in one group → identical scores. T4 enrolled
        # earlier, so the documented tie-breaker puts it first; T1–T3 fall
        # back to the lowest student id.
        for key, first, enrolled in (("T1", "Тилек", start), ("T2", "Тимур", start), ("T3", "Талант", start),
                                     ("T4", "Тынчтык", start - dt.timedelta(days=20))):
            plans.append(plan(key, first, f"Ничья-{key}", py3, att=1.0, hw=1.0, fb=90, enrolled=enrolled,
                              deterministic=True, scenario=f"{key}: одинаковые баллы (проверка тай-брейка)"))
        return plans

    def _students(self) -> None:
        rng = self.rng
        scenarios = self._scenario_plans()
        sizes = self._group_sizes()
        for p in scenarios:  # scenario students count towards the total
            index = p.group_index if sizes[p.group_index] > 0 else max(range(len(sizes)), key=lambda k: sizes[k])
            sizes[index] -= 1

        plans: list[StudentPlan] = []
        number = 0
        for group_index, size in enumerate(sizes):
            for _ in range(size):
                number += 1
                r = rng.random()
                if r < 0.78:
                    enrolled = self.data_start - dt.timedelta(days=rng.randint(0, 60))  # before the academy month 1
                elif r < 0.95:
                    enrolled = _add_months(self.data_start, rng.randint(1, 3)) + dt.timedelta(days=rng.randint(0, 20))
                else:
                    enrolled = self.current_month + dt.timedelta(days=rng.randint(0, max(0, self.data_end.day - 2)))
                plan = self._plan_from_profile(f"{number:04d}", group_index, self._pick_profile(), enrolled)
                edge = rng.random()
                if edge < 0.03:
                    plan.feedback_rule = "only_one"
                elif edge < 0.06:
                    plan.feedback_rule = "missing_one"
                plans.append(plan)

        # Status history edge cases: a few withdrawn / paused-and-returned students.
        regular = [p for p in plans if p.enrollment_date <= self.data_start]
        for p in rng.sample(regular, min(len(regular), max(2, self.n_students // 100))):
            p.withdrawn_on = _add_months(self.data_start, 3) + dt.timedelta(days=9)
        for p in rng.sample([p for p in regular if not p.withdrawn_on], min(len(regular), max(2, self.n_students // 100))):
            pause_start = _add_months(self.data_start, 2) + dt.timedelta(days=9)
            p.paused = (pause_start, pause_start + dt.timedelta(days=14))

        self.plans = plans + scenarios
        students = []
        for p in self.plans:
            withdrawn = p.withdrawn_on is not None
            students.append(Student(
                first_name=p.first_name, last_name=p.last_name, phone=ns.student_phone(p.key),
                group=self.groups[p.group_index], enrollment_date=p.enrollment_date,
                status=Student.Status.WITHDRAWN if withdrawn else Student.Status.ACTIVE, is_active=not withdrawn,
            ))
        created = Student.objects.bulk_create(students, batch_size=BATCH)
        tz = timezone.get_current_timezone()
        for p, s in zip(self.plans, created):
            p.student = s
            registered = p.enrollment_date - dt.timedelta(days=rng.randint(0, 21))
            s.created_at = dt.datetime.combine(registered, dt.time(10, rng.randint(0, 59)), tzinfo=tz)
            if p.scenario:
                self.report.scenarios[p.key] = (s, p.scenario)
        Student.objects.bulk_update(created, ["created_at"], batch_size=BATCH)

        events = []
        for p in self.plans:
            if p.withdrawn_on:
                events.append(StudentStatusEvent(
                    student=p.student, event_type=StudentStatusEvent.EventType.DEACTIVATED,
                    reason=StudentStatusEvent.Reason.RELOCATION, group=p.student.group, event_date=p.withdrawn_on,
                    previous_status=Student.Status.ACTIVE, performed_by=self.demo_admin,
                ))
            if p.paused:
                events += [
                    StudentStatusEvent(
                        student=p.student, event_type=StudentStatusEvent.EventType.PAUSED,
                        reason=StudentStatusEvent.Reason.HEALTH, group=p.student.group, event_date=p.paused[0],
                        expected_return_date=p.paused[1], previous_status=Student.Status.ACTIVE,
                        performed_by=self.demo_admin,
                    ),
                    StudentStatusEvent(
                        student=p.student, event_type=StudentStatusEvent.EventType.CONTINUED, group=p.student.group,
                        event_date=p.paused[1], previous_status=Student.Status.PAUSED, performed_by=self.demo_admin,
                    ),
                ]
        StudentStatusEvent.objects.bulk_create(events)

    # -- lessons ---------------------------------------------------------------

    def _lessons(self) -> None:
        rng = self.rng
        lessons, schedules = [], []
        numbers = defaultdict(int)
        for group, programs in zip(self.groups, self.group_programs):
            for position, (subject, gts) in enumerate(programs):
                pattern = WEEKDAY_PATTERNS[rng.randrange(len(WEEKDAY_PATTERNS))]
                start_time = dt.time(9 + 2 * position)
                end_time = dt.time(10 + 2 * position, 30)
                for weekday in pattern:
                    for gt in gts:
                        schedules.append(GroupSchedule(
                            group=group, teacher=gt.teacher, subject=gt.subject, group_teacher=gt,
                            day_of_week=WEEKDAY_CODES[weekday], start_time=start_time, end_time=end_time,
                        ))
                day = self.data_start
                count = 0
                while day <= self.data_end:
                    if day.weekday() in pattern:
                        gt = gts[count % len(gts)]  # several trainers alternate
                        count += 1
                        numbers[gt.id] += 1
                        cancelled = rng.random() < 0.03
                        lessons.append(Lesson(
                            group=group, group_teacher=gt, teacher=gt.teacher, subject=gt.subject,
                            lesson_number=numbers[gt.id], date=day, start_time=start_time, end_time=end_time,
                            topic=f"{subject}: тема {numbers[gt.id]}",
                            status=Lesson.Status.CANCELLED if cancelled else Lesson.Status.COMPLETED,
                            cancellation_reason="Праздничный день" if cancelled else "",
                            homework_not_required=subject in NO_HOMEWORK_SUBJECTS or rng.random() < 0.08,
                        ))
                    day += dt.timedelta(days=1)
        GroupSchedule.objects.bulk_create(schedules, batch_size=BATCH)
        self.lessons = Lesson.objects.bulk_create(lessons, batch_size=BATCH)
        self.lessons_by_group = defaultdict(list)
        for lesson in self.lessons:
            self.lessons_by_group[lesson.group_id].append(lesson)

    # -- attendance ------------------------------------------------------------

    def _attendance(self) -> None:
        rng = self.rng
        rows = []
        self.attended = {}  # (student_id, lesson_id) -> status
        for p in self.plans:
            for lesson in self.lessons_by_group[p.student.group_id]:
                if lesson.status == Lesson.Status.CANCELLED or not p.active_on(lesson.date):
                    continue
                if p.deterministic:
                    status = Attendance.Status.PRESENT
                elif p.scenario:
                    present = p.hit(("att", lesson.subject.name), p.rates(lesson.subject.name)[0])
                    status = Attendance.Status.PRESENT if present else Attendance.Status.ABSENT
                else:
                    if not p.scenario and rng.random() < 0.005:
                        continue  # a trainer forgot to mark this one → "без отметки"
                    att = p.rates(lesson.subject.name)[0]
                    if rng.random() < att:
                        status = Attendance.Status.LATE if rng.random() < 0.06 else Attendance.Status.PRESENT
                    else:
                        status = Attendance.Status.EXCUSED if rng.random() < 0.2 else Attendance.Status.ABSENT
                rows.append(Attendance(student=p.student, lesson=lesson, status=status))
                self.attended[(p.student.id, lesson.id)] = status
        Attendance.objects.bulk_create(rows, batch_size=BATCH)

    # -- homework --------------------------------------------------------------

    def _homework(self) -> None:
        rng = self.rng
        tz = timezone.get_current_timezone()
        homework = []
        for lesson in self.lessons:
            if lesson.status == Lesson.Status.CANCELLED or lesson.homework_not_required:
                continue
            homework.append(Homework(
                lesson=lesson, title=f"ДЗ {lesson.lesson_number}: {lesson.subject.name}",
                deadline=lesson.date + dt.timedelta(days=3),
            ))
        homework = Homework.objects.bulk_create(homework, batch_size=BATCH)
        by_lesson = {hw.lesson_id: hw for hw in homework}
        lesson_by_id = {lesson.id: lesson for lesson in self.lessons}

        results = []
        for p in self.plans:
            for lesson in self.lessons_by_group[p.student.group_id]:
                hw = by_lesson.get(lesson.id)
                if hw is None or (p.student.id, lesson.id) not in self.attended:
                    continue
                if p.deterministic:
                    status, score = HomeworkResult.Status.CHECKED, 10
                elif p.scenario:
                    done = p.hit(("hw", lesson.subject.name), p.rates(lesson.subject.name)[1])
                    if not done and p.missing_homework_rows and p.hit(("hw-missing",), 0.5):
                        continue  # no result row at all → «ДЗ без результата» warning
                    status = HomeworkResult.Status.CHECKED if done else HomeworkResult.Status.NOT_SUBMITTED
                    score = 9 if done else None
                else:
                    if not p.scenario and rng.random() < 0.02:
                        continue  # no result row at all
                    rate = p.rates(lesson_by_id[lesson.id].subject.name)[1]
                    r = rng.random()
                    if r < rate:
                        status = HomeworkResult.Status.CHECKED if rng.random() < 0.85 else HomeworkResult.Status.SUBMITTED
                    elif r < rate + (1 - rate) * 0.3:
                        status = HomeworkResult.Status.LATE
                    else:
                        status = HomeworkResult.Status.NOT_SUBMITTED
                    score = (
                        max(0, min(10, round(rng.gauss(10 * max(rate, 0.3), 1.2))))
                        if status in (HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE) else None
                    )
                done = status != HomeworkResult.Status.NOT_SUBMITTED
                submitted = dt.datetime.combine(lesson.date + dt.timedelta(days=5 if status == "late" else 2), dt.time(18), tzinfo=tz)
                results.append(HomeworkResult(
                    homework=hw, student=p.student, status=status, score=score,
                    submitted_at=submitted if done else None,
                    checked_at=submitted + dt.timedelta(days=1) if status == HomeworkResult.Status.CHECKED else None,
                ))
        HomeworkResult.objects.bulk_create(results, batch_size=BATCH)

    # -- scholarship periods + feedback --------------------------------------

    def _feedback_value(self, center: float) -> int:
        return max(1, min(5, round(self.rng.gauss(center / 20, 0.35))))

    def _feedback_rows(self, period: ScholarshipPeriod) -> list[TrainerFeedback]:
        """One TrainerFeedback per (student, subject, trainer) actually taught
        in the period — minus the deliberate edge cases."""
        taught = defaultdict(set)  # student_id -> {(subject, teacher)}
        for lesson in self.lessons:
            if not (period.period_start <= lesson.date <= period.period_end) or lesson.status == Lesson.Status.CANCELLED:
                continue
            for p in self._plans_by_group[lesson.group_id]:
                if (p.student.id, lesson.id) in self.attended:
                    taught[p.student.id].add((lesson.subject.name, lesson.teacher_id))
        rows = []
        for p in self.plans:
            pairs = sorted(taught.get(p.student.id, ()))
            if not pairs:
                continue
            subjects = sorted({s for s, _ in pairs})
            rule = p.feedback_rule
            if not p.scenario and not rule and self.rng.random() < 0.04:
                rule = "none"  # this trainer group simply didn't submit this month
            if rule == "none":
                continue
            skip = set()
            if rule == "missing_one" and len(subjects) > 1:
                skip = {subjects[-1]}
            elif rule == "missing_one":
                skip = set(subjects)
            elif rule == "only_one":
                skip = set(subjects[1:])
            for subject, teacher_id in pairs:
                if subject in skip:
                    continue
                fb = p.rates(subject)[2]
                values = (5, 4, 5, 4) if p.deterministic else tuple(self._feedback_value(fb) for _ in range(4))
                rows.append(TrainerFeedback(
                    period=period, student=p.student, subject=self.subjects[subject], teacher_id=teacher_id,
                    progress=values[0], participation=values[1], discipline=values[2], understanding=values[3],
                    comment="" if self.rng.random() < 0.7 else "Демо-комментарий тренера.",
                    created_by=self.demo_admin, updated_by=self.demo_admin,
                ))
        return rows

    def _periods(self) -> None:
        if Student.objects.exclude(ns.demo_student_q()).exists():
            self.report.skipped_periods.append(
                "В базе есть не-демо студенты: периоды оценивают ВСЕХ студентов, поэтому демо-периоды не создаются "
                "(запустите на отдельной/тестовой базе)."
            )
            return
        if ScholarshipConfiguration.objects.active() is None:
            self.report.skipped_periods.append("Нет активной конфигурации стипендий.")
            return
        self._plans_by_group = defaultdict(list)
        for p in self.plans:
            self._plans_by_group[p.student.group_id].append(p)

        for index, award_date in enumerate(self.award_dates):
            start = _add_months(award_date, -1)
            if ScholarshipPeriod.objects.filter(award_day=1, period_start=start).exists():
                self.report.skipped_periods.append(f"Период {start:%m.%Y} уже существует — не трогаем.")
                continue
            period = generate_period(award_date, 1, user=self.demo_admin, today=self.today).period
            TrainerFeedback.objects.bulk_create(self._feedback_rows(period), batch_size=BATCH)
            period = recalculate_period(period, user=self.demo_admin)
            if index < len(self.award_dates) - 1:
                period = approve_period(period, user=self.demo_admin)
            self.report.periods.append(period)


def clear_demo_data(stdout=None) -> dict:
    """Delete only namespaced demo rows. Refuses to delete a demo period that
    holds an *approved* award for a non-demo student."""
    demo_admin = User.objects.filter(ns.demo_user_q(), username=ns.ADMIN_USERNAME).first()
    periods = ScholarshipPeriod.objects.filter(generated_by=demo_admin) if demo_admin else ScholarshipPeriod.objects.none()
    unsafe = periods.filter(awards__status="approved").exclude(awards__student__phone__startswith=ns.PHONE_PREFIX)
    if unsafe.exists():
        raise ValueError(
            "Демо-период содержит утверждённые стипендии не-демо студентов: "
            + ", ".join(str(p) for p in unsafe.distinct()) + ". Удаление отменено."
        )
    groups = Group.objects.filter(ns.demo_group_q())
    lessons = Lesson.objects.filter(group__in=groups)
    counts = {
        "scholarship periods": periods.count(),
        "trainer feedback": TrainerFeedback.objects.filter(student__phone__startswith=ns.PHONE_PREFIX).count(),
        "students": Student.objects.filter(ns.demo_student_q()).count(),
        "groups": groups.count(),
        "lessons": lessons.count(),
        "attendance": Attendance.objects.filter(lesson__in=lessons).count(),
        "homework": Homework.objects.filter(lesson__in=lessons).count(),
        "homework results": HomeworkResult.objects.filter(homework__lesson__in=lessons).count(),
        "programs": Course.objects.filter(ns.demo_group_q()).count(),
        "users (trainers + admin)": User.objects.filter(ns.demo_user_q()).count(),
    }
    with transaction.atomic():
        if demo_admin:
            from apps.scholarships.models import ScholarshipRunLog

            ScholarshipRunLog.objects.filter(triggered_by=demo_admin).delete()
        periods.delete()
        Student.objects.filter(ns.demo_student_q()).delete()
        groups.delete()
        Course.objects.filter(ns.demo_group_q()).delete()
        User.objects.filter(ns.demo_user_q()).delete()
    return counts


def demo_data_exists() -> bool:
    return (
        Student.objects.filter(ns.demo_student_q()).exists()
        or Group.objects.filter(ns.demo_group_q()).exists()
        or User.objects.filter(ns.demo_user_q()).exists()
    )


