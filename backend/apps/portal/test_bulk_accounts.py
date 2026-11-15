"""Bulk student account generation: username format, CSPRNG passwords and
their storage, skipping of existing accounts, linking, scope, failures and
retry, one-time XLSX export, expiry, permissions and first-login change."""
from __future__ import annotations

import datetime as dt
import io
from unittest import mock

from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, Student
from apps.users.models import User

from .models import BulkAccountRun, BulkAccountRunItem, PortalAccount, StudentLink
from .services import accounts
from .services import bulk_accounts as bulk

PASSWORD = "Str0ngPassw0rd!"
TODAY = timezone.localdate()


class BulkBase(TestCase):
    def setUp(self):
        self.assistant = User.objects.create_user(
            username="assist", email="assist@okurmen.kg", password=PASSWORD, first_name="Asel",
            role=User.Role.ASSISTANT,
        )
        self.other_assistant = User.objects.create_user(
            username="assist2", email="assist2@okurmen.kg", password=PASSWORD, first_name="Nurgul",
            role=User.Role.ASSISTANT,
        )
        self.teacher = User.objects.create_user(
            username="trainer", email="trainer@okurmen.kg", password=PASSWORD, first_name="Islam",
            role=User.Role.TEACHER, is_verified=True,
        )
        self.team_lead = User.objects.create_user(
            username="lead", email="lead@okurmen.kg", password=PASSWORD, first_name="Lead",
            role=User.Role.TEAM_LEAD,
        )
        self.admin = User.objects.create_user(
            username="boss", email="boss@okurmen.kg", password=PASSWORD, first_name="Admin",
            role=User.Role.ADMIN,
        )
        course = Course.objects.create(name="Prog", count_lesson=12)
        self.g1 = Group.objects.create(name="PRO-01", course=course, start_date=TODAY - dt.timedelta(days=30))
        self.g2 = Group.objects.create(name="PRO-02", course=course, start_date=TODAY - dt.timedelta(days=30))
        self.begalys = Student.objects.create(first_name="Бегалы", last_name="Асанов", group=self.g1)
        self.begaly_2 = Student.objects.create(first_name="Бегалы", last_name="Жумабеков", group=self.g1)
        self.talant = Student.objects.create(first_name="Талант", last_name="Касымов", group=self.g2)
        self.bilal = Student.objects.create(first_name="Bilal", last_name="Omurov", group=self.g2)
        self.inactive = Student.objects.create(first_name="Ghost", last_name="Gone", group=self.g2, is_active=False)

    def students_count(self):
        return Student.objects.count()

    def run_all(self, performed_by=None, scope="all", group_ids=None):
        run = bulk.create_run(scope, group_ids or [], performed_by=performed_by or self.assistant)
        while run.items.filter(status=BulkAccountRunItem.Status.PENDING).exists():
            run = bulk.process_batch(run, performed_by=performed_by or self.assistant, limit=2)
        return run


class UsernameTests(BulkBase):
    def test_format_is_first_name_plus_two_digit_counter(self):
        self.assertEqual(bulk.plan_login("Бегалы"), "begaly01")
        self.assertEqual(bulk.plan_login("Талант"), "talant01")
        self.assertEqual(bulk.plan_login("Bilal"), "bilal01")

    def test_duplicate_names_get_unique_suffixes(self):
        run = self.run_all()
        logins = sorted(run.items.values_list("login", flat=True))
        self.assertIn("begaly01", logins)
        self.assertIn("begaly02", logins)
        self.assertEqual(len(logins), len(set(logins)))

    def test_taken_login_is_skipped(self):
        User.objects.create_user(username="talant01", email="x@okurmen.kg", password=PASSWORD, role=User.Role.TEACHER)
        self.assertEqual(bulk.plan_login("Талант"), "talant02")

    def test_reserved_logins_are_skipped_in_preview(self):
        self.assertEqual(bulk.plan_login("Bilal", reserved={"bilal01"}), "bilal02")

    def test_kyrgyz_letters_are_transliterated(self):
        self.assertEqual(bulk.plan_login("Өмүр"), "omur01")


