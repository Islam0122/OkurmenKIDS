"""Демо-набор финансового модуля (manage.py seed_billing_demo / reset_billing_demo).

Данные создаются настоящими сервисами оплаты — договор, бронь, платежи,
проведённые уроки, распределения, чеки — поэтому учебные месяцы, начисления,
сроки, долги и аналитика получаются теми же, что и в работе академии. Ничего
не «рисуется» в таблицах: статусы — следствие уроков и денег.

Безопасность
* Демо-записи определяются ТОЛЬКО реестром `accounting.DemoSeedRecord`
  (набор `billing_demo`), а не по именам. Реальные программы, группы,
  студенты и платежи не изменяются: под сценарии создаются отдельные
  «[DEMO]» программы, тарифы, группы, студенты и пользователи. Общие
  справочники (предметы IT / English) переиспользуются и не регистрируются.
* Каждый объект создаётся через `ensure(key)`, каждый сценарий — один раз
  (ключ `scenario:X`): повторный запуск ничего не дублирует.
* Очистка (`reset`) сначала добавляет в реестр всё, что принадлежит
  демо-студентам и демо-группам (в т.ч. платежи, внесённые вручную при
  проверке интерфейса), затем удаляет только зарегистрированное и
  останавливается, если удаление задело бы хоть одну запись вне набора
  (например, реальный платёж, принятый под демо-бухгалтером). Всё — в одной
  транзакции, после удаления сверяются количества.
* Не запускается при DJANGO_ENV=production. Пароли демо-пользователей не
  задаются: вход закрыт, пока их не задаст `billing_demo_passwords`.
"""
from __future__ import annotations

import datetime as dt
import os
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.academy.models import Attendance, Course, Group, GroupTeacher, Lesson, Student
from apps.accounting.models import DemoSeedRecord, PayrollAuditLog, StudentPayment, maintenance_delete
from apps.accounting.services.demo_seed import foreign_dependents
from apps.users.models import Subject, Teacher, User

from ..models import (
    BillingEvent,
    BillingPlan,
    BillingPlanVersion,
    Invoice,
    PaymentMode,
    ReservationAllocation,
    StudentBillingProfile,
)
from . import BillingError

DATASET = "billing_demo"
D = Decimal
START_OFFSET_DAYS = 70  # договоры демо-студентов начинаются 70 дней назад


class DemoError(BillingError):
    pass


def ensure_allowed() -> None:
    if os.environ.get("DJANGO_ENV") == "production":
        raise DemoError("Демо-набор не создаётся и не удаляется в production (DJANGO_ENV=production).",
                        code="forbidden_env")


# ---------------------------------------------------------------------------
# Реестр (общий с генератором бухгалтерии, свой набор)
# ---------------------------------------------------------------------------

def _ct(model) -> ContentType:
    return ContentType.objects.get_for_model(model, for_concrete_model=False)


def register(obj, key: str | None = None) -> bool:
    ct = _ct(type(obj))
    existing = DemoSeedRecord.objects.filter(content_type=ct, object_id=obj.pk).first()
    if existing is not None:
        if existing.dataset != DATASET:
            raise DemoError(f"{obj!r} уже принадлежит набору «{existing.dataset}».")
        return False
    DemoSeedRecord.objects.create(dataset=DATASET, key=key or f"{DATASET}:{ct.model}:{obj.pk}", content_type=ct,
                                  object_id=obj.pk)
    return True


def lookup(key: str):
    rec = DemoSeedRecord.objects.filter(key=f"{DATASET}:{key}").select_related("content_type").first()
    if rec is None or rec.content_type is None:
        return None
    return rec.content_type.model_class()._base_manager.filter(pk=rec.object_id).first()


def ensure(key: str, create):
    obj = lookup(key)
    if obj is None:
        obj = create()
        register(obj, f"{DATASET}:{key}")
    return obj


