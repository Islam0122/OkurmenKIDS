"""Личное расписание: часы по дням, перерыв, период действия, форма Django
admin, поиск сотрудника и влияние на расчёт опозданий."""
from __future__ import annotations

from datetime import date, time

from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.staff_attendance.models import (
    AttendanceAdminLog,
    AttendanceWorkSchedule,
    DayHours,
    parse_day_hours,
)
from apps.staff_attendance.services.schedule import late_minutes, window_for
from apps.users.models import Teacher, User

from .base import AttendanceFixture, frozen, local, make_user

API = "/api/v1/staff-attendance"
MON, WED, SAT = (2026, 10, 19), (2026, 10, 21), (2026, 10, 24)
ADD_URL = reverse("admin:staff_attendance_attendanceworkschedule_add")


def schedule(user, **extra) -> AttendanceWorkSchedule:
    values = {"work_start": time(9, 0), "work_end": time(18, 0), "work_days": [0, 1, 2, 3, 4],
              "late_grace_minutes": 0}
    values.update(extra)
    obj = AttendanceWorkSchedule(user=user, **values)
    obj.full_clean()
    obj.save()
    return obj


def form_payload(user, days=(0, 1, 2, 3, 4), start="09:00", end="18:00", **extra) -> dict:
    data = {"user": str(user.pk), "work_days": [str(d) for d in days], "break_mode": "none",
            "late_grace_minutes": "", "valid_from": "", "valid_until": "", "is_active": "on", "note": ""}
    for day in range(7):
        data.update({f"d{day}_start": start, f"d{day}_end": end, f"d{day}_break_start": "", f"d{day}_break_end": ""})
    data.update(extra)
    return data


class ScheduleModelTests(AttendanceFixture):
    def test_validation_messages(self):
        cases = [
            ({"work_start": time(18, 0), "work_end": time(9, 0)}, "work_end"),
            ({"break_start": time(13, 0)}, "break_end"),
            ({"break_start": time(14, 0), "break_end": time(13, 0)}, "break_end"),
            ({"break_start": time(8, 0), "break_end": time(9, 30)}, "break_start"),
            ({"valid_from": date(2026, 11, 1), "valid_until": date(2026, 10, 1)}, "valid_until"),
            ({"day_hours": {"9": {"start": "09:00", "end": "18:00"}}}, "day_hours"),
            ({"day_hours": {"1": {"start": "18:00", "end": "09:00"}}}, "day_hours"),
            ({"day_hours": {"1": {"start": "nope", "end": "09:00"}}}, "day_hours"),
            ({"day_hours": {"1": {"start": "09:00", "end": "18:00", "lunch": "13:00"}}}, "day_hours"),
            ({"day_hours": ["09:00"]}, "day_hours"),
        ]
        for extra, field in cases:
            with self.subTest(extra=extra), self.assertRaises(ValidationError) as ctx:
                schedule(self.assistant, **extra)
            self.assertIn(field, ctx.exception.message_dict)

    def test_day_hours_are_normalized(self):
        obj = schedule(self.assistant, work_days=[0, 1, 5], day_hours={
            1: {"start": "09:00", "end": "18:00"},                     # как базовые → не хранится
            "5": {"start": "10:00:00", "end": "14:00", "break_start": None, "break_end": None},
            "6": {"start": "10:00", "end": "12:00"},                   # нерабочий день → отброшен
        })
        self.assertEqual(obj.day_hours, {"5": {"start": "10:00", "end": "14:00", "break_start": None, "break_end": None}})
        self.assertEqual(obj.hours_for(5), DayHours(time(10, 0), time(14, 0)))
        self.assertEqual(obj.hours_for(0), DayHours(time(9, 0), time(18, 0)))
        self.assertIsNone(obj.hours_for(6))

    def test_corrupted_day_hours_fall_back_to_base_hours(self):
        obj = schedule(self.assistant)
        AttendanceWorkSchedule.objects.filter(pk=obj.pk).update(day_hours={"2": "garbage"})
        obj.refresh_from_db()
        self.assertEqual(obj.hours_for(2), DayHours(time(9, 0), time(18, 0)))
        self.assertEqual(parse_day_hours({}), {})


