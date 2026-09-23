import importlib
import io
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client as DjangoClient
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, clear_url_caches, reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.users.models import Subject, Teacher, User
from apps.users.services import change_teacher_password_and_send, create_teacher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_admin(username="admin", email="admin@okurmenkids.local") -> User:
    return User.objects.create_superuser(
        username=username, email=email, password="Str0ng!Pass123"
    )


def make_teacher(
    username="teacher1",
    email="teacher1@okurmenkids.local",
    password="Str0ng!Pass123",
    verified=True,
    send_email=False,
):
    result = create_teacher(
        username=username,
        email=email,
        first_name="Айбек",
        last_name="Тестов",
        password=password,
        send_email=send_email,
    )
    teacher = result.teacher
    if verified:
        teacher.user.is_verified = True
        teacher.user.save(update_fields=["is_verified"])
    return teacher, password


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class UserModelTests(TestCase):
    def test_create_admin_via_createsuperuser_has_admin_role(self):
        admin = make_admin()
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_admin)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_verified)
        self.assertTrue(admin.is_active)

    def test_create_teacher_has_teacher_role(self):
        teacher, _ = make_teacher()
        self.assertEqual(teacher.user.role, User.Role.TEACHER)
        self.assertTrue(teacher.user.is_teacher)

    def test_email_must_be_unique(self):
        User.objects.create_user(
            username="u1", email="dup@example.com", password="x", role=User.Role.TEACHER
        )
        with self.assertRaises(Exception):
            User.objects.create_user(
                username="u2", email="dup@example.com", password="x", role=User.Role.TEACHER
            )

    def test_user_model_has_no_email_verification_field(self):
        field_names = [f.name for f in User._meta.get_fields()]
        self.assertNotIn("is_email_verified", field_names)


# ---------------------------------------------------------------------------
# Teacher creation — Admin sets the password
# ---------------------------------------------------------------------------