def registered(model):
    ids = DemoSeedRecord.objects.filter(dataset=DATASET, content_type=_ct(model)).values_list("object_id", flat=True)
    return model._base_manager.filter(pk__in=ids)


def exists() -> bool:
    return DemoSeedRecord.objects.filter(dataset=DATASET).exists()


def _mark(key: str, **meta) -> None:
    DemoSeedRecord.objects.get_or_create(dataset=DATASET, key=f"{DATASET}:{key}", defaults={"meta": meta})


def _marked(key: str) -> bool:
    return DemoSeedRecord.objects.filter(key=f"{DATASET}:{key}").exists()


# ---------------------------------------------------------------------------
# Справочники: пользователи, программы, группы
# ---------------------------------------------------------------------------

USERS = {
    "accountant": ("demo_accountant", User.Role.ACCOUNTANT, "Демо", "Бухгалтер"),
    "manager": ("demo_manager", User.Role.ASSISTANT, "Демо", "Менеджер"),
    "director": ("demo_director", User.Role.DIRECTOR, "Демо", "Директор"),
    "trainer": ("demo_billing_trainer", User.Role.TEACHER, "Демо", "Тренер IT"),
}

# Демо-программы: (название, цена месяца, месяцев, уроков IT в месяце).
PROGRAMS = {
    "standard": ("[DEMO] Kid's Club Standard", D("15000"), 4, 12),
    "next": ("[DEMO] Kid's Club Next", D("15000"), 6, 12),
    "discount": ("[DEMO] Kid's Club Discount Demo", D("15000"), 4, 12),
}


@dataclass
class Ctx:
    today: dt.date
    start: dt.date
    users: dict = field(default_factory=dict)
    subjects: dict = field(default_factory=dict)
    courses: dict = field(default_factory=dict)
    plans: dict = field(default_factory=dict)
    teacher: Teacher | None = None
    created: list = field(default_factory=list)

    @property
    def accountant(self) -> User:
        return self.users["accountant"]


def _user(key: str) -> User:
    username, role, first, last = USERS[key]
    if User.objects.filter(username=username).exists() and lookup(f"user:{key}") is None:
        raise DemoError(f"Пользователь «{username}» уже есть и не относится к демо-набору — генератор его не трогает.")

    def create():
        user = User(username=username, email=f"{username}@demo.okurmenkids.invalid", first_name=first, last_name=last,
                    role=role, is_verified=True, is_active=True)
        user.set_unusable_password()  # вход — только после billing_demo_passwords
        user.save()
        return user

    return ensure(f"user:{key}", create)


def _subject(name: str) -> Subject:
    subject = Subject.objects.filter(name__iexact=name).first()
    if subject is not None:
        return subject  # общий справочник — используется, но не регистрируется
    return ensure(f"subject:{name}", lambda: Subject.objects.create(name=name, description="DEMO"))


def build_reference(ctx: Ctx) -> None:
    from .pricing import create_plan

    for key in USERS:
        ctx.users[key] = _user(key)
    for name in ("IT", "English"):
        ctx.subjects[name] = _subject(name)
    trainer_user = ctx.users["trainer"]
    ctx.teacher = ensure("teacher", lambda: Teacher.objects.create(user=trainer_user, position="DEMO тренер"))
    for key, (name, month_price, months, lessons) in PROGRAMS.items():
        if Course.objects.filter(name=name).exists() and lookup(f"course:{key}") is None:
            raise DemoError(f"Курс «{name}» уже есть и не относится к демо-набору.")

        def make_course(name=name, months=months, lessons=lessons):
            course = Course.objects.create(name=name, count_lesson=months * lessons * 2,
                                           description="DEMO: программа для проверки оплаты")
            course.subjects.set([ctx.subjects["IT"], ctx.subjects["English"]])
            return course

        ctx.courses[key] = ensure(f"course:{key}", make_course)
        if BillingPlan.objects.filter(name=name).exists() and lookup(f"plan:{key}") is None:
            raise DemoError(f"Тариф «{name}» уже есть и не относится к демо-набору.")
        ctx.plans[key] = ensure(f"plan:{key}", lambda name=name, key=key, month_price=month_price, months=months,
                                lessons=lessons: create_plan(
            actor=ctx.accountant, name=name, subject=ctx.subjects["IT"], course=ctx.courses[key],
            lessons_per_package=lessons, package_price=month_price, effective_from=ctx.start - dt.timedelta(days=30),
            duration_months=months, payment_deadline_lessons=3, reason="DEMO: демонстрационная цена",
        ))
        version = ctx.plans[key].versions.first()
        if version is not None:
            register(version)