class PasswordTests(BulkBase):
    def test_generated_passwords_are_unique_and_meet_policy(self):
        seen = set()
        for _ in range(300):
            password = accounts.generate_password()
            self.assertRegex(password, r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$")
            seen.add(password)
        self.assertEqual(len(seen), 300)

    def test_seal_round_trip_and_not_plaintext(self):
        token = bulk.seal("Hk7m-pQ3x-9tRw")
        self.assertNotIn("Hk7m", token)
        self.assertEqual(bulk.unseal(token), "Hk7m-pQ3x-9tRw")
        self.assertIsNone(bulk.unseal("garbage"))

    def test_no_plaintext_password_is_stored_anywhere(self):
        run = self.run_all()
        item = run.items.filter(status=BulkAccountRunItem.Status.CREATED).first()
        # The sealed token is the only thing kept while the export is pending.
        password = bulk.unseal(item.sealed_password)
        self.assertIsNotNone(password)
        for field in BulkAccountRunItem._meta.concrete_fields:
            value = getattr(item, field.attname)
            if isinstance(value, str):
                self.assertNotIn(password, value)
        for user in User.objects.all():
            self.assertNotEqual(user.password, password)
            self.assertNotIn(password, user.password)
        for log in LogEntry.objects.all():
            self.assertNotIn(password, log.change_message)
        self.assertTrue(User.objects.get(username=item.login).check_password(password))

    def test_new_accounts_are_marked_for_password_change(self):
        run = self.run_all()
        item = run.items.filter(status=BulkAccountRunItem.Status.CREATED).first()
        user = User.objects.get(username=item.login)
        self.assertEqual(user.role, User.Role.STUDENT_PARENT)
        self.assertTrue(user.is_active)
        self.assertTrue(user.portal_account.must_change_password)


class CreateRunTests(BulkBase):
    def test_creates_one_account_per_active_student_and_links_it(self):
        before_students = self.students_count()
        run = self.run_all()
        self.assertEqual(self.students_count(), before_students)  # no duplicate profiles
        self.assertEqual(run.items.count(), 4)  # the inactive student is out of scope
        self.assertFalse(run.items.filter(student=self.inactive).exists())
        for student in (self.begalys, self.begaly_2, self.talant, self.bilal):
            link = StudentLink.objects.get(student=student)
            self.assertEqual(link.account.user.role, User.Role.STUDENT_PARENT)
            self.assertEqual(accounts.account_of(student), link.account)
        self.assertEqual(run.status, BulkAccountRun.Status.COMPLETED)
        self.assertEqual(run.export_state, BulkAccountRun.ExportState.READY)

    def test_existing_accounts_are_detected_and_never_changed(self):
        existing_user = User.objects.create_user(
            username="old.login", email="old@portal.okurmenkids.invalid", password="Old-Pass-123",
            role=User.Role.STUDENT_PARENT, is_verified=True,
        )
        account = PortalAccount.objects.create(user=existing_user, must_change_password=False)
        StudentLink.objects.create(account=account, student=self.talant)
        hash_before = existing_user.password
        users_before = User.objects.count()

        run = self.run_all()

        self.assertEqual(run.items.get(student=self.talant).status, BulkAccountRunItem.Status.EXISTING)
        self.assertEqual(StudentLink.objects.filter(student=self.talant).count(), 1)
        existing_user.refresh_from_db()
        self.assertEqual(existing_user.password, hash_before)
        self.assertEqual(User.objects.count(), users_before + 3)  # three new, none for talant

    def test_group_scope_only_takes_selected_groups(self):
        run = self.run_all(scope="groups", group_ids=[self.g2.pk])
        self.assertEqual(set(run.items.values_list("student_id", flat=True)), {self.talant.pk, self.bilal.pk})
        self.assertFalse(StudentLink.objects.filter(student=self.begalys).exists())

    def test_single_group_is_a_group_selection(self):
        run = self.run_all(scope="groups", group_ids=[self.g1.pk])
        self.assertEqual(run.items.count(), 2)
        self.assertEqual(run.group_names, ["PRO-01"])

    def test_groups_scope_requires_existing_groups(self):
        with self.assertRaises(ValidationError):
            bulk.create_run("groups", [], performed_by=self.assistant)
        with self.assertRaises(ValidationError):
            bulk.create_run("groups", [999999], performed_by=self.assistant)

    def test_only_one_batch_at_a_time(self):
        bulk.create_run("all", [], performed_by=self.assistant)
        with self.assertRaises(bulk.RunConflict):
            bulk.create_run("all", [], performed_by=self.assistant)

    def test_the_run_is_logged_with_who_and_when(self):
        run = self.run_all()
        self.assertEqual(run.created_by, self.assistant)
        self.assertIsNotNone(run.created_at)
        self.assertTrue(LogEntry.objects.filter(
            user_id=self.assistant.pk, change_message__contains=f"пакет №{run.pk} запущен",
        ).exists())
        account = StudentLink.objects.get(student=self.talant).account
        self.assertTrue(LogEntry.objects.filter(object_id=str(account.user.pk), change_message__contains="создан для студента").exists())

    def test_preview_writes_nothing(self):
        users_before, runs_before = User.objects.count(), BulkAccountRun.objects.count()
        result = bulk.preview("all", [])
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["to_create"], 4)
        self.assertEqual(result["existing"], 0)
        self.assertEqual(User.objects.count(), users_before)
        self.assertEqual(BulkAccountRun.objects.count(), runs_before)
        self.assertIn("begaly02", [row["login"] for row in result["students"]])


