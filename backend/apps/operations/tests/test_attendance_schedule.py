"""Кабинет операционного директора → «Посещаемость сотрудников»: колонка
«По графику» (schedule) из личных расписаний, общего графика и исключений."""
from __future__ import annotations

from datetime import date, time

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.staff_attendance.models import AttendanceScheduleException, AttendanceWorkSchedule
from apps.staff_attendance.tests.base import AttendanceFixture, frozen, local, make_user
from apps.users.models import User

API = "/api/v1/operations/attendance/"
MON, WED, SAT, SUN = (2026, 10, 19), (2026, 10, 21), (2026, 10, 24), (2026, 10, 25)
Kind = AttendanceScheduleException.Kind


def personal(user, **extra) -> AttendanceWorkSchedule:
    values = {"work_start": time(10, 0), "work_end": time(19, 0), "work_days": [0, 1, 2, 3, 4],
              "late_grace_minutes": 5}
    values.update(extra)
    obj = AttendanceWorkSchedule(user=user, **values)
    obj.full_clean()
    obj.save()
    return obj


def exception(user, kind, start, end=None, **extra) -> AttendanceScheduleException:
    obj = AttendanceScheduleException(user=user, kind=kind, date_from=date(*start), date_to=date(*(end or start)),
                                      **extra)
    obj.full_clean()
    obj.save()
    return obj


