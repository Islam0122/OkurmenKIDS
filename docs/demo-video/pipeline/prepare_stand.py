"""Подготовка ЛОКАЛЬНОГО демо-стенда для записи видео (не для production).

Запуск (после generate_mock_data / seed_accounting_demo / seed_billing_demo):
    faketime -f "@2026-11-12 04:20:00" python manage.py shell < docs/demo-video/pipeline/prepare_stand.py

Что делает: заменяет тестовые имена на вымышленные реалистичные, убирает
префиксы [MOCK]/[DEMO], создаёт пользователей video_* для съёмки, офис с
геозоной и историю прихода/ухода, расписание на ближайшие две недели.
"""
import os
if os.environ.get("DJANGO_ENV") == "production":
    raise SystemExit("prepare_stand.py: только для локальной демо-базы")
# ---- 1. имена и названия ----
import random, re, datetime as dt
from django.utils import timezone
from apps.users.models import User
from apps.academy.models import Group, Student, Course
from apps.billing.models import BillingPlan
rng = random.Random(11)
M = ["Айбек","Нурсултан","Эмир","Арсен","Бекжан","Данияр","Тимур","Алихан","Нурислам","Адилет","Эрмек","Бакай","Санжар","Азамат","Темирлан","Ислам","Канат","Мирлан","Руслан","Улан"]
F = ["Айым","Алия","Аружан","Асема","Айзада","Медина","Нурай","Дана","Камила","Сезим","Элина","Амина","Айсулуу","Жибек","Малика","Томирис","Айдана","Бермет","Назира","Адина"]
L = ["Асанов","Садыков","Токтогулов","Жумабаев","Осмонов","Бекболотов","Алиев","Мамытов","Кадыров","Абдыкадыров","Сатыбалдиев","Орозбеков","Эсенов","Турсунов","Исаков","Касымов","Бакиров","Молдоев","Шаршеев","Усенов","Иманалиев","Калыков","Акматов","Сулайманов"]
def fem(s): return s + "а"
def name(): 
    if rng.random() < .5: return rng.choice(M), rng.choice(L)
    return rng.choice(F), fem(rng.choice(L))
for s in Student.objects.all():
    s.first_name, s.last_name = name(); s.save(update_fields=["first_name","last_name"])
for u in User.objects.filter(role="teacher"):
    u.first_name, u.last_name = name(); u.save(update_fields=["first_name","last_name"])
rx = re.compile(r"^\[(MOCK|DEMO)\]\s*|^DEMO\s+")
for model in (Group, Course, BillingPlan):
    for o in model.objects.all():
        n = rx.sub("", o.name).replace("[DEMO] ","").replace("[MOCK] ","")
        m = re.match(r"Финансы · (\w) · ", n)
        if m: n = f"IT Kids — поток {m.group(1)}"
        if n != o.name:
            if model is BillingPlan and model.objects.filter(name=n).exists(): continue
            o.name = n; o.save(update_fields=["name"])
# ---- 2. пользователи, офис, история посещаемости ----
import random, re
from datetime import timedelta, datetime, time
from django.utils import timezone
from zoneinfo import ZoneInfo
from apps.users.models import User
from apps.staff_attendance.models import AttendanceLocation, AttendanceSession, AttendanceEvent, AttendanceSettings
from apps.academy.models import Group

PW = os.environ["DEMO_PASSWORD"]  # задаётся при запуске, в репозитории паролей нет
rng = random.Random(7)
# 1. Video users (fictional people)
spec = [("video_admin", "admin", "Айбек", "Садыков"), ("video_ops", "operations_director", "Нурлан", "Асанов"),
        ("video_hr", "hr_manager", "Айгерим", "Токтогулова"), ("video_sales", "sales_manager", "Бекжан", "Алиев"),
        ("video_marketing", "marketing", "Асель", "Курманова"), ("video_rop", "rop", "Тимур", "Жумалиев")]