class FailureAndRetryTests(BulkBase):
    def test_failures_are_reported_and_retry_only_repeats_them(self):
        real = accounts.provision_account

        def flaky(student, **kwargs):
            if student.pk == self.bilal.pk:
                raise ValidationError({"detail": "Тестовая ошибка."})
            return real(student, **kwargs)

        with mock.patch.object(accounts, "provision_account", side_effect=flaky):
            run = self.run_all()

        failed = run.items.get(status=BulkAccountRunItem.Status.FAILED)
        self.assertEqual(failed.student, self.bilal)
        self.assertIn("Тестовая ошибка.", failed.error)
        self.assertFalse(StudentLink.objects.filter(student=self.bilal).exists())
        created_ids = set(run.items.filter(status="created").values_list("student_id", flat=True))
        self.assertEqual(len(created_ids), 3)

        retry = bulk.create_retry_run(run, performed_by=self.assistant)
        self.assertEqual(retry.retry_of, run)
        self.assertEqual(list(retry.items.values_list("student_id", flat=True)), [self.bilal.pk])
        while retry.items.filter(status="pending").exists():
            retry = bulk.process_batch(retry, performed_by=self.assistant)
        self.assertEqual(retry.items.get().status, BulkAccountRunItem.Status.CREATED)
        self.assertEqual(StudentLink.objects.filter(student=self.bilal).count(), 1)

        # Nothing left to retry, and the earlier successes are not duplicated.
        with self.assertRaises(ValidationError):
            bulk.create_retry_run(run, performed_by=self.assistant)
        for student in (self.begalys, self.begaly_2, self.talant, self.bilal):
            self.assertEqual(StudentLink.objects.filter(student=student).count(), 1)

    def test_retry_skips_students_who_got_an_account_meanwhile(self):
        with mock.patch.object(accounts, "provision_account", side_effect=ValidationError({"detail": "x"})):
            run = self.run_all(scope="groups", group_ids=[self.g2.pk])
        # The student gets an account elsewhere (e.g. the single-student flow) before the retry.
        accounts.provision_account(self.talant, performed_by=self.assistant)
        retry = bulk.create_retry_run(run, performed_by=self.assistant)
        pending = list(retry.items.filter(status=BulkAccountRunItem.Status.PENDING).values_list("student_id", flat=True))
        self.assertEqual(pending, [self.bilal.pk])
        self.assertEqual(retry.items.get(student=self.talant).status, BulkAccountRunItem.Status.EXISTING)
        self.assertEqual(StudentLink.objects.filter(student=self.talant).count(), 1)

    def test_batches_are_resumable_and_do_not_repeat_work(self):
        run = bulk.create_run("all", [], performed_by=self.assistant)
        run = bulk.process_batch(run, performed_by=self.assistant, limit=1)
        self.assertEqual(run.status, BulkAccountRun.Status.RUNNING)
        self.assertEqual(run.items.filter(status="pending").count(), 3)
        run = bulk.process_batch(run, performed_by=self.assistant, limit=10)
        self.assertEqual(run.status, BulkAccountRun.Status.COMPLETED)
        self.assertEqual(User.objects.filter(role=User.Role.STUDENT_PARENT).count(), 4)
        run = bulk.process_batch(run, performed_by=self.assistant, limit=10)  # finished run: no-op
        self.assertEqual(User.objects.filter(role=User.Role.STUDENT_PARENT).count(), 4)