# ---------------------------------------------------------------------------
# Сценарии A–O
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    key: str
    first: str
    last: str
    program: str
    title: str
    check: str
    contract: dict = field(default_factory=dict)
    # Шаги: ("res", сумма) оплата брони; ("pay", сумма[, режим]) платёж;
    # ("it", n) / ("en", n) провести n уроков IT / English; ("refund", сумма);
    # ("call", результат) контакт с родителем.
    steps: tuple = ()


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("A", "Алия", "Демонова", "standard", "Курс оплачен полностью",
             "Оплачено 60 000 из 60 000 (предоплата за весь курс); будущие месяцы — не долг.",
             {"payment_mode": PaymentMode.FULL_PREPAY}, (("pay", "60000"), ("it", 15))),
    Scenario("B", "Бекзат", "Тестов", "standard", "Оплачен один месяц, начался второй",
             "Месяц 1 оплачен и пройден (12 уроков IT) — месяц 2 в «К оплате» (15 000).",
             {}, (("pay", "15000"), ("it", 12))),
    Scenario("C", "Самира", "Скидкина", "discount", "Скидка 15 000 сом",
             "60 000 → итоговая 45 000 (скидка 15 000); оплачено 15 000; остаток курса 30 000.",
             {"discount_enabled": True, "final_course_price": "45000",
              "discount_reason": "DEMO: полная оплата по согласованию"}, (("pay", "15000"), ("it", 5))),
    Scenario("D", "Данияр", "Бронев", "standard", "Бронь + доплата за первый месяц",
             "Бронь 3 000 + доплата 12 000 = месяц 1 оплачен; бронь вычтена один раз.",
             {"reservation_amount": "3000"}, (("res", "3000"), ("pay", "12000"), ("it", 4))),
    Scenario("E", "Эльмира", "Безоплатова", "standard", "Только бронь, срок прошёл",
             "Бронь 3 000 в месяц 1, доплата 12 000 не внесена, проведено 5 уроков IT — просрочка.",
             {"reservation_amount": "3000"}, (("res", "3000"), ("it", 5), ("call", "NO_ANSWER"))),
    Scenario("F", "Фарида", "Частичная", "standard", "Частичная оплата",
             "Начислено 15 000, оплачено 8 000, долг 7 000 — частично оплачено, срок ещё не наступил.",
             {}, (("pay", "8000"), ("it", 2))),
    Scenario("G", "Гульнара", "Просрочкина", "standard", "Второй месяц просрочен",
             "Месяц 1 пройден; месяц 2: 3-й урок — последний срок, проведено 4 — просрочка 15 000.",
             {}, (("pay", "15000"), ("it", 16), ("call", "PROMISED"))),
    Scenario("H", "Хасан", "Скоров", "next", "Скоро оплата",
             "Программа Next (6 месяцев): 9 из 12 уроков IT месяца 1; срок месяца 2 — 3-й урок месяца 2, "
             "по расписанию через 6 дней — «Скоро оплата → через 6–10 дней» (15 000).",
             {}, (("pay", "15000"), ("it", 9))),
    Scenario("I", "Ислам", "Айтишников", "standard", "English отстаёт от IT",
             "IT 12, English 10 — месяц 1 завершён по IT, месяц 2 к оплате.",
             {}, (("pay", "15000"), ("en", 10), ("it", 12))),
    Scenario("J", "Жанара", "Инглишева", "standard", "English опережает IT",
             "IT 9, English 12 — месяц 1 не завершён, новый платёжный этап не наступил.",
             {}, (("pay", "15000"), ("en", 12), ("it", 9))),
    Scenario("K", "Кайрат", "Авансов", "standard", "Предоплата за три месяца",
             "Внесено 45 000 = 3 месяца: месяцы 1–2 закрыты, 15 000 аванса закроет месяц 3.",
             {}, (("pay", "45000"), ("it", 14))),
    Scenario("L", "Лейла", "Индивидуальная", "discount", "Индивидуальная стоимость",
             "Стандарт 15 000/мес, по договору 12 000/мес (итог 48 000) — начисления по 12 000.",
             {"discount_enabled": True, "final_course_price": "48000",
              "discount_reason": "DEMO: индивидуальная стоимость 12 000 сом в месяц"}, (("pay", "12000"), ("it", 13))),
    Scenario("M", "Марат", "Третьемесячный", "standard", "Просрочка третьего месяца",
             "Месяцы 1–2 пройдены и оплачены; месяц 3: оплачено 5 000 из 15 000, 4 урока — просрочка 10 000.",
             {}, (("pay", "15000"), ("it", 12), ("pay", "15000"), ("it", 12), ("pay", "5000"), ("it", 4))),
    Scenario("N", "Нурлан", "Переплатов", "standard", "Переплата",
             "Начислено 15 000, внесено 18 000 — месяц 1 оплачен, 3 000 — аванс, долг не отрицательный.",
             {}, (("pay", "18000"), ("it", 3))),
    Scenario("O", "Ольга", "Возвратова", "standard", "Возврат части денег",
             "Внесено 20 000 (15 000 — месяц 1, 5 000 — аванс), возвращено 3 000; исходный платёж в истории.",
             {}, (("pay", "20000"), ("it", 3), ("refund", "3000"))),
)


