"""Student & Parent Portal: provisioning, credentials handling, isolation,
ownership and the data the family sees.

Isolation tests sign in through the real login endpoint and send the JWT —
the isolation middleware works on the token, which `force_authenticate`
would skip."""
from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance,
    Course,
    Group,
    GroupTeacher,
    Homework,
    HomeworkResult,
    Lesson,
    Student,
)
from apps.users.models import Subject, Teacher, User
from apps.website.models import Branch

from .models import PortalAccount, StudentLink
from .services import accounts

PASSWORD = "Str0ngPassw0rd!"
NEW_PASSWORD = "MyOwn-Secret-2026"
TODAY = timezone.localdate()


class PortalTestBase(TestCase):
    def setUp(self):
        self.assistant = User.objects.create_user(
            username="assist", email="assist@okurmen.kg", password=PASSWORD, first_name="Asel",
            role=User.Role.ASSISTANT,
        )
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Prog", count_lesson=12)
        self.course.subjects.set([self.python])
        teacher_user = User.objects.create_user(
            username="islam", email="islam@okurmen.kg", password=PASSWORD, first_name="Islam",
            role=User.Role.TEACHER, is_verified=True,
        )
        self.teacher = Teacher.objects.create(user=teacher_user)
        self.branch = Branch.objects.create(name="Центр", address="Чуй 1")
        self.g1 = Group.objects.create(name="PRO-01", course=self.course, start_date=TODAY - dt.timedelta(days=90))
        self.g2 = Group.objects.create(name="PRO-02", course=self.course, start_date=TODAY - dt.timedelta(days=90))
        self.gt1 = GroupTeacher.objects.create(group=self.g1, teacher=self.teacher, subject=self.python)
        self.gt2 = GroupTeacher.objects.create(group=self.g2, teacher=self.teacher, subject=self.python)
        self.staff = APIClient()
        self.staff.force_authenticate(self.assistant)

    # -- helpers ---------------------------------------------------------
    def create_student(self, first="Айбек", last="Асанов", group=None, **extra):
        payload = {"first_name": first, "last_name": last, "parent_phone": "+996 555 123 456",
                   "group": (group or self.g1).pk, "branch": self.branch.pk, **extra}
        response = self.staff.post(reverse("assistant:students"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response

    def login(self, username, password):
        client = APIClient()
        response = client.post(reverse("auth-login"), {"username": username, "password": password}, format="json")
        if response.status_code == 200:
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client, response

    def portal_client(self, first="Айбек", last="Асанов", group=None):
        response = self.create_student(first, last, group)
        creds = response.data["credentials"]
        client, _ = self.login(creds["login"], creds["password"])
        client.post(reverse("portal:password"), {
            "current_password": creds["password"], "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        }, format="json")
        return client, Student.objects.get(pk=response.data["id"]), creds["login"]

    def lesson(self, group, gt, date, number=1, status_=Lesson.Status.COMPLETED):
        return Lesson.objects.create(group=group, group_teacher=gt, subject=self.python, teacher=self.teacher,
                                     lesson_number=number, date=date, start_time=dt.time(16), end_time=dt.time(17, 30),
                                     status=status_)


class ProvisioningTests(PortalTestBase):
    def test_create_student_provisions_account_and_returns_credentials_once(self):
        response = self.create_student()
        self.assertEqual(response["Cache-Control"], "no-store, private")
        creds = response.data["credentials"]
        self.assertEqual(creds["login"], "aibek.asanov")
        self.assertRegex(creds["password"], r"^[A-Za-z2-9]{4}-[A-Za-z2-9]{4}-[A-Za-z2-9]{4}$")

        user = User.objects.get(username="aibek.asanov")
        self.assertEqual(user.role, User.Role.STUDENT_PARENT)
        self.assertFalse(user.is_staff)
        self.assertNotEqual(user.password, creds["password"])  # hashed
        self.assertTrue(user.check_password(creds["password"]))
        account = user.portal_account
        self.assertTrue(account.must_change_password)
        self.assertEqual(account.parent_phone, "996555123456")
        self.assertEqual(list(account.students.all()), [Student.objects.get(pk=response.data["id"])])

        # Never again: not in the student card, not in the audit trail.
        detail = self.staff.get(reverse("assistant:student-detail", args=[response.data["id"]])).data
        self.assertNotIn("credentials", detail)
        self.assertNotIn(creds["password"], str(detail))
        self.assertEqual(detail["account"]["status"], "pending")
        for entry in LogEntry.objects.all():
            self.assertNotIn(creds["password"], entry.change_message)

    def test_logins_are_unique_and_readable(self):
        first = self.create_student().data["credentials"]["login"]
        second = self.create_student().data["credentials"]["login"]
        self.assertEqual((first, second), ("aibek.asanov", "aibek.asanov2"))
        self.assertEqual(accounts.transliterate("Үмүт Өмүрбекова"), "umut.omurbekova")

    def test_custom_login_is_validated(self):
        User.objects.create_user(username="taken", email="t@o.kg", password=PASSWORD)
        response = self.staff.post(reverse("assistant:students"), {
            "first_name": "A", "last_name": "B", "group": self.g1.pk, "login": "taken",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Student.objects.filter(first_name="A").exists())  # all-or-nothing

    def test_student_without_account(self):
        response = self.create_student(create_account=False)
        self.assertNotIn("credentials", response.data)
        self.assertIsNone(response.data["account"])

    def test_sibling_joins_the_family_account(self):
        first = self.create_student()
        account = PortalAccount.objects.get()
        check = self.staff.get(reverse("assistant:students-account-check"),
                               {"first_name": "Айжан", "last_name": "Асанова", "parent_phone": "0555123456"[1:]}).data
        self.assertEqual(check["suggested_login"], "aizhan.asanova")
        response = self.create_student("Айжан", "Асанова", link_account=account.pk)
        self.assertNotIn("credentials", response.data)
        self.assertEqual(account.students.count(), 2)
        self.assertEqual(response.data["account"]["login"], first.data["credentials"]["login"])

    def test_only_operations_staff_manage_accounts(self):
        student_id = self.create_student().data["id"]
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        for name in ("student-account-reset", "student-account-unlink"):
            self.assertEqual(client.post(reverse(f"assistant:{name}", args=[student_id])).status_code, 403)
        self.assertEqual(client.post(reverse("assistant:students"), {}).status_code, 403)

    def test_reset_password_is_audited_and_requires_change_again(self):
        response = self.create_student()
        student_id, old = response.data["id"], response.data["credentials"]
        client, _, login = self.portal_client("Бакыт", "Алиев")
        reset = self.staff.post(reverse("assistant:student-account-reset", args=[student_id]))
        self.assertEqual(reset.status_code, 200)
        new = reset.data["credentials"]
        self.assertNotEqual(new["password"], old["password"])
        self.assertEqual(self.login(old["login"], old["password"])[1].status_code, 400)
        self.assertEqual(self.login(new["login"], new["password"])[1].status_code, 200)
        self.assertTrue(PortalAccount.objects.get(user__username=old["login"]).must_change_password)
        self.assertTrue(LogEntry.objects.filter(user=self.assistant, change_message__contains="пароль").exists())

    def test_change_login_checks_uniqueness(self):
        a = self.create_student().data["id"]
        self.create_student("Бакыт", "Алиев")
        url = reverse("assistant:student-account-login", args=[a])
        self.assertEqual(self.staff.patch(url, {"login": "bakyt.aliev"}, format="json").status_code, 400)
        self.assertEqual(self.staff.patch(url, {"login": "Bad Login!"}, format="json").status_code, 400)
        response = self.staff.patch(url, {"login": "aibek.a"}, format="json")
        self.assertEqual(response.data["account"]["login"], "aibek.a")

    def test_deactivated_account_cannot_sign_in(self):
        response = self.create_student()
        creds = response.data["credentials"]
        self.staff.post(reverse("assistant:student-account-active", args=[response.data["id"]]), {"value": False},
                        format="json")
        self.assertEqual(self.login(creds["login"], creds["password"])[1].status_code, 400)

    def test_export_has_logins_but_no_passwords(self):
        creds = self.create_student().data["credentials"]
        response = self.staff.get(reverse("assistant:students-export"), {"export_format": "csv"})
        body = response.content.decode("utf-8-sig")
        self.assertIn(creds["login"], body)
        self.assertNotIn(creds["password"], body)

    def test_filters_by_branch_and_account(self):
        self.create_student()
        Student.objects.create(first_name="No", last_name="Account", group=self.g1)
        rows = self.staff.get(reverse("assistant:students"), {"account": "none"}).data["results"]
        self.assertEqual([r["last_name"] for r in rows], ["Account"])
        rows = self.staff.get(reverse("assistant:students"), {"branch": self.branch.pk}).data["results"]
        self.assertEqual([r["last_name"] for r in rows], ["Асанов"])


class FirstLoginAndIsolationTests(PortalTestBase):
    def test_first_login_requires_password_change(self):
        response = self.create_student()
        creds, student_id = response.data["credentials"], response.data["id"]
        client, login = self.login(creds["login"], creds["password"])
        self.assertTrue(login.data["user"]["must_change_password"])
        self.assertEqual(login.data["user"]["email"], "")
        blocked = client.get(reverse("portal:dashboard", args=[student_id]))
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["code"], "password_change_required")
        self.assertEqual(client.get(reverse("portal:me")).status_code, 200)

        weak = client.post(reverse("portal:password"), {"current_password": creds["password"], "new_password": "123",
                                                        "new_password_confirm": "123"}, format="json")
        self.assertEqual(weak.status_code, 400)
        ok = client.post(reverse("portal:password"), {"current_password": creds["password"],
                                                      "new_password": NEW_PASSWORD,
                                                      "new_password_confirm": NEW_PASSWORD}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(client.get(reverse("portal:dashboard", args=[student_id])).status_code, 200)
        self.assertFalse(client.get(reverse("auth-me")).data["must_change_password"])

    def test_portal_account_is_shut_out_of_staff_apis(self):
        client, _, _ = self.portal_client()
        for path in ("/api/v1/assistant/students/", "/api/v1/groups/", "/api/v1/trainers/", "/api/v1/students/",
                     "/api/v1/accounting/my/", "/api/v1/tasks/", "/api/v1/hr/employees/"):
            response = client.get(path)
            self.assertEqual(response.status_code, 403, path)
            self.assertEqual(response.json()["code"], "portal_only", path)

    def test_staff_cannot_use_portal_api(self):
        self.assertEqual(self.staff.get(reverse("portal:me")).status_code, 403)

    def test_portal_accounts_are_not_employees(self):
        self.create_student()
        self.assertFalse(User.objects.staff().filter(role=User.Role.STUDENT_PARENT).exists())
        self.assertTrue(User.objects.staff().filter(pk=self.assistant.pk).exists())
        self.assertNotIn(User.Role.STUDENT_PARENT, User.staff_role_values())


class OwnershipTests(PortalTestBase):
    def test_family_sees_only_its_own_children(self):
        client, own, _ = self.portal_client()
        other = Student.objects.create(first_name="Other", last_name="Kid", group=self.g1)
        homework = Homework.objects.create(lesson=self.lesson(self.g1, self.gt1, TODAY), title="HW")
        HomeworkResult.objects.create(homework=homework, student=other, comment="secret")
        for name, args in (("dashboard", [other.pk]), ("schedule", [other.pk]), ("homework", [other.pk]),
                           ("attendance", [other.pk]), ("monthly-report", [other.pk]), ("payments", [other.pk]),
                           ("homework-detail", [other.pk, homework.pk])):
            self.assertEqual(client.get(reverse(f"portal:{name}", args=args)).status_code, 404, name)
        me = client.get(reverse("portal:me")).data
        self.assertEqual([s["id"] for s in me["students"]], [own.pk])

    def test_parent_with_two_children_switches_between_them(self):
        client, first, _ = self.portal_client()
        account = PortalAccount.objects.get()
        sibling = self.create_student("Айжан", "Асанова", group=self.g2, link_account=account.pk).data["id"]
        me = client.get(reverse("portal:me")).data
        self.assertEqual({s["id"] for s in me["students"]}, {first.pk, sibling})
        for student_id in (first.pk, sibling):
            self.assertEqual(client.get(reverse("portal:dashboard", args=[student_id])).status_code, 200)

    def test_unlinked_child_disappears(self):
        client, first, _ = self.portal_client()
        account = PortalAccount.objects.get()
        sibling = self.create_student("Айжан", "Асанова", link_account=account.pk).data["id"]
        self.staff.post(reverse("assistant:student-account-unlink", args=[sibling]))
        self.assertEqual(client.get(reverse("portal:dashboard", args=[sibling])).status_code, 404)
        # The last child cannot be unlinked.
        self.assertEqual(self.staff.post(reverse("assistant:student-account-unlink", args=[first.pk])).status_code, 400)

    def test_lessons_before_joining_the_group_are_not_shown(self):
        client, student, _ = self.portal_client()
        Student.objects.filter(pk=student.pk).update(enrollment_date=TODAY - dt.timedelta(days=3))
        self.lesson(self.g1, self.gt1, TODAY - dt.timedelta(days=5))
        mine = self.lesson(self.g1, self.gt1, TODAY - dt.timedelta(days=1), number=2)
        data = client.get(reverse("portal:schedule", args=[student.pk]), {
            "start": (TODAY - dt.timedelta(days=7)).isoformat(), "end": TODAY.isoformat()}).data
        self.assertEqual([l["id"] for l in data["lessons"]], [mine.pk])


class DataTests(PortalTestBase):
    def setUp(self):
        super().setUp()
        self.client_, self.student, _ = self.portal_client()
        Student.objects.filter(pk=self.student.pk).update(enrollment_date=TODAY - dt.timedelta(days=60))
        self.month_start = TODAY.replace(day=1)

    def test_schedule_range_is_validated(self):
        url = reverse("portal:schedule", args=[self.student.pk])
        self.assertEqual(self.client_.get(url, {"start": "2026-01-01", "end": "2026-06-01"}).status_code, 400)
        self.assertEqual(self.client_.get(url, {"start": "nope"}).status_code, 400)

    def test_homework_is_read_only_and_awaits_the_trainer(self):
        lesson = self.lesson(self.g1, self.gt1, TODAY)
        lesson.youtube_url = "https://youtu.be/x"
        lesson.save()
        upcoming = Homework.objects.create(lesson=lesson, title="Upcoming", description="Решите 5 задач",
                                           deadline=TODAY + dt.timedelta(days=2))
        past = Homework.objects.create(lesson=lesson, title="Past", deadline=TODAY - dt.timedelta(days=1))
        url = reverse("portal:homework", args=[self.student.pk])
        rows = {r["title"]: r for r in self.client_.get(url).data["results"]}
        # Nothing recorded by the trainer yet → «awaiting», never «overdue», never a grade.
        self.assertEqual({t: r["state"] for t, r in rows.items()}, {"Upcoming": "awaiting", "Past": "awaiting"})
        self.assertTrue(all(r["score"] is None for r in rows.values()))

        detail = self.client_.get(reverse("portal:homework-detail", args=[self.student.pk, upcoming.pk])).data
        self.assertEqual(detail["description"], "Решите 5 задач")
        self.assertEqual(detail["assigned_date"], TODAY)
        self.assertEqual(detail["attachments"], [{"kind": "video", "url": "https://youtu.be/x"}])
        self.assertEqual((detail["score"], detail["feedback"]), (None, ""))
        for gone in ("submission", "can_submit"):
            self.assertNotIn(gone, detail)

        # No way to hand work in or change a result from the portal.
        detail_url = reverse("portal:homework-detail", args=[self.student.pk, upcoming.pk])
        self.assertEqual(self.client_.post(detail_url, {"text": "x"}, format="json").status_code, 405)
        self.assertEqual(self.client_.post(f"{detail_url}submit/", {"text": "x"}, format="json").status_code, 404)
        teacher_url = f"/api/v1/homework/{upcoming.pk}/results/"
        payload = [{"student": self.student.pk, "status": "checked", "score": 10, "comment": "self-graded"}]
        response = self.client_.post(teacher_url, payload, format="json")
        self.assertEqual((response.status_code, response.json()["code"]), (403, "portal_only"))
        self.assertFalse(HomeworkResult.objects.filter(homework=upcoming).exists())
        self.assertNotIn(past.pk, [n["params"].get("homework_id") for n in
                                   self.client_.get(reverse("portal:notifications", args=[self.student.pk])).data["results"]
                                   if n["kind"] != "homework_new"])

    def test_trainer_grading_form_is_reflected_immediately(self):
        lesson = self.lesson(self.g1, self.gt1, TODAY)
        hw = Homework.objects.create(lesson=lesson, title="Циклы", deadline=TODAY - dt.timedelta(days=1))
        other = Homework.objects.create(lesson=lesson, title="Списки", deadline=TODAY + dt.timedelta(days=3))
        teacher = APIClient()
        teacher.force_authenticate(self.teacher.user)
        results_url = f"/api/v1/homework/{hw.pk}/results/"
        detail_url = reverse("portal:homework-detail", args=[self.student.pk, hw.pk])

        # The trainer's existing form: each status, with an optional grade and comment.
        steps = [
            ({"status": "not_submitted", "score": None, "comment": ""}, ("not_submitted", None, "")),
            ({"status": "late", "score": None, "comment": "Принёс на следующий урок"},
             ("late", None, "Принёс на следующий урок")),
            ({"status": "submitted", "score": 7, "comment": ""}, ("submitted", 7, "")),
            ({"status": "checked", "score": 10, "comment": "Отлично!"}, ("checked", 10, "Отлично!")),
        ]
        for entry, expected in steps:
            saved = teacher.post(results_url, [{"student": self.student.pk, **entry}], format="json")
            self.assertEqual(saved.status_code, 200, saved.data)
            seen = self.client_.get(detail_url).data
            self.assertEqual((seen["state"], seen["score"], seen["feedback"]), expected)

        # The trainer reads the same form back unchanged; one row per student, history kept.
        rows = teacher.get(results_url).data
        mine = next(r for r in rows if r["student"] == self.student.pk)
        self.assertEqual((mine["status"], mine["score"], mine["comment"]), ("checked", 10, "Отлично!"))
        self.assertNotIn("submission_text", mine)
        self.assertEqual(HomeworkResult.objects.filter(homework=hw, student=self.student).count(), 1)

        dashboard = self.client_.get(reverse("portal:dashboard", args=[self.student.pk])).data
        self.assertEqual(dashboard["performance"]["homework_rate"], 100.0)  # only evaluated work counts
        self.assertEqual([h["title"] for h in dashboard["homework"]["open"]], ["Списки"])
        kinds = {n["kind"] for n in dashboard["notifications"]}
        self.assertIn("homework_checked", kinds)

        teacher.post(f"/api/v1/homework/{other.pk}/results/",
                     [{"student": self.student.pk, "status": "not_submitted", "score": None, "comment": ""}], format="json")
        dashboard = self.client_.get(reverse("portal:dashboard", args=[self.student.pk])).data
        self.assertEqual(dashboard["homework"]["not_submitted_count"], 1)
        self.assertIn("homework_not_submitted", {n["kind"] for n in dashboard["notifications"]})

    def test_assistant_still_reads_homework_results(self):
        lesson = self.lesson(self.g1, self.gt1, TODAY)
        hw = Homework.objects.create(lesson=lesson, title="HW")
        HomeworkResult.objects.create(homework=hw, student=self.student, status="checked", score=9, comment="ok")
        detail = self.staff.get(reverse("assistant:student-detail", args=[self.student.pk])).data
        self.assertEqual([(h["status"], h["score"]) for h in detail["homework"]], [("checked", 9)])

    def test_monthly_report_uses_real_records(self):
        days = [self.month_start + dt.timedelta(days=i) for i in range(3)]
        days = [d for d in days if d <= TODAY] or [TODAY]
        statuses = [Attendance.Status.PRESENT, Attendance.Status.ABSENT, Attendance.Status.LATE][:len(days)]
        for number, (day, mark) in enumerate(zip(days, statuses), start=1):
            lesson = self.lesson(self.g1, self.gt1, day, number=number)
            Attendance.objects.create(student=self.student, lesson=lesson, status=mark)
            homework = Homework.objects.create(lesson=lesson, title=f"HW{number}")
            if number == 1:
                HomeworkResult.objects.create(homework=homework, student=self.student,
                                              status=HomeworkResult.Status.CHECKED, score=8, comment="Хорошо")
        report = self.client_.get(reverse("portal:monthly-report", args=[self.student.pk]),
                                  {"year": TODAY.year, "month": TODAY.month}).data
        attended = sum(1 for s in statuses if s != Attendance.Status.ABSENT)
        self.assertEqual(report["attendance"]["total_lessons"], len(days))
        self.assertEqual(report["attendance"]["attended"], attended)
        self.assertEqual(report["attendance"]["missed"], len(days) - attended)
        self.assertEqual(report["homework"]["assigned"], len(days))
        self.assertEqual(report["homework"]["completed"], 1)
        self.assertEqual(report["homework"]["average_score"], 8.0)
        xp_expected = 10 + (5 if len(days) == 3 else 0) + 10 + 8
        self.assertEqual(report["xp"]["total"], xp_expected)
        self.assertEqual(len(report["trend"]), 6)
        self.assertEqual(report["comments"][0]["text"], "Хорошо")

        for lang in ("ru", "ky"):
            pdf = self.client_.get(reverse("portal:monthly-report-pdf", args=[self.student.pk]),
                                   {"year": TODAY.year, "month": TODAY.month, "lang": lang})
            self.assertEqual(pdf.status_code, 200)
            self.assertEqual(pdf["Content-Type"], "application/pdf")
            self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_future_month_is_refused(self):
        nxt = (TODAY.replace(day=28) + dt.timedelta(days=5))
        response = self.client_.get(reverse("portal:monthly-report", args=[self.student.pk]),
                                    {"year": nxt.year, "month": nxt.month})
        self.assertEqual(response.status_code, 400)

    def test_dashboard_and_notifications(self):
        lesson = self.lesson(self.g1, self.gt1, TODAY, status_=Lesson.Status.SCHEDULED)
        self.lesson(self.g1, self.gt1, TODAY + dt.timedelta(days=2), number=2, status_=Lesson.Status.CANCELLED)
        Homework.objects.create(lesson=lesson, title="Due", deadline=TODAY + dt.timedelta(days=1))
        Homework.objects.create(lesson=lesson, title="Old", deadline=TODAY - dt.timedelta(days=5))
        data = self.client_.get(reverse("portal:dashboard", args=[self.student.pk])).data
        self.assertEqual([l["id"] for l in data["today_lessons"]], [lesson.pk])
        self.assertEqual(data["homework"]["open_count"], 1)
        kinds = {n["kind"] for n in data["notifications"]}
        self.assertIn("homework_due", kinds)
        self.assertIn("lesson_cancelled", kinds)
        self.assertIsNone(data["payments"])  # no billing contract

    def test_payments_can_be_hidden(self):
        self.staff.post(reverse("assistant:student-account-payments", args=[self.student.pk]), {"value": False},
                        format="json")
        self.assertEqual(self.client_.get(reverse("portal:payments", args=[self.student.pk])).status_code, 403)
        self.assertIsNone(self.client_.get(reverse("portal:dashboard", args=[self.student.pk])).data["payments"])
        self.assertEqual(StudentLink.objects.count(), 1)
