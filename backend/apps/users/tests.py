from django.core import mail
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

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
        response = self.client.post("/api/v1/users/auth/change-password/", {})
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
        response = self.client.get("/api/v1/users/auth/verify-email/abc/def/")
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