def _group(ctx: Ctx, sc: Scenario) -> Group:
    def create():
        group = Group.objects.create(name=f"[DEMO] Финансы · {sc.key} · {sc.title}"[:150],
                                     course=ctx.courses[sc.program], start_date=ctx.start)
        for subject in ctx.subjects.values():
            GroupTeacher.objects.create(group=group, teacher=ctx.teacher, subject=subject)
        return group

    group = ensure(f"group:{sc.key}", create)
    for gt in GroupTeacher.objects.filter(group=group):
        register(gt)
    return group


def _student(ctx: Ctx, sc: Scenario, group: Group) -> Student:
    n = ord(sc.key) - ord("A") + 1
    return ensure(f"student:{sc.key}", lambda: Student.objects.create(
        first_name=sc.first, last_name=sc.last, group=group, enrollment_date=ctx.start,
        parent_phone=f"+996 000 000 {n:03d}",  # заведомо несуществующий номер
    ))


class _Clock:
    """Даты уроков и платежей сценария: уроки через день, последний — вчера
    (как в расписании академии); платёж датируется днём после последнего
    проведённого урока."""

    def __init__(self, today: dt.date, lessons: int):
        self.day = today - dt.timedelta(days=2 * lessons - 1)
        self.number = 0

    def next_lesson_day(self) -> dt.date:
        day = self.day
        self.day += dt.timedelta(days=2)
        self.number += 1
        return day