for u, role, fn, ln in spec:
    user, _ = User.objects.get_or_create(username=u, defaults={"role": role})
    user.role, user.first_name, user.last_name, user.is_verified, user.is_active = role, fn, ln, True, True
    user.email = f"{u}@demo.okurmenkids.invalid"; user.set_password(PW); user.save()
rename = {"demo_accountant": ("Жылдыз", "Мамбетова"), "demo_director": ("Эрлан", "Бекболотов"), "demo_manager": ("Мээрим", "Осмонова"),
          "mock_admin": ("Админ", "Академии"), "demo_acc_accountant": ("Гульнара", "Исаева"), "demo_acc_director": ("Канат", "Орозов"),
          "demo_acc_fix1": ("Алина", "Сыдыкова"), "demo_acc_fix2": ("Руслан", "Кадыров"), "demo_acc_t1": ("Эмир", "Айтиев"),
          "demo_acc_t2": ("Динара", "Абдраева"), "demo_acc_t3": ("Улан", "Беков"), "demo_acc_t4": ("Азат", "Шаршеев"),
          "demo_billing_trainer": ("Мирлан", "Усенов")}
for u, (fn, ln) in rename.items():
    User.objects.filter(username=u).update(first_name=fn, last_name=ln)
for user in User.objects.exclude(username__startswith="video_"):
    user.set_password(PW); user.is_active = True; user.save(update_fields=["password", "is_active"])
# cosmetic: strip test prefixes from group names (local demo DB only)
for g in Group.objects.all():
    n = re.sub(r"^\[(MOCK|DEMO)\]\s*", "", g.name)
    if n != g.name:
        g.name = n; g.save(update_fields=["name"])
# 2. Office + geofence
loc, _ = AttendanceLocation.objects.get_or_create(code="okurmen-main-office", defaults=dict(
    name="Okurmen Kids — главный офис", address="Бишкек, пр. Чуй", latitude=42.8746, longitude=74.6122, radius_m=120))
cfg = AttendanceSettings.load()
# 3. Two weeks of history
tz = cfg.tzinfo
staff = list(User.objects.filter(username__startswith="video_").exclude(username="video_admin")) + \
        list(User.objects.filter(username__in=["demo_accountant", "demo_manager", "demo_acc_fix1", "demo_acc_fix2"])) + \
        list(User.objects.filter(role="teacher", username__startswith="mock_teacher")[:12])