class ExportTests(BulkBase):
    def test_export_contains_exactly_this_runs_credentials_and_works_once(self):
        run = self.run_all()
        data = bulk.export_xlsx(run.pk, performed_by=self.assistant)
        sheet = load_workbook(io.BytesIO(data)).active
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(rows[0], bulk.EXPORT_HEADERS)
        self.assertEqual(len(rows) - 1, 4)
        by_login = {row[3]: row for row in rows[1:]}
        self.assertEqual(by_login["talant01"][0], self.talant.pk)
        self.assertEqual(by_login["talant01"][1], str(self.talant))
        self.assertEqual(by_login["talant01"][2], "PRO-02")
        self.assertEqual(by_login["talant01"][5], "Ожидает первого входа")
        self.assertTrue(User.objects.get(username="talant01").check_password(by_login["talant01"][4]))

        run.refresh_from_db()
        self.assertEqual(run.export_state, BulkAccountRun.ExportState.DOWNLOADED)
        self.assertFalse(run.items.exclude(sealed_password="").exists())
        with self.assertRaises(ValidationError):
            bulk.export_xlsx(run.pk, performed_by=self.assistant)

    def test_export_of_run_without_new_accounts_is_not_available(self):
        run = self.run_all()
        bulk.export_xlsx(run.pk, performed_by=self.assistant)
        again = bulk.create_run("all", [], performed_by=self.assistant)
        self.assertEqual(again.export_state, BulkAccountRun.ExportState.NONE)
        with self.assertRaises(ValidationError):
            bulk.export_xlsx(again.pk, performed_by=self.assistant)

    def test_expired_secrets_are_wiped_and_not_exported(self):
        run = self.run_all()
        BulkAccountRun.objects.filter(pk=run.pk).update(secrets_expire_at=timezone.now() - dt.timedelta(minutes=1))
        bulk.purge_all_expired()
        run.refresh_from_db()
        self.assertEqual(run.export_state, BulkAccountRun.ExportState.EXPIRED)
        self.assertFalse(run.items.exclude(sealed_password="").exists())
        with self.assertRaises(ValidationError):
            bulk.export_xlsx(run.pk, performed_by=self.assistant)