def _hold(ctx: Ctx, group: Group, student: Student, subject: Subject, clock: _Clock) -> Lesson:
    from .lessons import sync_lesson

    gt = GroupTeacher.objects.get(group=group, subject=subject)
    day = clock.next_lesson_day()
    if day >= ctx.today:
        raise DemoError("Демо-уроки должны быть в прошлом — увеличьте START_OFFSET_DAYS.")
    lesson = Lesson.objects.create(
        group=group, group_teacher=gt, teacher=ctx.teacher, subject=subject, lesson_number=clock.number, date=day,
        start_time=dt.time(15), end_time=dt.time(16, 30), status=Lesson.Status.COMPLETED,
    )
    Attendance.objects.create(lesson=lesson, student=student, status=Attendance.Status.PRESENT)
    sync_lesson(lesson.pk)  # как сигнал после коммита (идемпотентно)
    return lesson


def _run(ctx: Ctx, sc: Scenario) -> StudentBillingProfile:
    from .contacts import register_billing_contact
    from .payments import record_payment, refund_payment
    from .profiles import create_student_billing_profile
    from .reservations import record_reservation_payment

    group = _group(ctx, sc)
    student = _student(ctx, sc, group)
    profile = ensure(f"profile:{sc.key}", lambda: create_student_billing_profile(
        student=student, plan=ctx.plans[sc.program], actor=ctx.accountant, start_date=ctx.start,
        parent_name=f"Родитель: {sc.first} {sc.last} (DEMO)", responsible_accountant=ctx.accountant,
        reservation_allocation=ReservationAllocation.FIRST_MONTH, **sc.contract,
    ))
    total = sum(step[1] for step in sc.steps if step[0] in ("it", "en"))
    clock = _Clock(ctx.today, total)
    first_lesson = clock.day
    last_payment = None
    for i, step in enumerate(sc.steps):
        kind, value = step[0], step[1]
        # До первого урока — оплата в день начала договора, дальше — после последнего урока.
        on = min(clock.day - dt.timedelta(days=1) if clock.number else first_lesson - dt.timedelta(days=1), ctx.today)
        key = f"demo-{sc.key}-{i}"
        if kind == "res":
            record_reservation_payment(profile.reservations.get(status="PENDING"), actor=ctx.accountant, amount=value,
                                       received_date=on, method="cash", idempotency_key=key,
                                       payer_name=profile.parent_name)
        elif kind == "pay":
            last_payment, _ = record_payment(profile=profile, amount=value, received_date=on, actor=ctx.accountant,
                                             method="cash" if i % 2 == 0 else "card", idempotency_key=key,
                                             payer_name=profile.parent_name, comment="DEMO")
        elif kind in ("it", "en"):
            subject = ctx.subjects["IT" if kind == "it" else "English"]
            for _ in range(value):
                _hold(ctx, group, student, subject, clock)
        elif kind == "refund":
            refund_payment(last_payment, actor=ctx.accountant, amount=value, reason="DEMO: возврат части аванса",
                           refund_date=ctx.today - dt.timedelta(days=1), idempotency_key=key)
        elif kind == "call":
            promised = ctx.today + dt.timedelta(days=3) if value == "PROMISED" else None
            register_billing_contact(
                profile=profile, actor=ctx.accountant, channel="CALL", result=value,
                comment="DEMO: звонок родителю", contacted_at=timezone.now() - dt.timedelta(days=1),
                promised_payment_date=promised,
                next_contact_date=promised + dt.timedelta(days=1) if promised else ctx.today + dt.timedelta(days=1),
            )
    _plan_upcoming(ctx, group, ctx.subjects["IT"], last=clock.number)
    return profile


UPCOMING_LESSONS = 30


def _plan_upcoming(ctx: Ctx, group: Group, subject: Subject, *, last: int) -> None:
    """Расписание вперёд: запланированные уроки IT каждый день с завтрашнего —
    по ним «Скоро оплата» определяет дату урока-срока. Не проводятся и не
    списываются (статус «Запланирован»)."""
    gt = GroupTeacher.objects.get(group=group, subject=subject)
    for i in range(UPCOMING_LESSONS):
        ensure(f"upcoming:{group.pk}:{i}", lambda i=i: Lesson.objects.create(
            group=group, group_teacher=gt, teacher=ctx.teacher, subject=subject, lesson_number=last + i + 1,
            date=ctx.today + dt.timedelta(days=i + 1), start_time=dt.time(15), end_time=dt.time(16, 30),
            status=Lesson.Status.SCHEDULED,
        ))