AttendanceSession.objects.filter(location=loc).exclude(work_date=timezone.localdate()).delete()
today = timezone.now().astimezone(tz).date()
for d in range(14, 0, -1):
    day = today - timedelta(days=d)
    if day.weekday() >= 5: continue
    for user in staff:
        if rng.random() < 0.08: continue
        late = rng.random() < 0.18
        start = datetime.combine(day, time(9, 0), tz) + timedelta(minutes=rng.randint(12, 45) if late else -rng.randint(0, 20))
        end = datetime.combine(day, time(18, 0), tz) + timedelta(minutes=rng.randint(-15, 50))
        missing = rng.random() < 0.05
        s = AttendanceSession.objects.create(user=user, location=loc, work_date=day, checked_in_at=start,
            checked_out_at=None if missing else end,
            status=AttendanceSession.Status.MISSING_CHECKOUT if missing else AttendanceSession.Status.CLOSED,
            source=AttendanceSession.Source.QR, expected_start=datetime.combine(day, time(9, 0), tz),
            late_minutes=max(0, int((start - datetime.combine(day, time(9, 10), tz)).total_seconds() // 60)) if late else 0,
            check_in_distance_m=round(rng.uniform(4, 60), 1), check_in_accuracy_m=round(rng.uniform(5, 25), 1),
            check_out_distance_m=None if missing else round(rng.uniform(4, 60), 1), check_out_accuracy_m=None if missing else round(rng.uniform(5, 25), 1))
        AttendanceEvent.objects.create(session=s, user=user, kind=AttendanceEvent.Kind.CHECK_IN, occurred_at=start, location=loc,
            distance_m=s.check_in_distance_m, accuracy_m=s.check_in_accuracy_m)
        if not missing:
            AttendanceEvent.objects.create(session=s, user=user, kind=AttendanceEvent.Kind.CHECK_OUT, occurred_at=end, location=loc,
                distance_m=s.check_out_distance_m, accuracy_m=s.check_out_accuracy_m)
# today: most staff already in, except video_ops (will check in live on camera)
for user in staff:
    if user.username == "video_ops" or AttendanceSession.objects.filter(user=user, work_date=today).exists(): continue
    if rng.random() < 0.15: continue
    start = datetime.combine(today, time(9, 0), tz) + timedelta(minutes=rng.randint(-20, 25))
    s = AttendanceSession.objects.create(user=user, location=loc, work_date=today, checked_in_at=start, status="open", source="qr",
        expected_start=datetime.combine(today, time(9, 0), tz), late_minutes=max(0, int((start - datetime.combine(today, time(9, 10), tz)).total_seconds() // 60)),
        check_in_distance_m=round(rng.uniform(4, 60), 1), check_in_accuracy_m=round(rng.uniform(5, 25), 1))
    AttendanceEvent.objects.create(session=s, user=user, kind="check_in", occurred_at=start, location=loc, distance_m=s.check_in_distance_m, accuracy_m=s.check_in_accuracy_m)
print("ok", AttendanceSession.objects.count())
# ---- 3. занятия на ближайшие две недели ----
import datetime as dt, re
from django.db.models import Max
from apps.academy.models import Lesson, Group, Room
for r in Room.objects.all():
    n = re.sub(r"^\[(MOCK|DEMO)\]\s*", "", r.name)
    if n != r.name and not Room.objects.filter(name=n).exists(): r.name = n; r.save(update_fields=["name"])
today = dt.date(2026, 11, 12)
active = Group.objects.filter(status="active").exclude(name__startswith="IT Kids")
nums = {g["group"]: g["m"] or 0 for g in Lesson.objects.values("group").annotate(m=Max("lesson_number"))}
new = []
for i in range(14):
    d = today + dt.timedelta(days=i)
    for src in Lesson.objects.filter(group__in=active, date=d - dt.timedelta(days=7), status__in=["completed", "cancelled"]).order_by("group_id"):
        if src.date - dt.timedelta(days=0) < today - dt.timedelta(days=7): pass
        nums[src.group_id] = nums.get(src.group_id, 0) + 1
        new.append(Lesson(group_id=src.group_id, teacher_id=src.teacher_id, group_teacher_id=src.group_teacher_id, schedule_id=src.schedule_id,
            lesson_number=nums[src.group_id], date=d, start_time=src.start_time, end_time=src.end_time, room_id=src.room_id,
            subject_id=src.subject_id, topic=src.topic, status="scheduled", schedule_overridden=False))
    # if a source day was itself generated (i>=7), it was created in this loop: handle by bulk insert per day
    Lesson.objects.bulk_create(new); new = []
print("future lessons", Lesson.objects.filter(date__gte=today, group__in=active).count())
# ---- 4. должности, описания, суперпользователь для раздела «Офисы и QR» ----
from apps.accounting.models import EmployeeSalaryProfile
from apps.academy.models import Group, Course
from apps.users.models import User
pos = {"teacher": "Тренер", "team_lead": "Team Lead", "assistant": "Ассистент", "accountant": "Бухгалтер", "director": "Директор"}
for p in EmployeeSalaryProfile.objects.filter(position="DEMO").select_related("employee"):
    p.position = pos.get(p.employee.role, "Сотрудник"); p.save(update_fields=["position"])
for M in (Group, Course):
    for o in M.objects.all():
        d = (o.description or "").replace("(MOCK) ", "").replace("[MOCK] ", "")
        if d.strip() == "DEMO": d = ""
        if d != o.description: o.description = d; o.save(update_fields=["description"])
User.objects.filter(username="video_admin").update(is_superuser=True, is_staff=True)
