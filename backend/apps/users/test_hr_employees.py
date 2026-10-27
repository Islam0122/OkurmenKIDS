"""Раздел «Сотрудники» HR-менеджера: что HR может и чего не может —
проверки на сервере (API), а не только в интерфейсе."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from apps.staff_attendance.models import AttendanceLocation, AttendanceSession, AttendanceSettings
from apps.users.models import User

API = "/api/v1/hr/employees"
PASSWORD = "Str0ngPassw0rd!"
NEW_PASSWORD = "An0therStr0ng!pass"
TZ = ZoneInfo("Asia/Bishkek")


def make(username: str, role: str, **extra) -> User:
    return User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
                                    first_name=username.capitalize(), role=role, is_verified=True, **extra)


# Роли, которые HR назначает сам, и четыре, которые не назначает никогда.
ALLOWED = ("teacher", "team_lead", "assistant", "rop", "rom", "hr_manager", "sales_manager", "marketing")
FORBIDDEN = ("director", "accountant", "dop", "operations_director")


def login(username: str, password: str = PASSWORD) -> APIClient:
    client = APIClient()
    response = client.post("/api/v1/auth/login/", {"username": username, "password": password}, format="json")
    assert response.status_code == 200, response.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return client


class HREmployeesTests(TestCase):
    def setUp(self):
        self.hr = make("hr", User.Role.HR_MANAGER)
        self.rop = make("rop", User.Role.ROP, last_name="Иванов")
        self.sales = make("sales", User.Role.SALES_MANAGER)
        self.marketing = make("marketing", User.Role.MARKETING)
        # Защищённые должности и администратор — вне полномочий HR.
        self.protected = {role: make(f"p_{role}", role) for role in (*FORBIDDEN, User.Role.ADMIN)}
        self.other_hr = make("hr2", User.Role.HR_MANAGER)
        self.client = login("hr")

    # --- кто вообще имеет доступ -------------------------------------------

    def test_only_hr_reaches_the_api(self):
        self.assertEqual(APIClient().get(f"{API}/").status_code, 401)
        for username in ("rop", "sales", "p_admin", "p_director", "p_accountant", "p_dop", "p_operations_director"):
            client = APIClient()
            client.force_authenticate(User.objects.get(username=username))
            self.assertEqual(client.get(f"{API}/").status_code, 403, username)
        # Изоляция ролей с базовым доступом не мешает HR, но LMS для него закрыта.
        self.assertEqual(self.client.get("/api/v1/trainers/").status_code, 403)

    def test_inactive_hr_is_denied(self):
        self.hr.is_active = False
        self.hr.save()
        client = APIClient()
        client.force_authenticate(self.hr)
        self.assertEqual(client.get(f"{API}/").status_code, 403)

    # --- список, поиск, фильтры --------------------------------------------

    def test_list_shows_only_manageable_employees(self):
        data = self.client.get(f"{API}/", {"page_size": 100}).data
        ids = {row["id"] for row in data["results"]}
        # Без себя, защищённых должностей и администраторов.
        self.assertEqual(ids, {self.rop.pk, self.sales.pk, self.marketing.pk, self.other_hr.pk})
        row = next(r for r in data["results"] if r["id"] == self.rop.pk)
        self.assertEqual(row["role_label"], "РОП — руководитель отдела продаж")
        self.assertTrue(row["can_manage"])
        peer = next(r for r in data["results"] if r["id"] == self.other_hr.pk)
        self.assertFalse(peer["can_manage"])
        self.assertTrue(row["is_active"])
        self.assertIn("created_at", row)
        self.assertNotIn("password", row)

    def test_search_and_filters(self):
        self.marketing.is_active = False
        self.marketing.save()
        by_name = self.client.get(f"{API}/", {"search": "Иванов"}).data["results"]
        by_role = self.client.get(f"{API}/", {"role": "sales_manager"}).data["results"]
        inactive = self.client.get(f"{API}/", {"is_active": "false"}).data["results"]
        protected = self.client.get(f"{API}/", {"role": "accountant"}).data["results"]
        self.assertEqual(self.client.get(f"{API}/", {"role": "director"}).data["results"], [])
        self.assertEqual([r["id"] for r in by_name], [self.rop.pk])
        self.assertEqual([r["id"] for r in by_role], [self.sales.pk])
        self.assertEqual([r["id"] for r in inactive], [self.marketing.pk])
        self.assertEqual(protected, [])

    def test_meta_lists_assignable_and_protected_roles(self):
        meta = self.client.get(f"{API}/meta/").data
        self.assertEqual([r["value"] for r in meta["roles"]], list(ALLOWED))
        self.assertEqual([r["value"] for r in meta["protected_roles"]], list(FORBIDDEN))
        self.assertFalse({"admin", *FORBIDDEN} & {r["value"] for r in meta["roles"]})
        labels = {r["value"]: r["label"] for r in [*meta["roles"], *meta["protected_roles"]]}
        self.assertEqual(labels["dop"], "ДОП — директор отдела продаж")
        self.assertEqual(labels["rop"], "РОП — руководитель отдела продаж")
        self.assertEqual(labels["rom"], "РОМ — руководитель отдела маркетинга")
        self.assertEqual(labels["director"], "Директор")
        self.assertEqual(labels["accountant"], "Бухгалтер")
        self.assertEqual(labels["operations_director"], "Операционный директор")

    # --- создание ----------------------------------------------------------

    def _new(self, **over):
        body = {"username": "newbie", "email": "newbie@okurmen.kg", "first_name": "Нурлан", "last_name": "Н",
                "role": "sales_manager", "password": PASSWORD, "password_confirm": PASSWORD}
        body.update(over)
        return self.client.post(f"{API}/", body, format="json")

    def test_create_allowed_role_and_new_employee_can_log_in(self):
        response = self._new()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("password", response.data)
        user = User.objects.get(username="newbie")
        self.assertEqual(user.role, User.Role.SALES_MANAGER)
        self.assertNotEqual(user.password, PASSWORD)  # только хеш
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff or user.is_superuser)
        status = login("newbie").get("/api/v1/staff-attendance/me/status/")
        self.assertEqual(status.status_code, 200)

    def test_create_with_each_allowed_role(self):
        from apps.users.models import Teacher

        for role in ALLOWED:
            response = self._new(username=f"n_{role}", email=f"n_{role}@okurmen.kg", role=role)
            self.assertEqual(response.status_code, 201, (role, response.data))
            self.assertEqual(response.data["role"], role)
            user = User.objects.get(username=f"n_{role}")
            self.assertEqual(user.role, role)
            self.assertTrue(user.check_password(PASSWORD))
            self.assertFalse(user.is_staff or user.is_superuser, role)
            login(f"n_{role}")  # учётная запись рабочая: вход по паролю от HR
            # Новый сотрудник сразу виден в списке HR.
            listed = self.client.get(f"{API}/", {"search": f"n_{role}"}).data["results"]
            self.assertEqual([r["id"] for r in listed], [user.pk], role)
        # Тренер создаётся вместе с профилем тренера.
        self.assertTrue(Teacher.objects.filter(user__username="n_teacher").exists())

    def test_create_with_protected_or_privileged_role_is_rejected(self):
        for role in (*FORBIDDEN, "admin", "superuser", ""):
            response = self._new(username=f"x_{role}", email=f"x_{role}@okurmen.kg", role=role)
            self.assertEqual(response.status_code, 400, role)
            self.assertIn("role", response.data)
        self.assertFalse(User.objects.filter(username__startswith="x_").exists())

    def test_create_ignores_privilege_fields(self):
        response = self._new(is_staff=True, is_superuser=True, is_verified=False)
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="newbie")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_validates_password_and_uniqueness(self):
        self.assertIn("password_confirm", self._new(password_confirm="other").data)
        self.assertIn("password", self._new(password="123", password_confirm="123").data)
        self.assertIn("username", self._new(username="ROP").data)
        self.assertIn("email", self._new(email="rop@okurmen.kg").data)

    # --- изменение ---------------------------------------------------------

    def test_edit_allowed_employee(self):
        response = self.client.patch(f"{API}/{self.rop.pk}/", {"first_name": "Азамат", "role": "marketing"},
                                     format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.rop.refresh_from_db()
        self.assertEqual((self.rop.first_name, self.rop.role), ("Азамат", User.Role.MARKETING))

    def test_edit_to_each_allowed_role_except_teacher(self):
        # HR — последним: после этого сотрудник становится коллегой-HR,
        # и дальше его карточка только для просмотра.
        for role in [*(r for r in ALLOWED if r not in ("teacher", "hr_manager")), "hr_manager"]:
            response = self.client.patch(f"{API}/{self.sales.pk}/", {"role": role}, format="json")
            self.assertEqual(response.status_code, 200, (role, response.data))
            self.sales.refresh_from_db()
            self.assertEqual(self.sales.role, role)
        self.assertEqual(self.client.patch(f"{API}/{self.sales.pk}/", {"role": "rop"}, format="json").status_code, 403)

    def test_teacher_role_is_not_switched_on_existing_account(self):
        response = self.client.patch(f"{API}/{self.rop.pk}/", {"role": "teacher"}, format="json")
        self.assertEqual(response.status_code, 400)
        self._new(username="t1", email="t1@okurmen.kg", role="teacher", first_name="Тренер")
        teacher = User.objects.get(username="t1")
        self.assertEqual(self.client.patch(f"{API}/{teacher.pk}/", {"role": "rop"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"{API}/{teacher.pk}/", {"first_name": "Бакыт"},
                                           format="json").status_code, 200)
        teacher.refresh_from_db()
        self.assertEqual((teacher.role, teacher.first_name), (User.Role.TEACHER, "Бакыт"))

    def test_cannot_promote_employee_to_protected_role(self):
        for role in (*FORBIDDEN, "admin"):
            response = self.client.patch(f"{API}/{self.rop.pk}/", {"role": role}, format="json")
            self.assertEqual(response.status_code, 400, role)
        response = self.client.patch(f"{API}/{self.rop.pk}/", {"is_staff": True, "is_superuser": True,
                                                                "password": "hacked"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.rop.refresh_from_db()
        self.assertEqual(self.rop.role, User.Role.ROP)
        self.assertFalse(self.rop.is_staff or self.rop.is_superuser)
        self.assertTrue(self.rop.check_password(PASSWORD))

    def test_protected_employees_are_refused_for_every_action(self):
        self._assert_refused([*self.protected.values(), self.hr], include_get=True)

    def test_peer_hr_is_view_only(self):
        card = self.client.get(f"{API}/{self.other_hr.pk}/")
        self.assertEqual(card.status_code, 200)
        self.assertFalse(card.data["can_manage"])
        self._assert_refused([self.other_hr], include_get=False)

    def test_new_hr_created_by_hr_gets_no_extra_rights(self):
        self._new(username="hr3", email="hr3@okurmen.kg", role="hr_manager", is_staff=True)
        created = User.objects.get(username="hr3")
        self.assertFalse(created.is_staff or created.is_superuser)
        # Созданный HR — такой же коллега: только просмотр.
        self.assertEqual(self.client.post(f"{API}/{created.pk}/deactivate/").status_code, 403)
        # И у нового HR те же границы: защищённые должности ему недоступны.
        client = login("hr3")
        self.assertEqual(client.post(f"{API}/", {
            "username": "boss", "email": "boss@okurmen.kg", "first_name": "Б", "role": "director",
            "password": PASSWORD, "password_confirm": PASSWORD}, format="json").status_code, 400)
        self.assertEqual(client.patch(f"{API}/{self.hr.pk}/", {"first_name": "x"}, format="json").status_code, 403)

    def _assert_refused(self, targets, include_get):
        for target in targets:
            before = (target.first_name, target.role, target.is_active, target.password)
            calls = (
                *((("get", f"{API}/{target.pk}/", None),) if include_get else ()),
                ("patch", f"{API}/{target.pk}/", {"first_name": "Hacked"}),
                ("put", f"{API}/{target.pk}/", {"username": target.username, "email": target.email,
                                                 "first_name": "Hacked", "role": "rop"}),
                ("post", f"{API}/{target.pk}/set-password/", {"password": NEW_PASSWORD,
                                                              "password_confirm": NEW_PASSWORD}),
                ("post", f"{API}/{target.pk}/deactivate/", None),
                ("post", f"{API}/{target.pk}/activate/", None),
            )
            for method, url, body in calls:
                response = getattr(self.client, method)(url, body, format="json")
                self.assertEqual(response.status_code, 403, f"{target.role} {method} {url}")
            target.refresh_from_db()
            self.assertEqual((target.first_name, target.role, target.is_active, target.password), before, target.role)

    def test_hr_cannot_change_own_account(self):
        response = self.client.patch(f"{API}/{self.hr.pk}/", {"role": "rop"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.hr.refresh_from_db()
        self.assertEqual(self.hr.role, User.Role.HR_MANAGER)

    def test_no_delete(self):
        self.assertEqual(self.client.delete(f"{API}/{self.rop.pk}/").status_code, 405)
        self.assertTrue(User.objects.filter(pk=self.rop.pk).exists())

    def test_unknown_employee_is_404(self):
        self.assertEqual(self.client.get(f"{API}/999999/").status_code, 404)

    # --- пароль ------------------------------------------------------------

    def test_set_password(self):
        url = f"{API}/{self.sales.pk}/set-password/"
        self.assertEqual(self.client.post(url, {"password": NEW_PASSWORD, "password_confirm": "x"},
                                          format="json").status_code, 400)
        response = self.client.post(url, {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.data)
        self.sales.refresh_from_db()
        self.assertTrue(self.sales.check_password(NEW_PASSWORD))
        login("sales", NEW_PASSWORD)

    # --- деактивация -------------------------------------------------------

    def test_deactivate_keeps_history_and_blocks_login(self):
        office = AttendanceLocation.objects.first() or AttendanceLocation.objects.create(
            name="Офис", latitude=42.0, longitude=74.0)
        AttendanceSettings.load()
        moment = datetime(2026, 10, 21, 9, 0, tzinfo=TZ)
        session = AttendanceSession.objects.create(
            user=self.rop, location=office, work_date=moment.date(), checked_in_at=moment,
            checked_out_at=moment.replace(hour=18), status=AttendanceSession.Status.CLOSED)

        response = self.client.post(f"{API}/{self.rop.pk}/deactivate/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])
        self.rop.refresh_from_db()
        self.assertFalse(self.rop.is_active)
        self.assertTrue(AttendanceSession.objects.filter(pk=session.pk).exists())
        failed = APIClient().post("/api/v1/auth/login/", {"username": "rop", "password": PASSWORD}, format="json")
        self.assertEqual(failed.status_code, 400)

        self.assertEqual(self.client.post(f"{API}/{self.rop.pk}/activate/").status_code, 200)
        self.rop.refresh_from_db()
        self.assertTrue(self.rop.is_active)
        login("rop")


class HREmployeeHistoryTests(TestCase):
    def setUp(self):
        self.hr = make("hr", User.Role.HR_MANAGER)
        self.rop = make("rop", User.Role.ROP)
        self.client = login("hr")

    def test_actions_are_logged_without_passwords(self):
        from apps.recruitment.models import HRActivity

        self.client.patch(f"{API}/{self.rop.pk}/", {"role": "marketing", "first_name": "Новое"}, format="json")
        self.client.post(f"{API}/{self.rop.pk}/set-password/", {"password": NEW_PASSWORD,
                                                                 "password_confirm": NEW_PASSWORD}, format="json")
        self.client.post(f"{API}/{self.rop.pk}/deactivate/")
        self.client.post(f"{API}/{self.rop.pk}/activate/")
        entries = list(HRActivity.objects.filter(employee=self.rop).order_by("id"))
        self.assertEqual([e.kind for e in entries], ["employee_updated", "employee_password", "employee_deactivated",
                                                     "employee_activated"])
        self.assertIn(f"{User.Role.ROP.label} → {User.Role.MARKETING.label}", entries[0].message)
        self.assertTrue(all(e.actor_id == self.hr.pk for e in entries))
        self.assertFalse(any(NEW_PASSWORD in e.message or PASSWORD in e.message for e in entries))

    def test_card_shows_history_and_no_password(self):
        self.client.post(f"{API}/{self.rop.pk}/deactivate/")
        card = self.client.get(f"{API}/{self.rop.pk}/").data
        self.assertFalse(card["is_active"])
        self.assertIsNone(card["hired_from"])
        self.assertEqual(card["history"][0]["kind"], "employee_deactivated")
        self.assertNotIn("password", card)

    def test_ordering_and_page_size(self):
        User.objects.filter(pk=self.rop.pk).update(last_name="Якупов")
        make("sales", User.Role.SALES_MANAGER, last_name="Аманов")
        data = self.client.get(f"{API}/", {"ordering": "last_name", "page_size": 1}).data
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["username"], "sales")


class HRAttendanceScopeTests(TestCase):
    """HR не отвечает за приход и уход: отчёты посещаемости ему закрыты,
    своя отметка прихода остаётся."""

    def setUp(self):
        self.hr = make("hr", User.Role.HR_MANAGER)
        self.rop = make("rop", User.Role.ROP)
        self.client = login("hr")

    def test_attendance_reports_are_closed_for_hr(self):
        api = "/api/v1/staff-attendance/admin"
        for url in ("records/", "meta/", "overview/", f"employees/{self.rop.pk}/", "locations/"):
            self.assertEqual(self.client.get(f"{api}/{url}").status_code, 403, url)

    def test_own_check_in_status_still_works(self):
        self.assertEqual(self.client.get("/api/v1/staff-attendance/me/status/").status_code, 200)