# ---------------------------------------------------------------------------
# Сбор принадлежащих набору записей
# ---------------------------------------------------------------------------

# От этих моделей не идём по обратным связям: ими пользуются и реальные данные
# (демо-бухгалтер может открыть реальную карточку, на демо-тариф могут оформить
# реальный договор) — такие записи не становятся демо, а очистка остановится.
NO_TRAVERSE = {User, Teacher, Subject, Course, BillingPlan, BillingPlanVersion, ContentType, DemoSeedRecord}


def _registered_ids() -> dict[type, set[int]]:
    out: dict[type, set[int]] = defaultdict(set)
    for rec in DemoSeedRecord.objects.filter(dataset=DATASET, content_type__isnull=False).select_related("content_type"):
        model = rec.content_type.model_class()
        if model is None:
            raise DemoError(f"В реестре есть запись неизвестной модели: {rec.key}.")
        out[model].add(rec.object_id)
    return out


def sweep() -> int:
    """Зарегистрировать всё, что принадлежит демо-группам, демо-студентам и
    их договорам: уроки, посещаемость, платежи (в т.ч. внесённые вручную при
    проверке), начисления, распределения, чеки, контакты, журнал, события."""
    added = 0
    while True:
        ids = _registered_ids()
        new = 0
        for model, pks in ids.items():
            if model in NO_TRAVERSE or not pks:
                continue
            for rel in model._meta.related_objects:
                if rel.many_to_many:
                    continue
                related = rel.related_model
                for obj in related._base_manager.filter(**{f"{rel.field.name}__in": pks}).exclude(
                        pk__in=ids.get(related, set())):
                    new += register(obj)
        for model, pks in ids.items():
            for log in PayrollAuditLog.objects.filter(entity_type=model._meta.model_name, entity_id__in=pks).exclude(
                    pk__in=ids.get(PayrollAuditLog, set())):
                new += register(log)
        lesson_keys = [f"lesson:{pk}" for pk in ids.get(Lesson, set())]
        for event in BillingEvent.objects.filter(key__in=lesson_keys).exclude(pk__in=ids.get(BillingEvent, set())):
            new += register(event)
        added += new
        if not new:
            return added


# ---------------------------------------------------------------------------
# Генерация
# ---------------------------------------------------------------------------

def seed(*, today: dt.date | None = None) -> dict:
    """Создать недостающее (идемпотентно). Возвращает сводку."""
    ensure_allowed()
    today = today or timezone.localdate()
    with transaction.atomic():
        meta = DemoSeedRecord.objects.filter(key=f"{DATASET}:meta").first()
        start = dt.date.fromisoformat(meta.meta["start"]) if meta else today - dt.timedelta(days=START_OFFSET_DAYS)
        if meta is None:
            _mark("meta", start=start.isoformat(), today=today.isoformat())
        ctx = Ctx(today=today, start=start)
        build_reference(ctx)
        created = []
        for sc in SCENARIOS:
            if _marked(f"scenario:{sc.key}"):
                continue
            _run(ctx, sc)
            _mark(f"scenario:{sc.key}")
            created.append(sc.key)
        sweep()
    return {"created": created, "start": start.isoformat(), "records": DemoSeedRecord.objects.filter(
        dataset=DATASET).count()}


def scenario_rows() -> list[dict]:
    """Состояние каждого сценария из базы (для вывода команды и проверки)."""
    from .contracts import current_month, money_summary

    rows = []
    for sc in SCENARIOS:
        profile = lookup(f"profile:{sc.key}")
        if profile is None:
            continue
        summary, month = money_summary(profile), current_month(profile)
        rows.append({
            "key": sc.key, "student": str(profile.student), "program": profile.plan.name, "title": sc.title,
            "month": f"{month.month_number}: IT {month.lessons_used}/{month.lessons_total}" if month else "—",
            "due_now": summary["due_now"], "overdue": summary["overdue"], "credit": summary["credit"],
            "outstanding": summary["outstanding"], "profile": profile.pk,
        })
    return rows


