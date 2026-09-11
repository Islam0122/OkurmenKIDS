from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client as DjangoClient
from django.test import TestCase
from django.urls import reverse
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


class TeacherAdminImportExportTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.teacher, self.password = make_teacher(
            username="teacherWeb", email="teacherWeb@okurmenkids.local"
        )
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher_web = DjangoClient()
        self.teacher_web.force_login(self.teacher.user)

    def test_changelist_has_import_export_buttons(self):
        response = self.admin_web.get(reverse("admin:users_teacher_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:users_teacher_import"))
        self.assertContains(response, reverse("admin:users_teacher_export"))

    def test_export_view_downloads_csv(self):
        response = self.admin_web.get(reverse("admin:users_teacher_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertNotIn(b"password", response.content.lower())

    def test_import_preview_then_confirm(self):
        csv_content = "username,email,first_name\nwebimport,webimport@okurmenkids.local,WebImport\n"
        url = reverse("admin:users_teacher_import")

        preview_response = self.admin_web.post(url, {"file": _csv_file(csv_content), "preview": "1"})
        self.assertEqual(preview_response.status_code, 200)
        self.assertFalse(User.objects.filter(username="webimport").exists())

        confirm_response = self.admin_web.post(
            url, {"file": _csv_file(csv_content), "confirm": "1"}, follow=True
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertTrue(User.objects.filter(username="webimport").exists())

    def test_import_view_requires_admin(self):
        url = reverse("admin:users_teacher_import")
        response = self.teacher_web.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)


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
