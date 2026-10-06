"""Group and Student can be deleted through Django admin by a superuser only.

Staff/Admin-role accounts keep view / add / change (their Django model
permissions), but get no Delete button, no delete page (403 — also for a
hand-made POST) and no «delete_selected» bulk action — even when they hold
the Django «delete» permission. Absolute imports only — see the note at the
top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.academy.models import Course, Group, Student
from apps.users.models import User

PASSWORD = "Str0ngPassw0rd!"


class AdminDeleteIsSuperuserOnlyTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="Prog", count_lesson=10)
        self.group = Group.objects.create(name="PRO-01", course=self.course, start_date=dt.date(2026, 9, 1))
        self.student = Student.objects.create(first_name="Islam", last_name="D", group=self.group)

        self.superuser = User.objects.create_superuser(username="root", email="root@o.kg", password=PASSWORD)
        # A staff Admin-role account holding every Django permission on both
        # models, delete included: delete must still be refused.
        self.staff = User.objects.create_user(
            username="staff", email="staff@o.kg", password=PASSWORD, role=User.Role.ADMIN, is_staff=True,
        )
        self.staff.user_permissions.set(Permission.objects.filter(
            content_type__app_label="academy", content_type__model__in=["group", "student"],
        ))
        self.teacher = User.objects.create_user(
            username="trainer", email="t@o.kg", password=PASSWORD, role=User.Role.TEACHER, is_verified=True,
        )
        self.assistant = User.objects.create_user(
            username="assist", email="a@o.kg", password=PASSWORD, role=User.Role.ASSISTANT,
        )
        self.factory = RequestFactory()

    def client_for(self, user) -> Client:
        client = Client()
        client.force_login(user)
        return client

    def request_for(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def objects(self):
        return ((Group, self.group, "group"), (Student, self.student, "student"))

    # -- has_delete_permission / actions ------------------------------------

    def test_only_superuser_has_delete_permission(self):
        for model, obj, _ in self.objects():
            model_admin = admin.site._registry[model]
            with self.subTest(model=model.__name__):
                self.assertTrue(model_admin.has_delete_permission(self.request_for(self.superuser), obj))
                for user in (self.staff, self.teacher, self.assistant):
                    self.assertFalse(model_admin.has_delete_permission(self.request_for(user), obj), user.username)

    def test_add_and_change_are_untouched_for_staff(self):
        for model, obj, _ in self.objects():
            model_admin = admin.site._registry[model]
            request = self.request_for(self.staff)
            with self.subTest(model=model.__name__):
                self.assertTrue(model_admin.has_add_permission(request))
                self.assertTrue(model_admin.has_change_permission(request, obj))
                self.assertTrue(model_admin.has_view_permission(request, obj))

    def test_delete_selected_only_for_superuser(self):
        for model, _, name in self.objects():
            url = reverse(f"admin:academy_{name}_changelist")
            with self.subTest(model=model.__name__):
                self.assertContains(self.client_for(self.superuser).get(url), "delete_selected")
                response = self.client_for(self.staff).get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "delete_selected")
                self.assertNotIn("delete_selected", admin.site._registry[model].get_actions(self.request_for(self.staff)))

    def test_change_form_delete_link_only_for_superuser(self):
        for model, obj, name in self.objects():
            url = reverse(f"admin:academy_{name}_change", args=[obj.pk])
            delete_url = reverse(f"admin:academy_{name}_delete", args=[obj.pk])
            with self.subTest(model=model.__name__):
                self.assertContains(self.client_for(self.superuser).get(url), delete_url)
                response = self.client_for(self.staff).get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, delete_url)

    # -- the server refuses, not just the UI --------------------------------

    def test_staff_delete_page_and_manual_post_are_forbidden(self):
        client = self.client_for(self.staff)
        for model, obj, name in self.objects():
            url = reverse(f"admin:academy_{name}_delete", args=[obj.pk])
            with self.subTest(model=model.__name__):
                self.assertEqual(client.get(url).status_code, 403)
                self.assertEqual(client.post(url, {"post": "yes"}).status_code, 403)
                self.assertTrue(model.objects.filter(pk=obj.pk).exists())

    def test_staff_manual_delete_selected_post_deletes_nothing(self):
        client = self.client_for(self.staff)
        for model, obj, name in self.objects():
            with self.subTest(model=model.__name__):
                client.post(reverse(f"admin:academy_{name}_changelist"), {
                    "action": "delete_selected", "_selected_action": [obj.pk], "post": "yes",
                })
                self.assertTrue(model.objects.filter(pk=obj.pk).exists())

    def test_delete_model_and_queryset_refuse_non_superuser_directly(self):
        for model, obj, _ in self.objects():
            model_admin = admin.site._registry[model]
            request = self.request_for(self.staff)
            with self.subTest(model=model.__name__):
                with self.assertRaises(PermissionDenied):
                    model_admin.delete_model(request, obj)
                with self.assertRaises(PermissionDenied):
                    model_admin.delete_queryset(request, model.objects.filter(pk=obj.pk))
                self.assertTrue(model.objects.filter(pk=obj.pk).exists())

    def test_trainer_and_assistant_have_no_admin_at_all(self):
        for user in (self.teacher, self.assistant):
            response = self.client_for(user).post(
                reverse("admin:academy_student_delete", args=[self.student.pk]), {"post": "yes"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertIn("/admin/login/", response["Location"])
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    # -- superuser --------------------------------------------------------------

    def test_superuser_deletes_student_and_group(self):
        client = self.client_for(self.superuser)
        response = client.post(reverse("admin:academy_student_delete", args=[self.student.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        response = client.post(reverse("admin:academy_group_delete", args=[self.group.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Group.objects.filter(pk=self.group.pk).exists())

    def test_superuser_bulk_delete_selected(self):
        other = Student.objects.create(first_name="Aida")
        self.client_for(self.superuser).post(reverse("admin:academy_student_changelist"), {
            "action": "delete_selected", "_selected_action": [self.student.pk, other.pk], "post": "yes",
        })
        self.assertFalse(Student.objects.filter(pk__in=[self.student.pk, other.pk]).exists())