class ApiTests(BulkBase):
    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_full_flow_over_the_api(self):
        client = self.client_for(self.assistant)
        preview = client.get("/api/v1/assistant/bulk-accounts/preview/")
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertEqual(preview.data["to_create"], 4)

        self.assertEqual(client.post("/api/v1/assistant/bulk-accounts/runs/", {"scope": "all"}, format="json").status_code,
                         status.HTTP_400_BAD_REQUEST)  # confirmation is required
        created = client.post("/api/v1/assistant/bulk-accounts/runs/", {"scope": "all", "confirm": True}, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        run_id = created.data["id"]
        self.assertEqual(created.data["counts"]["pending"], 4)
        self.assertEqual(client.post("/api/v1/assistant/bulk-accounts/runs/", {"scope": "all", "confirm": True},
                                     format="json").status_code, status.HTTP_409_CONFLICT)

        for _ in range(5):
            response = client.post(f"/api/v1/assistant/bulk-accounts/runs/{run_id}/process/", {"limit": 2}, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            if response.data["counts"]["pending"] == 0:
                break
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["counts"]["created"], 4)
        self.assertTrue(response.data["export"]["downloadable"])
        self.assertNotIn("password", str(response.data).lower())

        exported = client.get(f"/api/v1/assistant/bulk-accounts/runs/{run_id}/export/")
        self.assertEqual(exported.status_code, status.HTTP_200_OK)
        self.assertEqual(exported["Cache-Control"], "no-store, private")
        self.assertIn("attachment", exported["Content-Disposition"])
        self.assertTrue(exported.content.startswith(b"PK"))  # XLSX is a zip container
        self.assertEqual(client.get(f"/api/v1/assistant/bulk-accounts/runs/{run_id}/export/").status_code,
                         status.HTTP_400_BAD_REQUEST)

    def test_only_admin_and_assistant_may_run_batches(self):
        for user in (self.teacher, self.team_lead):
            client = self.client_for(user)
            self.assertEqual(client.get("/api/v1/assistant/bulk-accounts/preview/").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(client.post("/api/v1/assistant/bulk-accounts/runs/",
                                         {"scope": "all", "confirm": True}, format="json").status_code,
                             status.HTTP_403_FORBIDDEN)
        self.assertEqual(APIClient().get("/api/v1/assistant/bulk-accounts/preview/").status_code,
                         status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client_for(self.admin).get("/api/v1/assistant/bulk-accounts/preview/").status_code,
                         status.HTTP_200_OK)

    def test_export_is_limited_to_the_starter_and_admin(self):
        run = self.run_all(performed_by=self.assistant)
        self.assertEqual(self.client_for(self.other_assistant).get(
            f"/api/v1/assistant/bulk-accounts/runs/{run.pk}/export/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client_for(self.admin).get(
            f"/api/v1/assistant/bulk-accounts/runs/{run.pk}/export/").status_code, status.HTTP_200_OK)

    def test_retry_endpoint(self):
        with mock.patch.object(accounts, "provision_account", side_effect=ValidationError({"detail": "boom"})):
            run = self.run_all()
        client = self.client_for(self.assistant)
        response = client.post(f"/api/v1/assistant/bulk-accounts/runs/{run.pk}/retry/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["retry_of"], run.pk)
        self.assertEqual(response.data["counts"]["pending"], 4)

    def test_new_account_must_change_password_before_using_the_portal(self):
        # The temporary password of a batch-created account is the one that was
        # handed over; reset_password gives us a known one to sign in with.
        self.run_all()
        account = StudentLink.objects.get(student=self.talant).account
        issued = accounts.reset_password(account, performed_by=self.assistant)
        token = APIClient().post("/api/v1/auth/login/", {"username": issued.login, "password": issued.password})
        self.assertEqual(token.status_code, status.HTTP_200_OK)
        auth = APIClient()
        auth.credentials(HTTP_AUTHORIZATION=f"Bearer {token.data['access']}")
        blocked = auth.get(f"/api/v1/portal/students/{self.talant.pk}/dashboard/")
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(blocked.json()["code"], "password_change_required")
        changed = auth.post("/api/v1/portal/password/", {
            "current_password": issued.password, "new_password": "MyOwn-Secret-2026",
            "new_password_confirm": "MyOwn-Secret-2026",
        }, format="json")
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(auth.get(f"/api/v1/portal/students/{self.talant.pk}/dashboard/").status_code,
                         status.HTTP_200_OK)

    def test_portal_accounts_cannot_reach_the_bulk_api(self):
        run = self.run_all()
        account = StudentLink.objects.get(student=self.talant).account
        issued = accounts.reset_password(account, performed_by=self.assistant)
        token = APIClient().post("/api/v1/auth/login/", {"username": issued.login, "password": issued.password})
        auth = APIClient()
        auth.credentials(HTTP_AUTHORIZATION=f"Bearer {token.data['access']}")
        self.assertEqual(auth.get("/api/v1/assistant/bulk-accounts/preview/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(auth.get(f"/api/v1/assistant/bulk-accounts/runs/{run.pk}/export/").status_code,
                         status.HTTP_403_FORBIDDEN)