class ScheduleCalculationTests(AttendanceFixture):
    def test_legacy_schedule_is_unchanged(self):
        # Запись «как до миграции»: без перерыва, часов по дням и периода.
        AttendanceWorkSchedule.objects.create(user=self.assistant, work_start=time(11, 0), work_end=time(20, 0),
                                              work_days=[0, 1, 2, 3, 4], late_grace_minutes=5)
        window = window_for(self.assistant, date(*WED), self.config)
        self.assertEqual((window.start.time(), window.end.time(), window.grace_minutes, window.source),
                         (time(11, 0), time(20, 0), 5, "personal"))
        self.assertIsNone(window.break_start)
        self.assertIsNone(window_for(self.assistant, date(*SAT), self.config))

    def test_different_hours_per_day(self):
        schedule(self.assistant, work_days=[0, 1, 2, 3, 4, 5], late_grace_minutes=10,
                 day_hours={"5": {"start": "10:00", "end": "14:00"}})
        sat = window_for(self.assistant, date(*SAT), self.config)
        self.assertEqual((sat.start.time(), sat.end.time()), (time(10, 0), time(14, 0)))
        self.assertEqual(late_minutes(local(*SAT, 10, 9), sat), 0)
        self.assertEqual(late_minutes(local(*SAT, 10, 15), sat), 15)
        wed = window_for(self.assistant, date(*WED), self.config)
        self.assertEqual(late_minutes(local(*WED, 9, 15), wed), 15)

    def test_break_is_exposed_but_does_not_change_lateness(self):
        schedule(self.assistant, break_start=time(13, 0), break_end=time(14, 0))
        window = window_for(self.assistant, date(*WED), self.config)
        self.assertEqual((window.break_start.time(), window.break_end.time()), (time(13, 0), time(14, 0)))
        self.assertEqual(late_minutes(local(*WED, 9, 1), window), 1)

    def test_grace_falls_back_to_global_settings(self):
        schedule(self.assistant, late_grace_minutes=None)
        self.assertEqual(window_for(self.assistant, date(*WED), self.config).grace_minutes,
                         self.config.late_grace_minutes)

    def test_validity_period_and_active_flag(self):
        obj = schedule(self.assistant, work_start=time(11, 0), work_end=time(20, 0),
                       valid_from=date(2026, 10, 20), valid_until=date(2026, 10, 22))
        self.assertEqual(window_for(self.assistant, date(*WED), self.config).source, "personal")
        self.assertEqual(window_for(self.assistant, date(2026, 10, 22), self.config).source, "personal")  # включительно
        before = window_for(self.assistant, date(*MON), self.config)
        self.assertEqual((before.source, before.start.time()), ("default", self.config.work_start))
        self.assertEqual(window_for(self.assistant, date(2026, 10, 23), self.config).source, "default")
        obj.is_active = False
        obj.save()
        self.assertEqual(window_for(self.assistant, date(*WED), self.config).source, "default")
        self.assertTrue(schedule(self.teacher).is_effective_on(date(*WED)))

    def test_check_in_uses_day_specific_hours(self):
        schedule(self.assistant, work_days=[0, 1, 2, 3, 4, 5], day_hours={"5": {"start": "12:00", "end": "16:00"}})
        with frozen(local(*SAT, 12, 20)):
            response = self.mark(self.assistant)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["session"]["late_minutes"], 20)
        self.assertTrue(response.data["session"]["expected_start"].startswith("2026-10-24T12:00:00"))

    def test_bulk_resolver_used_by_reports_respects_validity(self):
        from apps.staff_attendance.services.schedule import ScheduleResolver

        schedule(self.assistant, work_start=time(11, 0), work_end=time(20, 0), valid_from=date(2026, 10, 22))
        schedule(self.accountant, work_start=time(8, 0), work_end=time(17, 0), valid_until=date(2026, 10, 21))
        resolver = ScheduleResolver(self.config, [self.assistant, self.accountant], date(*WED))
        self.assertEqual(resolver.window(self.assistant).source, "default")
        self.assertEqual(resolver.window(self.accountant).start.time(), time(8, 0))