class TeacherCreationTests(TestCase):
    def test_create_teacher_creates_user_and_profile_atomically(self):
        subject = Subject.objects.create(name="Python")
        result = create_teacher(
            username="teacher2",
            email="teacher2@okurmenkids.local",
            first_name="Нурлан",
            password="Python2026!",
            subjects=[subject],
            send_email=False,
        )
        self.assertTrue(Teacher.objects.filter(pk=result.teacher.pk).exists())
        self.assertEqual(result.teacher.user.role, User.Role.TEACHER)
        self.assertIn(subject, result.teacher.subjects.all())

    def test_new_teacher_is_not_verified_by_default(self):
        result = create_teacher(
            username="teacher3",
            email="teacher3@okurmenkids.local",
            first_name="Данияр",
            password="Python2026!",
            send_email=False,
        )
        self.assertFalse(result.teacher.user.is_verified)

    def test_admin_supplied_password_is_hashed_not_stored_plaintext(self):
        password = "Python2026!"
        result = create_teacher(
            username="teacher4",
            email="teacher4@okurmenkids.local",
            first_name="Эрлан",
            password=password,
            send_email=False,
        )
        user = User.objects.get(pk=result.teacher.user_id)
        self.assertNotEqual(user.password, password)
        self.assertTrue(user.check_password(password))

    def test_password_works_for_login(self):
        teacher, password = make_teacher(username="teacher5", email="teacher5@okurmenkids.local")
        self.assertTrue(teacher.user.check_password(password))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class AuthenticationAPITests(APITestCase):
    def setUp(self):
        self.login_url = reverse("auth-login")
        self.refresh_url = reverse("auth-refresh")
        self.me_url = reverse("auth-me")

    def test_valid_login_returns_tokens_and_user(self):
        teacher, password = make_teacher()
        response = self.client.post(
            self.login_url, {"username": teacher.user.username, "password": password}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["role"], "teacher")
        self.assertNotIn("password", response.data["user"])
        self.assertNotIn("is_email_verified", response.data["user"])

    def test_invalid_password_rejected(self):
        teacher, _ = make_teacher()
        response = self.client.post(
            self.login_url, {"username": teacher.user.username, "password": "wrong"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_user_cannot_login(self):
        teacher, password = make_teacher()
        teacher.user.is_active = False
        teacher.user.save()
        response = self.client.post(
            self.login_url, {"username": teacher.user.username, "password": password}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unverified_teacher_cannot_login(self):
        teacher, password = make_teacher(
            username="teacher6", email="teacher6@okurmenkids.local", verified=False
        )
        response = self.client.post(
            self.login_url, {"username": teacher.user.username, "password": password}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("подтверждён", str(response.data["detail"]))

    def test_admin_can_login_without_extra_verification(self):
        admin = make_admin()
        response = self.client.post(
            self.login_url, {"username": admin.username, "password": "Str0ng!Pass123"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_jwt_refresh(self):
        teacher, password = make_teacher()
        login = self.client.post(
            self.login_url, {"username": teacher.user.username, "password": password}
        )
        response = self.client.post(self.refresh_url, {"refresh": login.data["refresh"]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_me_endpoint_requires_authentication(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_endpoint_returns_own_profile(self):
        teacher, password = make_teacher()
        login = self.client.post(
            self.login_url, {"username": teacher.user.username, "password": password}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], teacher.user.username)


# ---------------------------------------------------------------------------
# Permissions / Trainer API
# ---------------------------------------------------------------------------

class TrainerPermissionsAPITests(APITestCase):
    def setUp(self):
        self.login_url = reverse("auth-login")
        self.trainers_url = reverse("trainer-list")
        self.trainer_me_url = reverse("trainer-me")

        self.admin = make_admin()
        self.teacher_a, self.password_a = make_teacher(
            username="teacherA", email="teacherA@okurmenkids.local"
        )
        self.teacher_b, self.password_b = make_teacher(
            username="teacherB", email="teacherB@okurmenkids.local"
        )

    def _login(self, username, password):
        response = self.client.post(self.login_url, {"username": username, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_admin_has_full_access_to_trainer_list(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        response = self.client.get(self.trainers_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_cannot_list_trainers(self):
        self._login(self.teacher_a.user.username, self.password_a)
        response = self.client.get(self.trainers_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_can_access_own_profile_via_me(self):
        self._login(self.teacher_a.user.username, self.password_a)
        response = self.client.get(self.trainer_me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["username"], self.teacher_a.user.username)

    def test_teacher_cannot_access_another_teachers_record(self):
        self._login(self.teacher_a.user.username, self.password_a)
        url = reverse("trainer-detail", args=[self.teacher_b.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_cannot_create_trainer(self):
        self._login(self.teacher_a.user.username, self.password_a)
        response = self.client.post(self.trainers_url, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_trainer_with_own_password_and_email_is_sent(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        response = self.client.post(
            self.trainers_url,
            {
                "username": "newteacher",
                "email": "newteacher@okurmenkids.local",
                "first_name": "Айгерим",
                "password": "Python2026!",
                "password_confirm": "Python2026!",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="newteacher", role=User.Role.TEACHER)
        self.assertTrue(user.check_password("Python2026!"))
        self.assertFalse(user.is_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("newteacher@okurmenkids.local", mail.outbox[0].to)
        self.assertIn("Python2026!", mail.outbox[0].body)
        self.assertNotIn("password", response.data.get("user", {}))

    def test_create_trainer_rejects_mismatched_passwords(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        response = self.client.post(
            self.trainers_url,
            {
                "username": "badpair",
                "email": "badpair@okurmenkids.local",
                "first_name": "Тест",
                "password": "Python2026!",
                "password_confirm": "Different2026!",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="badpair").exists())

    def test_admin_verifies_trainer_account(self):
        unverified, _ = make_teacher(
            username="teacherC", email="teacherC@okurmenkids.local", verified=False
        )
        self._login(self.admin.username, "Str0ng!Pass123")
        url = reverse("trainer-verify", args=[unverified.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        unverified.user.refresh_from_db()
        self.assertTrue(unverified.user.is_verified)


# ---------------------------------------------------------------------------
# Trainer credential lock-down
# ---------------------------------------------------------------------------

class TrainerCannotChangeCredentialsTests(APITestCase):
    def setUp(self):
        self.login_url = reverse("auth-login")
        self.teacher, self.password = make_teacher()
        response = self.client.post(
            self.login_url, {"username": self.teacher.user.username, "password": self.password}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_teacher_cannot_patch_own_trainer_record(self):
        url = reverse("trainer-detail", args=[self.teacher.pk])
        response = self.client.patch(url, {"phone": "+996700000000"})
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED),
        )

    def test_no_change_password_endpoint_exists_for_teacher(self):
        response = self.client.post("/api/v1/auth/change-password/", {})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Password change by Admin
# ---------------------------------------------------------------------------

class ChangeTeacherPasswordTests(TestCase):
    def test_change_password_invalidates_old_and_sets_new(self):
        teacher, old_password = make_teacher(
            username="teacher7", email="teacher7@okurmenkids.local", send_email=False
        )
        result = change_teacher_password_and_send(teacher, "NewPython2026!")
        teacher.user.refresh_from_db()
        self.assertFalse(teacher.user.check_password(old_password))
        self.assertTrue(teacher.user.check_password("NewPython2026!"))
        self.assertTrue(result.email_sent)

    def test_new_password_is_sent_by_email(self):
        teacher, _ = make_teacher(
            username="teacher8", email="teacher8@okurmenkids.local", send_email=False
        )
        change_teacher_password_and_send(teacher, "AnotherPass2026!")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["teacher8@okurmenkids.local"])
        self.assertIn("AnotherPass2026!", message.body)
        self.assertIn(teacher.user.username, message.body)


# ---------------------------------------------------------------------------
# Email verification must be fully gone
# ---------------------------------------------------------------------------

class EmailVerificationRemovedTests(TestCase):
    def test_services_module_has_no_email_verification_helpers(self):
        from apps.users import services

        for name in (
            "EmailVerificationTokenGenerator",
            "email_verification_token_generator",
            "build_email_verification_token",
            "verify_email",
            "send_email_verification_link",
            "generate_temporary_password",
        ):
            self.assertFalse(hasattr(services, name), f"{name} should have been removed")

    def test_verify_email_url_does_not_exist(self):
        response = self.client.get("/api/v1/auth/verify-email/abc/def/")
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Credentials email on creation
# ---------------------------------------------------------------------------

class CredentialsEmailTests(TestCase):
    def test_credentials_email_sent_on_creation_with_admin_password(self):
        create_teacher(
            username="teacher9",
            email="teacher9@okurmenkids.local",
            first_name="Гульнара",
            password="Gulnara2026!",
        )
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["teacher9@okurmenkids.local"])
        self.assertIn("teacher9", message.body)
        self.assertIn("Gulnara2026!", message.body)


# ---------------------------------------------------------------------------
# Teacher Import / Export — apps.users.import_export.teachers
# ---------------------------------------------------------------------------

def _csv_file(content: str, name: str = "teachers.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


class TeacherImportExportAPITests(APITestCase):
    def setUp(self):
        self.login_url = reverse("auth-login")
        self.export_url = reverse("trainer-export")
        self.import_url = reverse("trainer-import-file")
        self.preview_url = reverse("trainer-import-preview")

        self.admin = make_admin()
        self.subject = Subject.objects.create(name="Python")
        self.teacher_a, self.password_a = make_teacher(
            username="teacherA", email="teacherA@okurmenkids.local"
        )
        self.teacher_a.subjects.set([self.subject])

    def _login(self, username, password):
        response = self.client.post(self.login_url, {"username": username, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_export_returns_csv_without_password(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        response = self.client.get(self.export_url, {"export_format": "csv"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.content.decode("utf-8-sig")
        header = content.splitlines()[0]
        self.assertEqual(
            header,
            "username,email,first_name,last_name,role,is_active,is_verified,phone,"
            "position,experience_years,bio,hire_date,subjects",
        )
        self.assertNotIn("password", content.lower())
        self.assertIn("teacherA", content)
        self.assertIn("Python", content)

    def test_export_xlsx_format(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        response = self.client.get(self.export_url, {"export_format": "xlsx"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_teacher_cannot_export_teachers(self):
        self._login(self.teacher_a.user.username, self.password_a)
        response = self.client.get(self.export_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_cannot_import_teachers(self):
        self._login(self.teacher_a.user.username, self.password_a)
        response = self.client.post(
            self.import_url, {"file": _csv_file("username,email,first_name\nx,x@x.com,X\n")}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="x").exists())

    def test_import_creates_new_teacher_with_generated_password(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = (
            "username,email,first_name,last_name,phone,position,experience_years,"
            "hire_date,subjects,is_active\n"
            "newteacher,newteacher@okurmenkids.local,New,Teacher,+996555111111,"
            "Trainer,2,2024-01-01,Python,true\n"
        )
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data, {"created": 1, "updated": 0, "total": 1})

        user = User.objects.get(username="newteacher")
        self.assertEqual(user.role, User.Role.TEACHER)
        self.assertFalse(user.is_verified)
        self.assertTrue(user.has_usable_password())
        # A random password was generated — it must not be the empty string
        # and must not appear anywhere in the response.
        self.assertNotIn("password", str(response.data).lower())

        teacher = Teacher.objects.get(user=user)
        self.assertEqual(teacher.position, "Trainer")
        self.assertEqual(teacher.experience_years, 2)
        self.assertIn(self.subject, teacher.subjects.all())

    def test_password_is_never_exported(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        response = self.client.get(self.export_url)
        body = response.content.decode("utf-8-sig").lower()
        self.assertNotIn("password", body)
        self.assertNotIn(self.teacher_a.user.password.lower(), body)

    def test_import_updates_existing_teacher_found_by_username(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = (
            f"username,email,first_name,last_name,position\n"
            f"teacherA,teacherA@okurmenkids.local,Айбек,Обновлённый,Senior Trainer\n"
        )
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data, {"created": 0, "updated": 1, "total": 1})

        self.teacher_a.refresh_from_db()
        self.teacher_a.user.refresh_from_db()
        self.assertEqual(self.teacher_a.user.last_name, "Обновлённый")
        self.assertEqual(self.teacher_a.position, "Senior Trainer")
        # No duplicate User was created.
        self.assertEqual(User.objects.filter(username="teacherA").count(), 1)

    def test_import_updates_existing_teacher_found_by_email(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = (
            f"username,email,first_name,position\n"
            f"a-different-username,teacherA@okurmenkids.local,Айбек,Lead Trainer\n"
        )
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["updated"], 1)
        self.teacher_a.user.refresh_from_db()
        self.assertEqual(self.teacher_a.user.username, "a-different-username")

    def test_import_with_unknown_subject_is_rejected_and_atomic(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        before = User.objects.count()
        csv_content = (
            "username,email,first_name,subjects\n"
            "valid1,valid1@okurmenkids.local,Valid,Python\n"
            "valid2,valid2@okurmenkids.local,Valid,C++\n"
        )
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["invalid"], 1)
        self.assertIn('"C++"', response.data["errors"][0]["errors"][0])
        # Atomic rollback: not even the valid row was saved.
        self.assertEqual(User.objects.count(), before)
        self.assertFalse(User.objects.filter(username="valid1").exists())

    def test_subject_is_never_auto_created(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = "username,email,first_name,subjects\nx,x@x.com,X,Совершенно Новый Предмет\n"
        self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertFalse(Subject.objects.filter(name="Совершенно Новый Предмет").exists())

    def test_import_invalid_email_is_rejected(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = "username,email,first_name\nbademail,not-an-email,X\n"
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data["errors"][0]["errors"][0].lower())

    def test_import_duplicate_username_within_file_is_rejected(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = (
            "username,email,first_name\n"
            "dupuser,dup1@okurmenkids.local,X\n"
            "dupuser,dup2@okurmenkids.local,Y\n"
        )
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(any("Дублирующийся" in e["errors"][0] for e in response.data["errors"]))

    def test_import_missing_required_fields_is_rejected(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = "username,email,first_name\n,missing@x.com,\n"
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        errors = " ".join(response.data["errors"][0]["errors"])
        self.assertIn("username", errors)
        self.assertIn("first_name", errors)

    def test_import_invalid_experience_years_is_rejected(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = "username,email,first_name,experience_years\nx,x@x.com,X,not-a-number\n"
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_import_invalid_date_is_rejected(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = "username,email,first_name,hire_date\nx,x@x.com,X,not-a-date\n"
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_import_cannot_hijack_existing_admin_account(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        csv_content = f"username,email,first_name\n{self.admin.username},{self.admin.email},Hacked\n"
        response = self.client.post(self.import_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)
        self.assertNotEqual(self.admin.first_name, "Hacked")

    def test_import_preview_does_not_save_anything(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        before = User.objects.count()
        csv_content = "username,email,first_name\npreviewonly,preview@x.com,Preview\n"
        response = self.client.post(self.preview_url, {"file": _csv_file(csv_content)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"total": 1, "valid": 1, "invalid": 0, "errors": []})
        self.assertEqual(User.objects.count(), before)

    def test_unsupported_file_extension_is_rejected(self):
        self._login(self.admin.username, "Str0ng!Pass123")
        bad_file = SimpleUploadedFile("teachers.txt", b"whatever", content_type="text/plain")
        response = self.client.post(self.import_url, {"file": bad_file}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anon_cannot_export_or_import(self):
        anon = APIClient()
        response = anon.get(self.export_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TeacherAdminChangelistTests(TestCase):
    """The Teacher admin changelist has no admin-side Import/Export UI —
    those buttons were removed in favor of the Trainers REST API
    (TrainerViewSet.export/import/import_preview)."""

    def setUp(self):
        self.admin = make_admin()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)

    def test_changelist_has_no_import_export_buttons(self):
        response = self.admin_web.get(reverse("admin:users_teacher_changelist"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("Import", content)
        self.assertNotIn("Export CSV", content)
        self.assertNotIn("Export XLSX", content)

    def test_import_and_export_admin_urls_no_longer_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("admin:users_teacher_import")
        with self.assertRaises(NoReverseMatch):
            reverse("admin:users_teacher_export")

    def test_changelist_still_has_add_button(self):
        response = self.admin_web.get(reverse("admin:users_teacher_changelist"))
        self.assertContains(response, reverse("admin:users_teacher_add"))


# ---------------------------------------------------------------------------
# Management command production guards (reset_dev_db, init_production)
# ---------------------------------------------------------------------------

class SubjectViewSetPermissionTests(APITestCase):
    """`SubjectViewSet.get_permissions()` must require authentication
    explicitly for anonymous requests, not fall through to the project-wide
    DRF default — this is exactly the view the audit found depending on
    that default before `DEFAULT_PERMISSION_CLASSES` was set."""

    def test_anonymous_request_is_rejected(self):
        response = self.client.get(reverse("subject-list"))
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_authenticated_teacher_can_list_active_subjects(self):
        teacher, password = make_teacher(username="subject_teacher", email="subject_teacher@okurmenkids.local")
        self.client.force_authenticate(teacher.user)
        response = self.client.get(reverse("subject-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ResetDevDbGuardTests(TestCase):
    """`reset_dev_db` must never run against production, and must never run
    without an explicit --confirm even outside production — regardless of
    what a caller passes on the command line."""

    def test_refuses_when_django_env_is_production_even_with_confirm(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "production"}):
            with self.assertRaises(CommandError) as ctx:
                call_command("reset_dev_db", "--confirm")
        self.assertIn("production", str(ctx.exception).lower())

    def test_refuses_without_confirm_flag_in_development(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            with self.assertRaises(CommandError) as ctx:
                call_command("reset_dev_db")
        self.assertIn("--confirm", str(ctx.exception))

    def test_proceeds_past_guards_in_development_with_confirm(self):
        # Verifies the guard lets a correctly-confirmed dev run through to
        # the actual reset logic, without exercising real file/DB deletion
        # (that's exercised manually — see the reset/seed documentation).
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            with mock.patch(
                "apps.users.management.commands.reset_dev_db.call_command"
            ) as mocked_call_command:
                call_command("reset_dev_db", "--confirm")
        mocked_call_command.assert_any_call("migrate", interactive=False)


class InitProductionGuardTests(TestCase):
    """`init_production` is a production-only bootstrap: it must refuse to
    run under any other DJANGO_ENV, and must never create a user or print a
    password."""

    def test_refuses_outside_production(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            with self.assertRaises(CommandError) as ctx:
                call_command("init_production")
        self.assertIn("production", str(ctx.exception).lower())

    def test_runs_migrate_and_never_creates_a_user_when_env_is_production(self):
        before = User.objects.count()
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "production"}):
            with mock.patch(
                "apps.users.management.commands.init_production.call_command"
            ) as mocked_call_command:
                out = self._call_and_capture()
        mocked_call_command.assert_any_call("migrate", interactive=False)
        self.assertEqual(User.objects.count(), before)
        self.assertNotIn("password", out.lower())

    def _call_and_capture(self) -> str:
        from io import StringIO

        buffer = StringIO()
        call_command("init_production", stdout=buffer)
        return buffer.getvalue()


# ---------------------------------------------------------------------------
# Media serving (Teacher.image) — config/urls.py + SERVE_MEDIA
# ---------------------------------------------------------------------------

def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (40, 160, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def _reload_urlconf():
    # config/urls.py decides at import time whether a media route exists, so
    # it has to be re-imported for DEBUG/SERVE_MEDIA overrides to apply.
    import config.urls

    clear_url_caches()
    importlib.reload(config.urls)


class MediaServingTests(TestCase):
    """Uploaded files (Teacher.image) must be reachable under MEDIA_URL in
    development (DEBUG=True) and in production (DEBUG=False + SERVE_MEDIA),
    and never leak anything outside MEDIA_ROOT."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.media_root = self.tmp_dir / "media"
        (self.media_root / "teachers").mkdir(parents=True)
        self.png = _png_bytes()
        (self.media_root / "teachers" / "probe.png").write_bytes(self.png)
        # Sits next to MEDIA_ROOT, never inside it — must stay unreachable.
        (self.tmp_dir / "secret.txt").write_text("TOP-SECRET")

    def _get(self, url, **overrides):
        try:
            with override_settings(MEDIA_ROOT=self.media_root, **overrides):
                _reload_urlconf()
                return self.client.get(url)
        finally:
            _reload_urlconf()

    def test_debug_true_serves_media(self):
        response = self._get("/media/teachers/probe.png", DEBUG=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(b"".join(response.streaming_content), self.png)

    def test_production_with_serve_media_serves_media(self):
        response = self._get("/media/teachers/probe.png", DEBUG=False, SERVE_MEDIA=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(b"".join(response.streaming_content), self.png)

    def test_production_without_serve_media_does_not_serve_media(self):
        response = self._get("/media/teachers/probe.png", DEBUG=False, SERVE_MEDIA=False)
        self.assertEqual(response.status_code, 404)

    def test_missing_file_returns_404(self):
        response = self._get("/media/teachers/missing.png", DEBUG=False, SERVE_MEDIA=True)
        self.assertEqual(response.status_code, 404)

    def test_directory_listing_is_not_served(self):
        response = self._get("/media/teachers/", DEBUG=False, SERVE_MEDIA=True)
        self.assertEqual(response.status_code, 404)

    def test_path_traversal_outside_media_root_is_blocked(self):
        for url in (
            "/media/../secret.txt",
            "/media/%2e%2e/secret.txt",
            "/media/teachers/..%2f..%2fsecret.txt",
            "/media/%2Fetc%2Fpasswd",
            "/media//etc/passwd",
        ):
            with self.subTest(url=url):
                response = self._get(url, DEBUG=False, SERVE_MEDIA=True)
                self.assertIn(response.status_code, (400, 404))
                body = b"".join(response.streaming_content) if response.streaming else response.content
                self.assertNotIn(b"TOP-SECRET", body)
                self.assertNotIn(b"root:", body)

    def test_existing_routes_still_resolve_with_media_route_enabled(self):
        admin = make_admin(username="media_admin", email="media_admin@okurmenkids.local")
        self.client.force_login(admin)
        try:
            with override_settings(MEDIA_ROOT=self.media_root, DEBUG=False, SERVE_MEDIA=True):
                _reload_urlconf()
                self.assertEqual(self.client.get(reverse("users-health")).status_code, 200)
                self.assertEqual(self.client.get(reverse("admin:users_teacher_changelist")).status_code, 200)
                self.assertEqual(self.client.get(reverse("schema")).status_code, 200)
                self.assertEqual(reverse("trainer-list"), "/api/v1/trainers/")
                self.assertEqual(reverse("auth-login"), "/api/v1/auth/login/")
        finally:
            _reload_urlconf()


class TeacherImageUploadTests(TestCase):
    """End-to-end: an image uploaded through the Teacher admin change form is
    stored under MEDIA_ROOT/teachers/, and is then served, shown in the admin
    and the API, and embedded in the monthly report PDF."""

    def setUp(self):
        self.media_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        overrides = override_settings(MEDIA_ROOT=self.media_root, DEBUG=False, SERVE_MEDIA=True)
        overrides.enable()
        self.addCleanup(_reload_urlconf)
        self.addCleanup(overrides.disable)
        _reload_urlconf()

        self.admin = make_admin(username="upload_admin", email="upload_admin@okurmenkids.local")
        self.teacher, _ = make_teacher(username="photo_teacher", email="photo_teacher@okurmenkids.local")
        self.png = _png_bytes()

    def _upload_via_admin(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:users_teacher_change", args=[self.teacher.pk]),
            {
                "user": self.teacher.user.pk,
                "phone": "",
                "position": "Тренер",
                "experience_years": 1,
                "hire_date": "",
                "subjects": [],
                "is_active": "on",
                "bio": "",
                "image": SimpleUploadedFile("avatar.png", self.png, content_type="image/png"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.teacher.refresh_from_db()

    def test_admin_upload_is_stored_under_media_root_and_served(self):
        self._upload_via_admin()

        self.assertTrue(self.teacher.image.name.startswith("teachers/"))
        stored = self.media_root / self.teacher.image.name
        self.assertTrue(stored.is_file())
        self.assertEqual(Path(self.teacher.image.path), stored)
        self.assertEqual(self.teacher.image.url, f"/media/{self.teacher.image.name}")

        response = self.client.get(self.teacher.image.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), self.png)

    def test_uploaded_image_is_shown_in_admin_and_api(self):
        self._upload_via_admin()
        url = self.teacher.image.url

        changelist = self.client.get(reverse("admin:users_teacher_changelist"))
        self.assertContains(changelist, f'src="{url}"')
        change = self.client.get(reverse("admin:users_teacher_change", args=[self.teacher.pk]))
        self.assertContains(change, f'src="{url}"')

        api = APIClient()
        api.force_authenticate(self.teacher.user)
        me = api.get(reverse("trainer-me"))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["image"], f"http://testserver{url}")

    def test_monthly_report_pdf_embeds_uploaded_image(self):
        from apps.academy.models import MonthlyTeacherReport
        from apps.academy.services.monthly_report_pdf import build_monthly_report_pdf

        report = MonthlyTeacherReport.objects.create(teacher=self.teacher, year=2026, month=9)
        without_image = build_monthly_report_pdf(report)
        self.assertNotIn(b"/Subtype /Image", without_image)

        self._upload_via_admin()
        report.refresh_from_db()
        with_image = build_monthly_report_pdf(report)
        self.assertTrue(with_image.startswith(b"%PDF"))
        self.assertIn(b"/Subtype /Image", with_image)


class TeacherImageAbsoluteUrlTests(APITestCase):
    """Every API response carrying a Teacher returns `image` as an absolute
    URL on the API's own host — the SPA runs on a different origin (Vercel),
    so a root-relative `/media/...` would be fetched from the wrong host."""

    def setUp(self):
        self.media_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        overrides = override_settings(MEDIA_ROOT=self.media_root)
        overrides.enable()
        self.addCleanup(overrides.disable)

        self.admin = make_admin(username="abs_admin", email="abs_admin@okurmenkids.local")
        self.teacher, _ = make_teacher(username="abs_teacher", email="abs_teacher@okurmenkids.local")
        self.teacher.image = SimpleUploadedFile("avatar.png", _png_bytes(), content_type="image/png")
        self.teacher.save()
        self.expected = f"http://testserver{self.teacher.image.url}"

    def test_me_returns_absolute_image_url(self):
        self.client.force_authenticate(self.teacher.user)
        response = self.client.get(reverse("trainer-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["image"], self.expected)

    @override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_me_uses_https_behind_the_railway_proxy(self):
        self.client.force_authenticate(self.teacher.user)
        # Real requests always carry Host; without it the test client adds :80.
        response = self.client.get(
            reverse("trainer-me"), HTTP_HOST="testserver", HTTP_X_FORWARDED_PROTO="https"
        )
        self.assertEqual(response.data["image"], f"https://testserver{self.teacher.image.url}")

    def test_me_returns_null_without_image(self):
        teacher, _ = make_teacher(username="no_photo", email="no_photo@okurmenkids.local")
        self.client.force_authenticate(teacher.user)
        response = self.client.get(reverse("trainer-me"))
        self.assertIsNone(response.data["image"])

    def test_verify_returns_absolute_image_url(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(reverse("trainer-verify", args=[self.teacher.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["image"], self.expected)

    def test_create_returns_absolute_image_url(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("trainer-list"),
            {
                "username": "created_with_photo",
                "email": "created_with_photo@okurmenkids.local",
                "first_name": "Айгерим",
                "password": "Python2026!",
                "password_confirm": "Python2026!",
                "image": SimpleUploadedFile("new.png", _png_bytes(), content_type="image/png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Teacher.objects.get(user__username="created_with_photo")
        self.assertEqual(response.data["image"], f"http://testserver{created.image.url}")

    def test_retrieve_and_list_match_the_same_absolute_url(self):
        self.client.force_authenticate(self.admin)
        detail = self.client.get(reverse("trainer-detail", args=[self.teacher.pk]))
        self.assertEqual(detail.data["image"], self.expected)
        listing = self.client.get(reverse("trainer-list"))
        row = next(r for r in listing.data["results"] if r["id"] == self.teacher.pk)
        self.assertEqual(row["image"], self.expected)

    def test_teacher_availability_returns_absolute_image_url(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            reverse("teacher-availability"),
            {"date": "2026-09-14", "start_time": "10:00", "end_time": "11:00"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(r for r in response.data["available"] if r["id"] == self.teacher.pk)
        self.assertEqual(row["image"], self.expected)


class ProductionMediaSettingsTests(TestCase):
    """production.py reads MEDIA_ROOT / SERVE_MEDIA from the environment,
    defaulting to the Railway Volume mount path and to serving media."""

    BASE_ENV = {
        "ALLOWED_HOST": "example.up.railway.app",
        "EMAIL_HOST_USER": "noreply@okurmenkids.local",
        "EMAIL_HOST_PASSWORD": "x",
    }

    def _load(self, **env):
        name = "config.settings.production"
        with mock.patch.dict("os.environ", {**self.BASE_ENV, **env}):
            sys.modules.pop(name, None)
            try:
                return importlib.import_module(name)
            finally:
                sys.modules.pop(name, None)

    def test_defaults_point_at_railway_volume(self):
        with mock.patch.dict("os.environ", {}, clear=False) as environ:
            environ.pop("MEDIA_ROOT", None)
            environ.pop("SERVE_MEDIA", None)
            production = self._load()
        self.assertEqual(production.MEDIA_ROOT, Path("/app/media"))
        self.assertIs(production.SERVE_MEDIA, True)
        self.assertIs(production.DEBUG, False)
        self.assertEqual(production.MEDIA_URL, "/media/")

    def test_env_overrides(self):
        production = self._load(MEDIA_ROOT="/data/uploads", SERVE_MEDIA="False")
        self.assertEqual(production.MEDIA_ROOT, Path("/data/uploads"))
        self.assertIs(production.SERVE_MEDIA, False)

    def test_base_settings_do_not_serve_media(self):
        from config.settings import base

        self.assertIs(base.SERVE_MEDIA, False)