class ScheduledArrivalTests(AttendanceFixture):
    def setUp(self):
        super().setUp()
        self.od = make_user("odir", User.Role.OPERATIONS_DIRECTOR)

    def get(self, day=WED, moment=None, **params):
        params.setdefault("period", "today")
        with frozen(moment or local(*day, 20, 0)):
            response = self.as_user(self.od).get(API, params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def row(self, data, user, day=WED):
        return next(r for r in data["rows"] if r["user"]["id"] == user.pk and r["date"] == date(*day).isoformat())

    # -- время по графику ---------------------------------------------------

    def test_personal_and_default_arrival_times(self):
        personal(self.assistant)
        data = self.get()
        own = self.row(data, self.assistant)["schedule"]
        self.assertEqual((own["kind"], own["label"], own["expected_start"], own["expected_end"]),
                         ("work", "10:00", "10:00", "19:00"))
        self.assertEqual((own["grace_minutes"], own["late_after"], own["source"], own["source_label"]),
                         (5, "10:05", "personal", "Личный график"))
        general = self.row(data, self.accountant)["schedule"]
        self.assertEqual((general["label"], general["source"], general["grace_minutes"]),
                         ("09:00", "default", self.config.late_grace_minutes))
        # Старые поля не изменились.
        self.assertTrue(self.row(data, self.assistant)["expected_start"].isoformat().startswith("2026-10-21T10:00"))

    def test_day_specific_hours_and_validity_period(self):
        personal(self.assistant, work_days=[0, 1, 2, 3, 4, 5], day_hours={"5": {"start": "11:30", "end": "15:00"}})
        self.assertEqual(self.row(self.get(SAT), self.assistant, SAT)["schedule"]["label"], "11:30")
        personal(self.accountant, valid_until=date(2026, 10, 20))
        expired = self.row(self.get(), self.accountant)["schedule"]
        self.assertEqual((expired["label"], expired["source"]), ("09:00", "default"))

    def test_lateness_compares_qr_check_in_with_schedule(self):
        personal(self.assistant, work_start=time(9, 0), work_end=time(18, 0), late_grace_minutes=10)
        with frozen(local(*WED, 9, 8)):
            self.assertEqual(self.mark(self.assistant).data["session"]["late_minutes"], 0)
        with frozen(local(*WED, 9, 15)):
            self.assertEqual(self.mark(self.teacher).data["session"]["late_minutes"], 15)  # общий график, льгота 10
        data = self.get()
        on_time, late = self.row(data, self.assistant), self.row(data, self.teacher)
        self.assertEqual((on_time["status"], on_time["schedule"]["late_after"]), ("present", "09:10"))
        self.assertEqual((late["status"], late["late_minutes"], late["schedule"]["expected_start"]),
                         ("late", 15, "09:00"))

    # -- нерабочие дни и отсутствие графика ---------------------------------

    def test_days_off(self):
        personal(self.assistant, work_days=[0, 1])  # среда — выходной по личному графику
        data = self.get()
        row = self.row(data, self.assistant)
        self.assertEqual((row["status"], row["schedule"]["kind"], row["schedule"]["label"]),
                         ("day_off", "day_off", "Выходной"))
        self.assertIsNone(row["schedule"]["expected_start"])
        sunday = self.row(self.get(SUN), self.accountant, SUN)["schedule"]  # общий график Пн–Сб
        self.assertEqual((sunday["label"], sunday["source_label"]), ("Выходной", "Общий график"))

    def test_no_schedule_at_all(self):
        self.config.work_days = []
        self.config.save()
        row = self.row(self.get(), self.accountant)
        self.assertEqual((row["schedule"]["kind"], row["schedule"]["label"]), ("not_set", "Не задано"))
        self.assertNotEqual(row["status"], "absent")
        # Личное расписание задаёт время даже без общего графика.
        personal(self.accountant)
        self.assertEqual(self.row(self.get(), self.accountant)["schedule"]["label"], "10:00")

    def test_teacher_without_lessons(self):
        self.config.teacher_schedule_from_lessons = True
        self.config.save()
        schedule = self.row(self.get(), self.teacher)["schedule"]
        self.assertEqual((schedule["label"], schedule["source_label"]), ("Выходной", "Нет занятий"))

    # -- исключения из графика ------------------------------------------------

    def test_vacation_and_sick_leave(self):
        personal(self.assistant)
        exception(self.assistant, Kind.VACATION, MON, (2026, 10, 30), note="Ежегодный")
        exception(self.accountant, Kind.SICK_LEAVE, WED)
        data = self.get()
        vacation, sick = self.row(data, self.assistant), self.row(data, self.accountant)
        self.assertEqual((vacation["status"], vacation["status_label"], vacation["schedule"]["label"]),
                         ("vacation", "Отпуск", "Отпуск"))
        self.assertEqual(vacation["schedule"]["source_label"], "Ежегодный")
        self.assertEqual(sick["schedule"]["source_label"], "")
        self.assertEqual((sick["status"], sick["schedule"]["kind"], sick["schedule"]["label"]),
                         ("sick_leave", "sick_leave", "Больничный"))
        # Отпуск и больничный — не отсутствие и не рабочий день в посещаемости.
        counts = data["summary"]["counts"]
        self.assertEqual((counts["vacation"], counts["sick_leave"]), (1, 1))
        self.assertEqual(counts["absent"], len(data["rows"]) - 2)
        self.assertEqual(data["summary"]["expected_days"], len(data["rows"]) - 2)
        self.assertEqual([r["user"]["id"] for r in self.get(status="vacation")["rows"]], [self.assistant.pk])
        self.assertTrue(data["leave_tracking"])
        self.assertIn({"value": "sick_leave", "label": "Больничный"}, data["statuses"])

    def test_exception_day_off_and_custom_hours(self):
        exception(self.assistant, Kind.DAY_OFF, WED)
        exception(self.accountant, Kind.CUSTOM_HOURS, WED, work_start=time(12, 0), work_end=time(16, 0),
                  note="Сокращённый день")
        with frozen(local(*WED, 12, 30)):
            late = self.mark(self.accountant)
        self.assertEqual(late.data["session"]["late_minutes"], 30)  # от особых часов, а не от 09:00
        data = self.get()
        day_off, custom = self.row(data, self.assistant)["schedule"], self.row(data, self.accountant)["schedule"]
        self.assertEqual((day_off["label"], day_off["source"]), ("Выходной", "exception"))
        self.assertEqual((custom["label"], custom["expected_end"], custom["source_label"]),
                         ("12:00", "16:00", "Особые часы: Сокращённый день"))
        # Вне периода исключения — обычный график.
        self.assertEqual(self.row(self.get(MON), self.assistant, MON)["schedule"]["label"], "09:00")

    def test_check_in_during_vacation_is_never_late(self):
        exception(self.assistant, Kind.VACATION, WED)
        with frozen(local(*WED, 13, 0)):
            response = self.mark(self.assistant)
        self.assertEqual(response.data["session"]["late_minutes"], 0)
        self.assertIsNone(response.data["session"]["expected_start"])

    def test_exception_validation(self):
        exception(self.assistant, Kind.VACATION, MON, WED)
        for kind, start, end, extra, field in (
                (Kind.SICK_LEAVE, WED, SAT, {}, "date_from"),                       # пересечение
                (Kind.CUSTOM_HOURS, SAT, None, {}, "work_start"),                   # без часов
                (Kind.CUSTOM_HOURS, SAT, None, {"work_start": time(15, 0), "work_end": time(9, 0)}, "work_end"),
                (Kind.DAY_OFF, SAT, MON, {}, "date_to")):                            # конец раньше начала
            with self.subTest(kind=kind, field=field), self.assertRaises(ValidationError) as ctx:
                exception(self.assistant, kind, start, end, **extra)
            self.assertIn(field, ctx.exception.message_dict)
        clean = exception(self.assistant, Kind.DAY_OFF, SAT, work_start=time(9, 0))
        self.assertIsNone(clean.work_start)  # часы нужны только «особым часам»

    # -- фильтры, периоды, запросы -----------------------------------------------

    def test_filters_and_periods(self):
        personal(self.assistant)
        tracked = User.objects.filter(is_active=True).count()
        for params, days in (({"period": "today"}, 1), ({"period": "yesterday"}, 1),
                             ({"period": "this_week"}, 3), ({"period": "this_month"}, 21),
                             ({"period": "last_month"}, 30),
                             ({"period": "custom", "start_date": "2026-10-17", "end_date": "2026-10-21"}, 5)):
            with self.subTest(params=params):
                data = self.get(**params)
                self.assertEqual(len(data["rows"]), tracked * days)
                self.assertTrue(all("schedule" in r and r["schedule"]["label"] for r in data["rows"]))
        self.assertEqual(self.row(self.get(period="this_month"), self.assistant, MON)["schedule"]["label"], "10:00")
        by_role = self.get(role="assistant")["rows"]
        self.assertEqual({r["user"]["id"] for r in by_role}, {self.assistant.pk})
        self.assertEqual(by_role[0]["schedule"]["label"], "10:00")
        academy = self.get(department="academy")["rows"]
        self.assertEqual({r["user"]["id"] for r in academy}, {self.teacher.pk, self.assistant.pk, self.team_lead.pk})
        self.assertEqual(academy[0]["user"]["department_label"], "Академия")
        found = self.get(q="helper")["rows"]
        self.assertEqual([r["schedule"]["label"] for r in found], ["10:00"])

    def test_query_count_does_not_grow_with_days_or_employees(self):
        personal(self.assistant)
        exception(self.accountant, Kind.VACATION, MON)

        def count(**params):
            with CaptureQueriesContext(connection) as ctx:
                self.get(**params)
            return len(ctx.captured_queries)

        one_day = count(period="today")
        month = count(period="this_month")
        for i in range(10):
            personal(make_user(f"extra{i}", User.Role.MARKETING))
            exception(make_user(f"leave{i}", User.Role.SALES_MANAGER), Kind.SICK_LEAVE, WED)
        more_people = count(period="this_month")
        self.assertEqual(one_day, month)
        self.assertEqual(month, more_people)