class ScheduleApiTests(AttendanceFixture):
    def url(self, user):
        return f"{API}/admin/employees/{user.pk}/schedule/"

    def test_put_with_new_fields(self):
        admin = self.as_user(self.admin)
        response = admin.put(self.url(self.accountant), {
            "work_start": "09:00", "work_end": "18:00", "work_days": [0, 1, 2, 3, 4, 5],
            "break_start": "13:00", "break_end": "14:00",
            "day_hours": {"5": {"start": "10:00", "end": "14:00", "break_start": None, "break_end": None}},
            "valid_from": "2026-11-01", "late_grace_minutes": 10, "note": "Испытательный срок",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["break_start"], "13:00:00")
        self.assertEqual(response.data["day_hours"]["5"]["start"], "10:00")
        self.assertEqual(response.data["valid_from"], "2026-11-01")

    def test_put_rejects_invalid_values(self):
        admin = self.as_user(self.admin)
        base = {"work_start": "09:00", "work_end": "18:00", "work_days": [0, 1, 2, 3, 4]}
        for extra, field in (({"break_start": "08:00", "break_end": "09:30"}, "break_start"),
                             ({"break_start": "13:00"}, "break_end"),
                             ({"valid_from": "2026-12-01", "valid_until": "2026-11-01"}, "valid_until"),
                             ({"day_hours": {"2": {"start": "18:00", "end": "10:00"}}}, "day_hours"),
                             ({"late_grace_minutes": 500}, "late_grace_minutes")):
            response = admin.put(self.url(self.accountant), {**base, **extra}, format="json")
            self.assertEqual(response.status_code, 400, extra)
            self.assertIn(field, response.data, extra)
        self.assertFalse(AttendanceWorkSchedule.objects.exists())

    def test_partial_update_keeps_existing_values(self):
        admin = self.as_user(self.admin)
        schedule(self.accountant, work_days=[0, 1, 5], day_hours={"5": {"start": "10:00", "end": "14:00"}})
        # Старый клиент меняет только дни: часы субботы отбрасываются без ошибки.
        response = admin.put(self.url(self.accountant), {"work_days": [0, 1]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["day_hours"], {})
        response = admin.put(self.url(self.accountant), {"work_end": "08:00"}, format="json")
        self.assertEqual(response.status_code, 400)


class ScheduleAdminTests(AttendanceFixture):
    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser(username="root", email="root@okurmen.kg",
                                                       password="Str0ngPassw0rd!", first_name="Root")
        self.web = Client()
        self.web.force_login(self.superuser)

    def test_add_page_has_visual_editor_and_no_raw_json(self):
        response = self.web.get(ADD_URL)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for title in ("Сотрудник", "Рабочие дни", "График работы", "Перерыв", "Настройки опоздания",
                      "Период действия", "Дополнительная информация", "Льготное время опоздания (минуты)"):
            self.assertIn(title, html)
        self.assertEqual(html.count('name="work_days"'), 7)
        self.assertNotIn("[0, 1, 2", html)
        self.assertNotIn('name="day_hours"', html)
        self.assertIn("data-employee-select", html)
        self.assertIn("select2.full.min.js", html)
        # Новое расписание по умолчанию — дни и часы общих настроек.
        self.assertIn('name="d0_start" value="09:00"', html)

    def test_create_schedule_with_saturday_hours_and_same_break(self):
        data = form_payload(self.assistant, days=(0, 1, 2, 3, 4, 5), break_mode="same",
                            break_start="13:00", break_end="14:00", late_grace_minutes="10",
                            valid_from="2026-11-01", note="Сокращённая суббота",
                            d5_start="10:00", d5_end="15:00")
        response = self.web.post(ADD_URL, data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:3000])
        obj = AttendanceWorkSchedule.objects.get(user=self.assistant)
        self.assertEqual(obj.work_days, [0, 1, 2, 3, 4, 5])
        self.assertEqual((obj.work_start, obj.work_end, obj.break_start, obj.break_end),
                         (time(9, 0), time(18, 0), time(13, 0), time(14, 0)))
        self.assertEqual(obj.day_hours, {"5": {"start": "10:00", "end": "15:00",
                                               "break_start": "13:00", "break_end": "14:00"}})
        self.assertEqual((obj.late_grace_minutes, obj.valid_from, obj.note), (10, date(2026, 11, 1),
                                                                              "Сокращённая суббота"))
        self.assertEqual(obj.updated_by, self.superuser)
        self.assertTrue(AttendanceAdminLog.objects.filter(action="schedule_update", object_id=str(obj.pk)).exists())

    def test_per_day_breaks_and_base_day_without_monday(self):
        data = form_payload(self.assistant, days=(2, 4), break_mode="per_day",
                            d2_start="08:00", d2_end="17:00", d2_break_start="12:00", d2_break_end="12:30",
                            d4_start="10:00", d4_end="19:00")
        self.assertEqual(self.web.post(ADD_URL, data).status_code, 302)
        obj = AttendanceWorkSchedule.objects.get(user=self.assistant)
        # Понедельник не рабочий → базовые часы — первого рабочего дня (среда).
        self.assertEqual((obj.work_start, obj.break_start), (time(8, 0), time(12, 0)))
        self.assertEqual(obj.hours_for(4), DayHours(time(10, 0), time(19, 0)))
        self.assertEqual(obj.hours_for(2), DayHours(time(8, 0), time(17, 0), time(12, 0), time(12, 30)))

    def test_form_errors_are_shown_and_nothing_saved(self):
        cases = [
            (form_payload(self.assistant, days=()), "Выберите хотя бы один рабочий день."),
            (form_payload(self.assistant, d1_start="18:00", d1_end="09:00"),
             "Окончание рабочего дня должно быть позже начала"),
            (form_payload(self.assistant, d3_end=""), "Укажите окончание рабочего дня."),
            (form_payload(self.assistant, break_mode="same", break_start="07:00", break_end="08:00"),
             "перерыв должен быть внутри рабочего времени"),
            (form_payload(self.assistant, break_mode="same"), "Укажите начало перерыва."),
            (form_payload(self.assistant, break_mode="per_day", d0_break_start="13:00"),
             "укажите и начало, и конец перерыва"),
            (form_payload(self.assistant, late_grace_minutes="300"), "Не больше 240 минут"),
            (form_payload(self.assistant, valid_from="2026-12-01", valid_until="2026-11-01"),
             "Дата окончания не может быть раньше даты начала."),
            (form_payload(self.assistant, d0_start="25:99"), "Введите правильное время"),
        ]
        for data, message in cases:
            with self.subTest(message=message):
                response = self.web.post(ADD_URL, data)
                self.assertEqual(response.status_code, 200)
                self.assertIn(message.lower(), response.content.decode().lower())
        self.assertFalse(AttendanceWorkSchedule.objects.exists())

    def test_hours_of_unselected_days_are_ignored(self):
        data = form_payload(self.assistant, days=(0,), d6_start="", d6_end="bad")
        self.assertEqual(self.web.post(ADD_URL, data).status_code, 302)

    def test_one_schedule_per_employee(self):
        schedule(self.assistant)
        response = self.web.post(ADD_URL, form_payload(self.assistant))
        self.assertContains(response, "уже есть личное расписание")
        self.assertEqual(AttendanceWorkSchedule.objects.count(), 1)

    def test_edit_existing_schedule_prefills_and_keeps_values(self):
        obj = schedule(self.assistant, work_start=time(11, 0), work_end=time(20, 0), work_days=[0, 2, 5],
                       day_hours={"5": {"start": "10:00", "end": "14:00"}})
        url = reverse("admin:staff_attendance_attendanceworkschedule_change", args=[obj.pk])
        html = self.web.get(url).content.decode()
        self.assertIn('name="d0_start" value="11:00"', html)
        self.assertIn('name="d5_start" value="10:00"', html)
        self.assertRegex(html, r'name="work_days" value="2"[^>]*checked')
        self.assertNotRegex(html, r'name="work_days" value="1"[^>]*checked')
        self.assertIn(employee_label_for(self.assistant), html)
        data = form_payload(self.assistant, days=(0, 2, 5), start="11:00", end="20:00",
                            d5_start="10:00", d5_end="14:00", late_grace_minutes="0")
        self.assertEqual(self.web.post(url, data).status_code, 302)
        obj.refresh_from_db()
        self.assertEqual((obj.work_start, obj.work_days), (time(11, 0), [0, 2, 5]))
        self.assertEqual(obj.day_hours["5"]["start"], "10:00")

    def test_admin_schedule_drives_attendance(self):
        data = form_payload(self.assistant, days=(5,), start="12:00", end="16:00", late_grace_minutes="5")
        self.assertEqual(self.web.post(ADD_URL, data).status_code, 302)
        with frozen(local(*SAT, 12, 4)):
            on_time = self.mark(self.assistant)
        self.assertEqual(on_time.data["session"]["late_minutes"], 0)
        with frozen(local(*SAT, 13, 0)):
            self.mark(self.assistant, "check-out")
        with frozen(local(*WED, 12, 0)):  # среда — выходной по личному расписанию
            self.assertIsNone(self.mark(self.assistant).data["session"]["expected_start"])

    def test_changelist(self):
        schedule(self.assistant, work_days=[0, 1, 2, 3, 4, 5], day_hours={"5": {"start": "10:00", "end": "14:00"}},
                 late_grace_minutes=None)
        response = self.web.get(reverse("admin:staff_attendance_attendanceworkschedule_changelist"))
        self.assertContains(response, "Пн–Сб")
        self.assertContains(response, "по дням")
        self.assertContains(response, "Действует")

    def test_delete_is_logged(self):
        obj = schedule(self.assistant)
        url = reverse("admin:staff_attendance_attendanceworkschedule_delete", args=[obj.pk])
        self.assertEqual(self.web.post(url, {"post": "yes"}).status_code, 302)
        self.assertTrue(AttendanceAdminLog.objects.filter(action="schedule_delete").exists())


class EmployeeSearchTests(AttendanceFixture):
    url = reverse("admin:staff_attendance_attendanceworkschedule_employee_search")

    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser(username="root", email="root@okurmen.kg",
                                                       password="Str0ngPassw0rd!")
        self.web = Client()
        self.web.force_login(self.superuser)

    def test_results_show_name_position_and_department(self):
        from apps.accounting.models import Department, EmployeeSalaryProfile

        aibek = make_user("aibek", User.Role.TEACHER, first_name="Айбек", last_name="Садыков")
        Teacher.objects.create(user=aibek, position="Senior Python Trainer")
        EmployeeSalaryProfile.objects.create(employee=aibek, salary_type="FIXED", department=Department.IT,
                                             effective_from=date(2026, 1, 1))
        # SQLite (тесты) не сравнивает кириллицу без учёта регистра, PostgreSQL — да.
        results = self.web.get(self.url, {"term": "Садыков"}).json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual((results[0]["full_name"], results[0]["position"], results[0]["department"]),
                         ("Айбек Садыков", "Senior Python Trainer", "IT"))
        self.assertEqual(results[0]["text"], "Айбек Садыков · Senior Python Trainer · IT")
        # Поиск по должности, по нескольким словам.
        self.assertEqual(len(self.web.get(self.url, {"term": "python Айбек"}).json()["results"]), 1)
        # Без зарплатного профиля: должность — роль, отдела нет.
        helper = self.web.get(self.url, {"term": "helper"}).json()["results"][0]
        self.assertEqual((helper["position"], helper["department"]), ("Ассистент", ""))

    def test_existing_schedule_is_disabled_except_current(self):
        schedule(self.assistant)
        item = self.web.get(self.url, {"term": "helper"}).json()["results"][0]
        self.assertTrue(item["disabled"])
        item = self.web.get(self.url, {"term": "helper", "current": self.assistant.pk}).json()["results"][0]
        self.assertFalse(item["disabled"])

    def test_inactive_users_hidden_and_pagination(self):
        make_user("ghost", User.Role.ASSISTANT, is_active=False)
        self.assertEqual(self.web.get(self.url, {"term": "ghost"}).json()["results"], [])
        for i in range(25):
            make_user(f"bulk{i}", User.Role.MARKETING)
        first = self.web.get(self.url, {"term": "bulk"}).json()
        second = self.web.get(self.url, {"term": "bulk", "page": 2}).json()
        self.assertEqual((len(first["results"]), first["pagination"]["more"]), (20, True))
        self.assertEqual((len(second["results"]), second["pagination"]["more"]), (5, False))

    def test_requires_admin_access(self):
        anonymous = Client().get(self.url)
        self.assertEqual(anonymous.status_code, 302)
        staff = make_user("hr_staff", User.Role.HR_MANAGER, is_staff=True)
        web = Client()
        web.force_login(staff)
        self.assertIn(web.get(self.url).status_code, (302, 403))


def employee_label_for(user) -> str:
    from apps.staff_attendance.admin_forms import employee_label

    return employee_label(user)