# ---------------------------------------------------------------------------
# Очистка
# ---------------------------------------------------------------------------

def _delete_all(ids: dict[type, set[int]]) -> dict[str, int]:
    """Удалить зарегистрированные записи в порядке, который допускают
    внешние ключи (PROTECT): повторяем проходы, пока есть прогресс; записи,
    ссылающиеся друг на друга внутри модели (возврат → платёж, сторно →
    списание), удаляются поштучно."""
    remaining = {model: set(pks) for model, pks in ids.items() if pks}
    deleted: dict[str, int] = defaultdict(int)
    while remaining:
        progress = False
        for model in list(remaining):
            pks = {pk for pk in remaining[model] if model._base_manager.filter(pk=pk).exists()}
            if not pks:
                del remaining[model]
                progress = True
                continue
            try:
                with transaction.atomic():
                    _, per_model = model._base_manager.filter(pk__in=pks).delete()
            except ProtectedError:
                for pk in sorted(pks, reverse=True):
                    try:
                        with transaction.atomic():
                            _, per_model = model._base_manager.filter(pk=pk).delete()
                    except ProtectedError:
                        continue
                    for label, n in per_model.items():
                        deleted[label] += n
                    progress = True
                continue
            for label, n in per_model.items():
                deleted[label] += n
            progress = True
            del remaining[model]
        if not progress:
            stuck = {m._meta.label: len(p) for m, p in remaining.items()}
            raise DemoError(f"Очистка отменена: не удалось удалить {stuck} (на них ссылаются другие записи).")
    return dict(deleted)


def reset(*, dry_run: bool = False) -> dict[str, int]:
    """Удалить только демо-набор. Останавливается, если удаление задело бы
    данные вне набора; `dry_run` — показать и откатить."""
    ensure_allowed()
    with transaction.atomic():
        sweep()
        ids = _registered_ids()
        problems = foreign_dependents(ids)
        if problems:
            raise DemoError("Очистка остановлена: удаление задело бы данные вне демо-набора — " + "; ".join(problems))
        with maintenance_delete():
            deleted = _delete_all(ids)
        from django.apps import apps as django_apps

        own = {m._meta.label for m in ids}
        extra = {label: n for label, n in deleted.items()
                 if label not in own and not django_apps.get_model(label)._meta.auto_created}
        if extra:
            raise DemoError(f"Очистка отменена: каскадом задеты записи вне набора {extra}.")
        for model, pks in ids.items():
            if model._base_manager.filter(pk__in=pks).exists():
                raise DemoError(f"Очистка отменена: остались записи {model._meta.label}.")
        DemoSeedRecord.objects.filter(dataset=DATASET).delete()
        if dry_run:
            transaction.set_rollback(True)
    return {label: n for label, n in sorted(deleted.items()) if label in own}


# ---------------------------------------------------------------------------
# Пароли демо-пользователей (только локально)
# ---------------------------------------------------------------------------

def set_passwords(password: str | None = None) -> dict[str, str]:
    """Задать пароли демо-пользователям. Без `password` — случайный пароль
    каждому (показывается один раз). Только вне production."""
    import secrets

    ensure_allowed()
    result = {}
    for key in ("accountant", "manager", "director"):  # тренеру вход не нужен
        username = USERS[key][0]
        user = lookup(f"user:{key}")
        if user is None:
            continue
        value = password or secrets.token_urlsafe(12)
        user.set_password(value)
        user.save(update_fields=["password"])
        result[username] = value
    if not result:
        raise DemoError("Демо-пользователей нет — сначала выполните seed_billing_demo.")
    return result

