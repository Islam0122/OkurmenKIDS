"""Тестовые данные бухгалтерии за август–октябрь 2026 (manage.py seed_accounting_demo).

Набор создаётся через сервисы модуля (синхронизация циклов, расчёт,
утверждение, выплаты), поэтому циклы, начисления, строки, остатки и журнал
получаются теми же, что и в работе. Ничего не «рисуется» в бухгалтерских
таблицах: прогресс циклов — это реальные тестовые уроки.

Безопасность
* Все созданные записи — в реестре `DemoSeedRecord` (не по именам). Реальные
  сотрудники, группы, курсы, настройки и начисления не изменяются: под
  сценарии создаются DEMO-сотрудники, DEMO-курсы и DEMO-группы; общие
  справочники (предметы IT / English / Soft Skills) переиспользуются, если уже
  есть, и тогда не попадают в реестр.
* Каждый объект создаётся через `ensure(key)` — повторный запуск без
  `--clear` ничего не дублирует; выплаты дополнительно защищены ключом
  идемпотентности, расчёты — статусами.
* `clear()` удаляет только объекты из реестра и останавливается с ошибкой,
  если удаление задело бы (каскадом, PROTECT, SET_NULL или связью M2M) хоть
  одну незарегистрированную запись; после удаления сверяет количества.
* Всё в одной транзакции; `dry_run` откатывает её.

Сценарии (при генерации 10.10.2026; другая дата сдвигает только статусы
уроков «проведён / запланирован»):
* Оклад 30 000 (Ассистент): август выплачен полностью, сентябрь — частично
  (остаток 10 000), октябрь — рассчитан, ждёт утверждения.
* Оклад Team Lead: 35 000 в августе, с 01.09 — 40 000 (новая версия правила,
  история сохранена); август — частично (остаток 15 000), сентябрь не оплачен.
* IT-тренер 10 % ведёт две группы: блоки 10.08 (→15.08), 20.08 (→01.09),
  12.09 (→15.09), блок G2 09.09 вели два тренера (9/12 и 3/12 по их ставкам),
  второй блок G2 в сентябре (29.09) — «Требует проверки»; открытые блоки
  8/12 (прогноз 10 × 10 000 × 10 % = 10 000, завершение 20.10 → выплата 01.11)
  и 10/12.
* English-тренер 8 %, с 01.10 — 9 % (ставка сохранена в истории начисления):
  несколько блоков в одном месяце у одной группы, несколько выплат по одному
  начислению, блок 10.10 (→15.10) рассчитан и ждёт утверждения.
* Soft Skills-тренер без правила оплаты — блок завершён, начисления нет,
  расчёт показывает «Не настроена ставка».
* IT-тренер 14 % — блок на 20 уроков (одна выбыла: 11 студентов × 8 000),
  открытый блок 19/20, замена в чужом блоке.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import Sum

from apps.academy.models import (
    Course,
    CourseLessonPlan,
    Group,
    GroupTeacher,
    Lesson,
    Student,
    StudentStatusEvent,
    TrainerAssignment,
)
from apps.users.models import Subject, Teacher, User

from ..models import (
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    CycleAccrual,
    CycleLesson,
    DemoSeedRecord,
    EmployeeSalaryProfile,
    Payroll,
    PayrollAdjustment,
    PayrollAuditLog,
    PayrollLine,
    PayrollPayment,
    PayrollPeriod,
    SalaryRule,
    StudentPayment,
    maintenance_delete,
)
from . import AccountingError
from .money import ZERO, money

DATASET = "accounting_demo"
MONTHS = {"2026-08": (2026, 8), "2026-09": (2026, 9), "2026-10": (2026, 10)}
FIRST, SECOND, MONTH = "FIRST_HALF", "SECOND_HALF", "MONTH"
D = Decimal


class SeedError(AccountingError):
    pass


# ---------------------------------------------------------------------------
# Реестр
# ---------------------------------------------------------------------------

def _ct(model) -> ContentType:
    return ContentType.objects.get_for_model(model, for_concrete_model=False)


def registered(model) -> models.QuerySet:
    ids = DemoSeedRecord.objects.filter(dataset=DATASET, content_type=_ct(model)).values_list("object_id", flat=True)
    return model._base_manager.filter(pk__in=ids)


def register(obj, key: str | None = None) -> None:
    ct = _ct(type(obj))
    if DemoSeedRecord.objects.filter(content_type=ct, object_id=obj.pk).exists():
        return
    DemoSeedRecord.objects.create(dataset=DATASET, key=key or f"{DATASET}:{ct.model}:{obj.pk}", content_type=ct,
                                  object_id=obj.pk)


def lookup(key: str):
    rec = DemoSeedRecord.objects.filter(key=f"{DATASET}:{key}").select_related("content_type").first()
    if rec is None or rec.content_type is None:
        return None
    return rec.content_type.model_class()._base_manager.filter(pk=rec.object_id).first()


def ensure(key: str, create):
    """Объект набора по стабильному ключу: существующий — или созданный и
    зарегистрированный. Повторный запуск возвращает тот же объект."""
    obj = lookup(key)
    if obj is None:
        obj = create()
        register(obj, f"{DATASET}:{key}")
    return obj


def exists() -> bool:
    return DemoSeedRecord.objects.filter(dataset=DATASET).exists()


def meta() -> dict:
    rec = DemoSeedRecord.objects.filter(key=f"{DATASET}:meta").first()
    return rec.meta if rec else {}


# ---------------------------------------------------------------------------
# Календарь сценариев
# ---------------------------------------------------------------------------

def d(month: int, day: int) -> dt.date:
    return dt.date(2026, month, day)


def spread(start: dt.date, end: dt.date, n: int) -> list[dt.date]:
    """n дат урока от start до end включительно (без воскресений), равномерно;
    если дней меньше, чем уроков, — по два урока в день."""
    days = [start + dt.timedelta(i) for i in range((end - start).days + 1)]
    days = [x for x in days if x.weekday() != 6 or x in (start, end)]  # первый и последний день — всегда
    if len(days) >= n:
        return [days[round(i * (len(days) - 1) / (n - 1))] for i in range(n)] if n > 1 else [end]
    out = []
    for i in range(n):
        out.append(days[min(len(days) - 1, i * len(days) // n)])
    out[-1] = days[-1]
    return sorted(out)


@dataclass
class Segment:
    """Уроки одного блока: проведённые даты (+ запланированные на будущее)."""
    dates: list[dt.date]
    scheduled: list[dt.date] = field(default_factory=list)
    substitute_positions: tuple[int, ...] = ()  # номера уроков (с 0), которые ведёт замена


# (группа, предмет) → тренер, замена и блоки. Даты завершения подобраны под
# правило выплаты: 1–15 → 15-е, 16–конец → 1-е следующего месяца.
PLAN = {
    ("G1", "IT"): ("T1", None, [
        Segment(spread(d(8, 1), d(8, 10), 12)),                    # завершён 10.08 → 15.08
        Segment(spread(d(8, 11), d(9, 12), 12)),                   # завершён 12.09 → 15.09
        Segment(spread(d(9, 14), d(10, 9), 8), [d(10, 13), d(10, 15), d(10, 17), d(10, 20)]),  # 8/12 → 20.10 → 01.11
    ]),
    ("G1", "English"): ("T2", None, [
        Segment(spread(d(8, 3), d(8, 20), 12)),                    # 20.08 → 01.09
        Segment(spread(d(8, 21), d(9, 20), 12)),                   # 20.09 → 01.10
        Segment(spread(d(9, 21), d(10, 10), 10), [d(10, 14), d(10, 16)]),  # 10/12
    ]),
    ("G1", "Soft Skills"): ("T3", None, [
        Segment(spread(d(8, 5), d(9, 10), 12)),                    # завершён, правила нет
        Segment(spread(d(9, 11), d(10, 9), 11), [d(10, 16)]),      # 11/12
    ]),
    ("G2", "IT"): ("T1", "T4", [
        Segment(spread(d(8, 5), d(8, 20), 12)),                    # 20.08 → 01.09
        Segment(spread(d(8, 21), d(9, 9), 12), substitute_positions=(4, 5, 6)),  # два тренера, 09.09 → 15.09
        Segment(spread(d(9, 10), d(9, 29), 12)),                   # второй блок за сентябрь → проверка
        Segment(spread(d(9, 30), d(10, 10), 10), [d(10, 13), d(10, 15)]),  # 10/12
    ]),
    ("G2", "English"): ("T2", None, [
        Segment(spread(d(8, 10), d(9, 25), 12)),                   # 25.09 → 01.10
        Segment(spread(d(9, 26), d(10, 10), 12)),                  # 10.10 → 15.10, ставка 9 %
    ]),
    ("G3", "IT"): ("T4", None, [
        Segment(spread(d(8, 3), d(9, 18), 20)),                    # блок 20 уроков, 18.09 → 01.10
        Segment(spread(d(9, 19), d(10, 10), 19), [d(10, 12)]),     # 19/20
    ]),
}
LESSON_HOUR = {"IT": 10, "English": 14, "Soft Skills": 16}

STAFF = {
    # ключ: (роль, имя, фамилия)
    "DIRECTOR": (User.Role.DIRECTOR, "DEMO Директор", "Бухгалтерии"),
    "ACCOUNTANT": (User.Role.ACCOUNTANT, "DEMO Бухгалтер", "Тестовый"),
    "FIX1": (User.Role.ASSISTANT, "DEMO Ассистент", "Окладов"),
    "FIX2": (User.Role.TEAM_LEAD, "DEMO Тимлид", "Ставкин"),
    "T1": (User.Role.TEACHER, "DEMO IT-тренер", "Айтиев"),
    "T2": (User.Role.TEACHER, "DEMO English-тренер", "Инглишева"),
    "T3": (User.Role.TEACHER, "DEMO Soft-тренер", "Безставкин"),
    "T4": (User.Role.TEACHER, "DEMO IT-тренер", "Робототехников"),
}
TEACHERS = ("T1", "T2", "T3", "T4")
GROUPS = {"G1": ("DEMO Prog A", "P", 10), "G2": ("DEMO Prog B", "P", 8), "G3": ("DEMO Robotics", "R", 12)}
COURSES = {"P": ("DEMO Программатика", 144, 12, D("10000")), "R": ("DEMO Robotics", 40, 20, D("8000"))}

# Операции с расчётами: (месяц, период, сотрудник, действие, параметры).
PAYROLL_OPS = [
    ("2026-08", FIRST, "T1", "approve", [(D("10000"), d(8, 15))]),                      # полностью
    ("2026-08", SECOND, "T1", "approve", [(D("8000"), d(9, 1))]),                       # полностью
    ("2026-08", SECOND, "T2", "approve", [(D("5000"), d(9, 1)), (D("3000"), d(9, 10))]),  # двумя платежами
    ("2026-08", MONTH, "FIX1", "approve", [(D("30000"), d(8, 31))]),                    # оклад полностью
    ("2026-08", MONTH, "FIX2", "approve", [(D("20000"), d(9, 5))]),                     # частично, позже даты
    ("2026-09", FIRST, "T1", "approve", [(D("10000"), d(9, 15))]),                      # частично (16 000)
    ("2026-09", FIRST, "T4", "approve", []),                                            # не оплачено
    ("2026-09", FIRST, "T3", "calculate", []),                                          # нет ставки — ошибка
    ("2026-09", SECOND, "T1", "calculate", []),                                         # блок на проверке
    ("2026-09", SECOND, "T2", "approve", [(D("14400"), d(10, 1))]),
    ("2026-09", SECOND, "T4", "approve", [(D("10000"), d(10, 1))]),                     # частично
    ("2026-09", SECOND, "T3", "calculate", []),
    ("2026-09", MONTH, "FIX1", "approve", [(D("20000"), d(9, 30))]),                    # частично
    ("2026-09", MONTH, "FIX2", "approve", []),                                          # не оплачено
    ("2026-10", FIRST, "T2", "calculate", []),                                          # ждёт утверждения
    ("2026-10", MONTH, "FIX1", "calculate", []),
    ("2026-10", MONTH, "FIX2", "calculate", []),
]


# ---------------------------------------------------------------------------
# Генерация
# ---------------------------------------------------------------------------

@dataclass
class Context:
    seed: int
    today: dt.date
    cutoff: dt.date
    months: list[str]
    demo_password: str | None
    users: dict = field(default_factory=dict)
    teachers: dict = field(default_factory=dict)
    subjects: dict = field(default_factory=dict)
    courses: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)
    programs: dict = field(default_factory=dict)
    previous_cutoff: dt.date | None = None


def _user(ctx: Context, key: str):
    role, first, last = STAFF[key]
    username = f"demo_acc_{key.lower()}"
    existing = User.objects.filter(username=username).first()
    if existing is not None and lookup(f"user:{key}") is None:
        raise SeedError(f"Пользователь «{username}» уже есть и не относится к тестовому набору — генератор его не трогает.")

    def create():
        user = User(username=username, email=f"{username}@demo.okurmenkids.invalid", first_name=first,
                    last_name=last, role=role, is_verified=True, is_active=True)
        user.set_password(ctx.demo_password) if ctx.demo_password else user.set_unusable_password()
        user.save()
        return user

    return ensure(f"user:{key}", create)


def _subject(name: str):
    subject = Subject.objects.filter(name__iexact=name).first()
    if subject is not None:
        return subject  # общий справочник — используется, но не регистрируется
    return ensure(f"subject:{name}", lambda: Subject.objects.create(name=name, description="DEMO"))


def build_reference(ctx: Context) -> None:
    from .pricing import set_price
    from .salary_rules import create_rule, new_version

    for key in STAFF:
        ctx.users[key] = _user(ctx, key)
    for name in ("IT", "English", "Soft Skills"):
        ctx.subjects[name] = _subject(name)
    for key in TEACHERS:
        user = ctx.users[key]
        ctx.teachers[key] = ensure(f"teacher:{key}", lambda u=user: Teacher.objects.create(user=u, position="DEMO тренер"))
    actor = ctx.users["ACCOUNTANT"]
    for ckey, (name, total, block, price) in COURSES.items():
        if Course.objects.filter(name=name).exists() and lookup(f"course:{ckey}") is None:
            raise SeedError(f"Курс «{name}» уже существует и не относится к тестовому набору.")
        course = ensure(f"course:{ckey}", lambda n=name, t=total: Course.objects.create(name=n, count_lesson=t,
                                                                                         description="DEMO"))
        ctx.courses[ckey] = course
        subjects = ["IT", "English", "Soft Skills"] if ckey == "P" else ["IT"]
        course.subjects.add(*[ctx.subjects[s] for s in subjects])
        per_subject = total // len(subjects)  # 144 = 48 + 48 + 48; Robotics — 40 IT
        number = 0
        for s in subjects:
            for i in range(per_subject):
                number += 1
                ensure(f"plan:{ckey}:{number}", lambda c=course, n=number, sub=ctx.subjects[s], i=i: CourseLessonPlan.objects.create(
                    course=c, lesson_number=n, subject=sub, topic=f"DEMO {sub.name} — тема {i + 1}"))
        settings = ensure(f"settings:{ckey}", lambda c=course, b=block, p=price: CoursePayrollSettings.objects.create(
            course=c, price_per_student=p, required_lessons=b))
        if lookup(f"price:{ckey}") is None:
            version = set_price(course=course, price_per_student=price, effective_from=d(1, 1),
                                reason="DEMO: стоимость обучения за ученика в месяц", actor=actor)
            register(version, f"{DATASET}:price:{ckey}")
        assert settings.pk
    rng = random.Random(ctx.seed)
    first_names = ["Айбек", "Алина", "Бекзат", "Дана", "Эрлан", "Жибек", "Нурсултан", "Айпери", "Тимур", "Камила",
                   "Санжар", "Асель", "Мирлан", "Айгерим"]
    for gkey, (name, ckey, students) in GROUPS.items():
        if Group.objects.filter(name=name).exists() and lookup(f"group:{gkey}") is None:
            raise SeedError(f"Группа «{name}» уже существует и не относится к тестовому набору.")
        group = ensure(f"group:{gkey}", lambda n=name, c=ckey: Group.objects.create(
            name=n, course=ctx.courses[c], start_date=d(8, 1), description="DEMO"))
        ctx.groups[gkey] = group
        for i in range(students):
            fname = rng.choice(first_names)
            ensure(f"student:{gkey}:{i}", lambda g=group, f=fname, i=i: Student.objects.create(
                first_name=f, last_name=f"DEMO-{g.pk}-{i + 1}", group=g, enrollment_date=d(7, 25)))
    # Состав меняется: в Robotics одна ученица выбывает 01.09.
    leaver = lookup("student:G3:0")
    if lookup("event:G3:leave") is None and d(9, 1) <= ctx.cutoff:
        event = StudentStatusEvent.objects.create(
            student=leaver, event_type=StudentStatusEvent.EventType.DEACTIVATED,
            reason=StudentStatusEvent.Reason.RELOCATION, previous_status=Student.Status.ACTIVE, group=leaver.group,
            event_date=d(9, 1), comment="DEMO")
        register(event, f"{DATASET}:event:G3:leave")
        Student.objects.filter(pk=leaver.pk).update(status=Student.Status.WITHDRAWN, is_active=False)
    # Программы (предмет → тренер) групп.
    for (gkey, subject), (tkey, _, _) in PLAN.items():
        ctx.programs[(gkey, subject)] = ensure(
            f"program:{gkey}:{subject}", lambda g=ctx.groups[gkey], t=ctx.teachers[tkey], s=ctx.subjects[subject]:
            GroupTeacher.objects.create(group=g, teacher=t, subject=s))
    # Зарплатные профили и правила (у Soft Skills-тренера правила нет — сценарий ошибки).
    profiles = {
        "FIX1": ("FIXED", "", None), "FIX2": ("FIXED", "", None),
        "T1": ("PERCENT", "IT", None), "T2": ("PERCENT", "ENGLISH", None),
        "T3": ("PERCENT", "SOFT_SKILLS", None), "T4": ("PERCENT", "IT", None),
    }
    for key, (salary_type, department, _) in profiles.items():
        ensure(f"profile:{key}", lambda u=ctx.users[key], st=salary_type, dep=department:
               EmployeeSalaryProfile.objects.create(employee=u, salary_type=st, department=dep,
                                                    effective_from=d(8, 1), position="DEMO"))
    rules = [
        ("FIX1", "FIXED", {"amount": D("30000")}), ("FIX2", "FIXED", {"amount": D("35000")}),
        ("T1", "PERCENT", {"percentage": D("10")}), ("T2", "PERCENT", {"percentage": D("8")}),
        ("T4", "PERCENT", {"percentage": D("14")}),
    ]
    for key, rtype, values in rules:
        if lookup(f"rule:{key}") is None:
            rule = create_rule(actor=actor, data={
                "employee_profile": lookup(f"profile:{key}"), "rule_type": rtype, "effective_from": d(8, 1),
                "calculation_method": SalaryRule.METHODS_BY_TYPE[rtype][0], "description": "DEMO", **values})
            register(rule, f"{DATASET}:rule:{key}")
    # Смена ставки с сохранением истории.
    for key, start, values in (("FIX2", d(9, 1), {"amount": D("40000")}), ("T2", d(10, 1), {"percentage": D("9")})):
        if lookup(f"rule:{key}:v2") is None and start <= ctx.cutoff:
            rule = new_version(lookup(f"rule:{key}"), actor=actor, changes={"effective_from": start, **values})
            register(rule, f"{DATASET}:rule:{key}:v2")


def build_lessons(ctx: Context) -> None:
    counters: dict = defaultdict(int)
    for (gkey, subject), (tkey, sub_key, segments) in PLAN.items():
        program = ctx.programs[(gkey, subject)]
        n = 0
        for bi, segment in enumerate(segments):
            items = [(x, True) for x in segment.dates] + [(x, False) for x in segment.scheduled]
            per_day: Counter = Counter()
            for li, (day, _planned) in enumerate(items):
                n += 1
                # Уроки — в пределах выбранных месяцев; при генерации октября
                # оставшиеся уроки октября создаются запланированными.
                if not (day <= ctx.cutoff or ("2026-10" in ctx.months and day.month == 10)):
                    continue
                completed = day <= ctx.today
                hour = LESSON_HOUR[subject] + per_day[day]
                per_day[day] += 1
                teacher = ctx.teachers[sub_key] if sub_key and li in segment.substitute_positions else ctx.teachers[tkey]
                key = f"lesson:{gkey}:{subject}:{n}"
                lesson = lookup(key)
                if lesson is None:
                    lesson = Lesson.objects.create(
                        group=ctx.groups[gkey], group_teacher=program, teacher=teacher, subject=ctx.subjects[subject],
                        lesson_number=n, date=day, start_time=dt.time(hour), end_time=dt.time(hour + 1),
                        status=Lesson.Status.COMPLETED if completed else Lesson.Status.SCHEDULED,
                        topic=f"DEMO {subject}, блок {bi + 1}, урок {li + 1}",
                    )
                    register(lesson, f"{DATASET}:{key}")
                elif completed and lesson.status == Lesson.Status.SCHEDULED:
                    lesson.status = Lesson.Status.COMPLETED  # урок набора наступил с прошлого запуска
                    lesson.save(update_fields=["status", "updated_at"])
                counters[(gkey, subject)] += 1


def sync_demo_cycles(ctx: Context) -> None:
    from .cycles import sync_group

    for gkey, group in ctx.groups.items():
        settings = CoursePayrollSettings.objects.get(course=group.course)
        sync_group(group, settings, actor=ctx.users["ACCOUNTANT"])


def run_payroll_ops(ctx: Context) -> None:
    from .approval_service import approve_payroll
    from .payment_service import register_payment
    from .payroll_calculator import calculate_payroll
    from .periods import get_or_create_period

    accountant, director = ctx.users["ACCOUNTANT"], ctx.users["DIRECTOR"]
    for month, half, ekey, action, payments in PAYROLL_OPS:
        if month not in ctx.months:
            continue
        year, mon = MONTHS[month]
        start, end = PayrollPeriod.bounds(year, mon, half)
        if start > ctx.cutoff:
            continue
        period, created = get_or_create_period(year, mon, half, accountant)
        if created:
            register(period, f"{DATASET}:period:{month}:{half}")
        employee = ctx.users[ekey]
        payroll = Payroll.objects.filter(period=period, employee=employee).first()
        # Пересчёт — только если расчёта нет или данные продвинулись с прошлого
        # запуска: повторный запуск с теми же параметрами ничего не меняет.
        advanced = ctx.previous_cutoff is None or ctx.cutoff > ctx.previous_cutoff
        if payroll is None or (payroll.is_editable and advanced):
            payroll = calculate_payroll(period, employee, accountant, sync=False)
        if action == "approve" and payroll.status == Payroll.Status.CALCULATED and end <= ctx.cutoff:
            if not payroll.errors:
                payroll = approve_payroll(payroll, director)
        for i, (amount, day) in enumerate(payments):
            if day > ctx.cutoff or payroll.status not in Payroll.LOCKED_STATUSES:
                continue
            key = f"{DATASET}:pay:{month}:{half}:{ekey}:{i}"
            register_payment(payroll, amount=amount, payment_date=day, actor=accountant,
                             payment_method=PayrollPayment.Method.BANK, reference=f"DEMO-{month}-{half[:1]}-{ekey}-{i + 1}",
                             comment="DEMO", idempotency_key=hashlib.sha1(key.encode()).hexdigest())


def build_student_payments(ctx: Context) -> None:
    accountant = ctx.users["ACCOUNTANT"]
    for month in ctx.months:
        year, mon = MONTHS[month]
        received = dt.date(year, mon, 5)
        if received > ctx.cutoff:
            continue
        for rec in DemoSeedRecord.objects.filter(dataset=DATASET, key__startswith=f"{DATASET}:student:"):
            student = Student.objects.get(pk=rec.object_id)
            if student.status != Student.Status.ACTIVE and mon > 8:
                continue
            course = student.group.course
            price = COURSES["P" if course == ctx.courses["P"] else "R"][3]
            key = f"stpay:{rec.key.split(':', 2)[2]}:{month}"
            ensure(key, lambda s=student, p=price, r=received: StudentPayment.objects.create(
                student=s, group=s.group, course=s.group.course, amount=p, received_date=r,
                service_start=r.replace(day=1), service_end=r.replace(day=28), reference=f"DEMO-{s.pk}-{r:%m}",
                comment="DEMO", created_by=accountant))
    # Возврат выбывшей ученице за август (частичный).
    original = lookup("stpay:student:G3:0:2026-08")
    if original is not None and lookup("stpay:refund:G3:0") is None and d(9, 3) <= ctx.cutoff:
        refund = StudentPayment.objects.create(
            student=original.student, group=original.group, course=original.course, kind=StudentPayment.Kind.REFUND,
            amount=D("4000"), received_date=d(9, 3), service_start=original.service_start,
            service_end=original.service_end, refund_of=original, comment="DEMO возврат", created_by=accountant)
        register(refund, f"{DATASET}:stpay:refund:G3:0")


def register_scope(ctx: Context) -> None:
    """Зарегистрировать записи, которые создали сервисы и сигналы (циклы,
    начисления, строки, журнал, назначения тренеров…) — по связи с объектами
    набора, а не по именам."""
    users = list(registered(User).values_list("pk", flat=True))
    groups = list(registered(Group).values_list("pk", flat=True))
    courses = list(registered(Course).values_list("pk", flat=True))
    scope = [
        TrainerAssignment.objects.filter(group_id__in=groups),
        StudentStatusEvent.objects.filter(student__group_id__in=groups),
        CourseCycle.objects.filter(group_id__in=groups),
        CycleLesson.objects.filter(cycle__group_id__in=groups),
        CycleAccrual.objects.filter(employee_id__in=users),
        Payroll.objects.filter(employee_id__in=users),
        PayrollLine.objects.filter(payroll__employee_id__in=users),
        PayrollPayment.objects.filter(payroll__employee_id__in=users),
        PayrollAdjustment.objects.filter(payroll__employee_id__in=users),
        EmployeeSalaryProfile.objects.filter(employee_id__in=users),
        SalaryRule.objects.filter(employee_profile__employee_id__in=users),
        CoursePriceVersion.objects.filter(course_id__in=courses),
        StudentPayment.objects.filter(student__group_id__in=groups),
    ]
    for qs in scope:
        for obj in qs.model._base_manager.filter(pk__in=qs.values("pk")):
            register(obj)
    by_type: dict[str, set] = defaultdict(set)
    for rec in DemoSeedRecord.objects.filter(dataset=DATASET, content_type__isnull=False).select_related("content_type"):
        by_type[rec.content_type.model].add(rec.object_id)
    payrolls = by_type.get("payroll", set())
    for log in PayrollAuditLog.objects.filter(payroll_id__in=payrolls):
        register(log)
    for model_name, ids in by_type.items():
        for log in PayrollAuditLog.objects.filter(entity_type=model_name, entity_id__in=ids):
            register(log)


def generate(*, seed: int = 42, months: list[str], today: dt.date, demo_password: str | None = None,
             dry_run: bool = False) -> dict:
    """Создать (или дополнить) набор. Возвращает сводку и проверки."""
    if not months:
        raise SeedError("Не выбран ни один месяц.")
    existing = meta()
    if existing and existing.get("seed") != seed:
        raise SeedError(f"Набор уже создан с --seed {existing.get('seed')}. Чтобы пересоздать с другим seed, "
                        "сначала выполните --clear.")
    last_month = max(months)
    year, mon = MONTHS[last_month]
    month_end = dt.date(year, mon, 28) + dt.timedelta(days=4)
    month_end -= dt.timedelta(days=month_end.day)
    cutoff = min(month_end, today)
    ordered = [m for m in MONTHS if m <= last_month]  # месяц включает предыдущие: циклы переходят через границы
    ctx = Context(seed=seed, today=today, cutoff=cutoff, months=ordered, demo_password=demo_password,
                  previous_cutoff=dt.date.fromisoformat(existing["cutoff"]) if existing.get("cutoff") else None)
    before = counts()
    with transaction.atomic():
        build_reference(ctx)
        build_lessons(ctx)
        sync_demo_cycles(ctx)
        build_student_payments(ctx)
        run_payroll_ops(ctx)
        register_scope(ctx)
        rec, _ = DemoSeedRecord.objects.get_or_create(key=f"{DATASET}:meta", defaults={"dataset": DATASET})
        prev = rec.meta.get("cutoff")
        rec.meta = {"seed": seed, "months": sorted(set(rec.meta.get("months", [])) | set(ordered)),
                    "cutoff": max(cutoff.isoformat(), prev or ""), "today": today.isoformat()}
        rec.save()
        problems = verify()
        if problems:
            raise SeedError("Проверка целостности не пройдена: " + "; ".join(problems))
        result = {"created": {k: v - before.get(k, 0) for k, v in counts().items() if v != before.get(k, 0)},
                  "summary": summary(), "fingerprint": fingerprint(), "cutoff": cutoff, "months": ordered}
        if dry_run:
            transaction.set_rollback(True)
    return result


# ---------------------------------------------------------------------------
# Сводка и проверки
# ---------------------------------------------------------------------------

def counts() -> dict[str, int]:
    out = Counter()
    for rec in DemoSeedRecord.objects.filter(dataset=DATASET, content_type__isnull=False).select_related("content_type"):
        out[rec.content_type.model] += 1
    return dict(out)


def _payroll_rows():
    return registered(Payroll).select_related("period", "employee").order_by("period__start_date", "employee_id")


def summary() -> dict:
    payrolls = list(_payroll_rows())
    per_month: dict = {}
    for m in MONTHS:
        year, mon = MONTHS[m]
        rows = [p for p in payrolls if (p.period.year, p.period.month) == (year, mon) and p.status != Payroll.Status.VOID]
        locked = [p for p in rows if p.is_locked]
        accrued = sum((p.total_accrued + p.total_adjustments for p in locked), ZERO)
        paid = sum((p.total_paid for p in locked), ZERO)
        cash = registered(PayrollPayment).filter(
            status=PayrollPayment.Status.CONFIRMED, payment_date__year=year, payment_date__month=mon,
        ).aggregate(s=Sum("amount"))["s"] or ZERO
        per_month[m] = {
            "accrued": accrued, "paid": paid, "outstanding": accrued - paid,
            "awaiting_approval": sum((p.total_accrued + p.total_adjustments for p in rows
                                      if p.status == Payroll.Status.CALCULATED), ZERO),
            "with_errors": sum(1 for p in rows if p.errors), "cash_paid_in_month": cash, "payrolls": len(rows),
        }
    from .estimates import _estimate_rows

    open_cycles = registered(CourseCycle).filter(status=CourseCycle.Status.IN_PROGRESS).select_related(
        "group", "course", "subject")
    today = dt.date.fromisoformat(meta().get("today") or dt.date.today().isoformat())
    estimates = [row for c in open_cycles for row in _estimate_rows(c, today) if c.lessons_done]
    cycles = registered(CourseCycle).filter(per_subject=True)
    staff = registered(User)
    return {
        "employees": staff.exclude(role__in=(User.Role.DIRECTOR, User.Role.ACCOUNTANT)).count(),
        "staff_users": staff.count(),
        "salary_rules": registered(SalaryRule).count(),
        "subject_cycles": cycles.exclude(status=CourseCycle.Status.INVALIDATED).count(),
        "completed_blocks": cycles.filter(status=CourseCycle.Status.COMPLETED).count(),
        "open_blocks": cycles.filter(status=CourseCycle.Status.IN_PROGRESS, lessons_done__gt=0).count(),
        "lessons": registered(Lesson).count(),
        "estimates": len(estimates),
        "review_required": registered(CycleAccrual).filter(status=CycleAccrual.Status.REVIEW_REQUIRED).count(),
        "months": per_month,
        "total_outstanding": sum((v["outstanding"] for v in per_month.values()), ZERO),
    }


def verify() -> list[str]:
    """Проверки целостности набора (пустой список — всё сходится)."""
    problems = []
    accruals = registered(CycleAccrual)
    dup = accruals.values("cycle_id", "employee_id").annotate(n=models.Count("id")).filter(n__gt=1)
    if dup.exists():
        problems.append(f"дубли начислений за циклы: {list(dup)}")
    for p in _payroll_rows():
        lines = p.lines.aggregate(s=Sum("amount"))["s"] or ZERO
        adj = p.adjustments.filter(status=PayrollAdjustment.Status.APPLIED).aggregate(s=Sum("amount"))["s"] or ZERO
        paid = p.payments.filter(status=PayrollPayment.Status.CONFIRMED).aggregate(s=Sum("amount"))["s"] or ZERO
        if lines != p.total_accrued:
            problems.append(f"расчёт #{p.pk}: сумма строк {lines} ≠ начислено {p.total_accrued}")
        if paid != p.total_paid or p.amount_due != lines + adj - paid:
            problems.append(f"расчёт #{p.pk}: остаток {p.amount_due} ≠ {lines} + {adj} − {paid}")
        if paid > lines + adj:
            problems.append(f"расчёт #{p.pk}: переплата {paid} > {lines + adj}")
        if paid and not p.is_locked:
            problems.append(f"расчёт #{p.pk}: выплаты по неутверждённому расчёту")
    for link in registered(CycleLesson).select_related("cycle", "lesson"):
        if link.lesson and link.lesson.subject_id != link.cycle.subject_id:
            problems.append(f"урок {link.lesson_ref} другого предмета в цикле #{link.cycle_id}")
    for c in registered(CourseCycle).filter(status=CourseCycle.Status.COMPLETED, per_subject=True):
        if c.cycle_lessons.filter(is_live=True).count() != c.required_lessons:
            problems.append(f"цикл #{c.pk}: связано уроков {c.cycle_lessons.count()} ≠ {c.required_lessons}")
    for a in accruals.exclude(status=CycleAccrual.Status.CANCELLED):
        numerator = a.lessons_taught if a.lessons_taught is not None else a.lessons
        expected = money(a.course_price * a.student_count * a.percentage * numerator / (D(100) * a.lessons))
        if expected != a.amount:
            problems.append(f"начисление за цикл #{a.pk}: {a.amount} ≠ формула {expected}")
    return problems


def fingerprint() -> str:
    """Отпечаток набора: количества и суммы — одинаковый при повторном запуске."""
    data = {
        "counts": counts(),
        "payrolls": [(p.period.year, p.period.month, p.period.period_type, p.employee.username, str(p.total_accrued),
                      str(p.total_paid), p.status) for p in _payroll_rows()],
        "accruals": sorted((a.cycle.group.name, a.cycle.subject.name if a.cycle.subject else "", a.cycle.number,
                            a.employee.username, str(a.amount), a.status)
                           for a in registered(CycleAccrual).select_related("cycle__group", "cycle__subject", "employee")),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Очистка
# ---------------------------------------------------------------------------

# Порядок удаления: сначала те, кто ссылается на других.
CLEAR_ORDER = (
    CycleAccrual, PayrollAuditLog, PayrollPayment, PayrollAdjustment, PayrollLine, Payroll, PayrollPeriod,
    CycleLesson, CourseCycle, SalaryRule, EmployeeSalaryProfile, CoursePriceVersion, CoursePayrollSettings,
    StudentPayment, Lesson, StudentStatusEvent, Student, TrainerAssignment, GroupTeacher, Group, CourseLessonPlan,
    Course, Teacher, Subject, User,
)
SELF_CHAINS = {SalaryRule: "next_version", CoursePriceVersion: "next_version", StudentPayment: "refunds"}


def _registered_ids() -> dict[type, set[int]]:
    out: dict[type, set[int]] = defaultdict(set)
    for rec in DemoSeedRecord.objects.filter(dataset=DATASET, content_type__isnull=False).select_related("content_type"):
        model = rec.content_type.model_class()
        if model is None:
            raise SeedError(f"В реестре есть запись неизвестной модели: {rec.key}.")
        out[model].add(rec.object_id)
    return out


def foreign_dependents(ids: dict[type, set[int]]) -> list[str]:
    """Незарегистрированные записи, которые удаление набора задело бы:
    ссылаются на объекты набора (CASCADE / PROTECT / SET_NULL) или связаны с
    ними через M2M со стороны «чужого» объекта."""
    problems = []
    for model, pks in ids.items():
        if model is PayrollPeriod:
            continue  # общие периоды проверяются отдельно (их не удаляем, если ими пользуются)
        for rel in model._meta.related_objects:
            related = rel.related_model
            if rel.many_to_many:
                through = rel.through if hasattr(rel, "through") else rel.field.remote_field.through
                if not through._meta.auto_created:
                    continue
                source_field = next(f for f in through._meta.fields if f.is_relation and f.related_model is related)
                target_field = next(f for f in through._meta.fields if f.is_relation and f.related_model is model
                                    and f is not source_field)
                rows = through.objects.filter(**{f"{target_field.attname}__in": pks}).values_list(
                    source_field.attname, flat=True)
                foreign = set(rows) - ids.get(related, set())
                if foreign:
                    problems.append(f"{related._meta.label} ({len(foreign)}) связаны с {model._meta.label} через "
                                    f"{rel.field.name}")
                continue
            field_name = rel.field.name
            refs = set(related._base_manager.filter(**{f"{field_name}__in": pks}).values_list("pk", flat=True))
            foreign = refs - ids.get(related, set())
            if foreign:
                problems.append(f"{related._meta.label}: {len(foreign)} незарегистр. записей ссылаются на "
                                f"{model._meta.label} ({field_name}), например #{min(foreign)}")
    return problems


def _delete_leaf_first(model, pks: set[int], reverse_name: str) -> int:
    total = 0
    while True:
        remaining = model._base_manager.filter(pk__in=pks)
        if not remaining.exists():
            return total
        n, _ = model.objects.filter(pk__in=pks).filter(**{f"{reverse_name}__isnull": True}).delete()
        if not n:
            raise SeedError(f"Не удалось удалить {model._meta.label}: циклическая ссылка.")
        total += n


def clear(*, dry_run: bool = False) -> dict[str, int]:
    """Удалить только зарегистрированные записи набора. Останавливается, если
    удаление задело бы незарегистрированные данные."""
    with transaction.atomic():
        ids = _registered_ids()
        problems = foreign_dependents(ids)
        if problems:
            raise SeedError("Очистка остановлена: удаление задело бы данные вне тестового набора — "
                            + "; ".join(problems))
        unknown = set(ids) - set(CLEAR_ORDER)
        if unknown:
            raise SeedError(f"В реестре есть модели, которые генератор не умеет удалять: {sorted(m.__name__ for m in unknown)}")
        deleted: dict[str, int] = {}
        kept_periods = 0
        with maintenance_delete():
            for model in CLEAR_ORDER:
                pks = ids.get(model, set())
                if not pks:
                    continue
                if model is PayrollPeriod:
                    used = set(Payroll._base_manager.filter(period_id__in=pks).values_list("period_id", flat=True))
                    kept_periods = len(used)
                    if used:
                        # Период, созданный генератором, уже используют реальные
                        # расчёты: он общий — остаётся, выходит из набора и
                        # перестаёт ссылаться на DEMO-пользователей.
                        PayrollPeriod.objects.filter(pk__in=used).update(created_by=None, approved_by=None)
                        DemoSeedRecord.objects.filter(content_type=_ct(PayrollPeriod), object_id__in=used).delete()
                    pks = pks - used
                    if not pks:
                        continue
                if model in SELF_CHAINS:
                    n = _delete_leaf_first(model, pks, SELF_CHAINS[model])
                    deleted[model._meta.label] = n
                    continue
                _, per_model = model.objects.filter(pk__in=pks).delete()
                for label, n in per_model.items():
                    deleted[label] = deleted.get(label, 0) + n
        # Удалено ровно зарегистрированное (связи M2M собственных объектов — не в счёт).
        for model, pks in ids.items():
            label = model._meta.label
            expected = len(pks) - (kept_periods if model is PayrollPeriod else 0)
            if deleted.get(label, 0) != expected:
                raise SeedError(f"Очистка отменена: {label} удалено {deleted.get(label, 0)}, ожидалось {expected}.")
            leftover = model._base_manager.filter(pk__in=pks).count()
            if leftover and model is not PayrollPeriod:
                raise SeedError(f"Очистка отменена: остались записи {label} ({leftover}).")
        from django.apps import apps as django_apps

        own = {m._meta.label for m in ids}
        extra = {label: n for label, n in deleted.items()
                 if label not in own and not django_apps.get_model(label)._meta.auto_created}
        if extra:
            raise SeedError(f"Очистка отменена: каскадом задеты незарегистрированные модели {extra}.")
        DemoSeedRecord.objects.filter(dataset=DATASET).delete()
        if dry_run:
            transaction.set_rollback(True)
    return deleted
