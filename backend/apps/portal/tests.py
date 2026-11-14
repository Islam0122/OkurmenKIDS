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
        self.assertEqual(dashboard["homework"]["open"], [])  # no next lesson scheduled
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
        self.assertEqual(data["homework"]["open_count"], 0)  # the only later lesson is cancelled
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


class NextLessonHomeworkTests(PortalTestBase):
    """/student/homework shows only the homework of the NEXT scheduled lesson;
    everything already given stays in the history."""

    def setUp(self):
        super().setUp()
        self.client_, self.student, _ = self.portal_client()
        Student.objects.filter(pk=self.student.pk).update(enrollment_date=TODAY - dt.timedelta(days=120))
        self.student.refresh_from_db()
        # Lessons 1–20, twice a week; lesson 17 is today.
        self.lessons, self.hw = {}, {}
        for number in range(1, 21):
            day = TODAY + dt.timedelta(days=(number - 17) * 3)
            status_ = Lesson.Status.COMPLETED if day < TODAY else Lesson.Status.SCHEDULED
            lesson = self.lesson(self.g1, self.gt1, day, number=number, status_=status_)
            self.lessons[number] = lesson
            self.hw[number] = Homework.objects.create(lesson=lesson, title=f"ДЗ к уроку {number}")

    def next_(self):
        response = self.client_.get(reverse("portal:homework-next", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        return response.data

    def titles(self, data):
        return [[hw["title"] for hw in block["homework"]] for block in data["lessons"]]

    def history(self, **params):
        rows = self.client_.get(reverse("portal:homework", args=[self.student.pk]), {"page_size": 100, **params}).data
        return [r["title"] for r in rows["results"]]

    def test_lesson_17_today_shows_homework_of_lesson_18_only(self):
        data = self.next_()
        self.assertEqual([b["lesson"]["lesson_number"] for b in data["lessons"]], [18])
        self.assertEqual(self.titles(data), [["ДЗ к уроку 18"]])
        block = data["lessons"][0]["homework"][0]
        self.assertEqual((block["lesson"]["lesson_number"], block["state"], block["score"]), (18, "awaiting", None))
        # History: lessons up to today (17 … 1), never 18+.
        history = self.history()
        self.assertEqual(history[0], "ДЗ к уроку 17")
        self.assertEqual(len(history), 17)
        self.assertNotIn("ДЗ к уроку 18", history)
        # Distant future homework is not reachable even by id.
        for number in (19, 20):
            url = reverse("portal:homework-detail", args=[self.student.pk, self.hw[number].pk])
            self.assertEqual(self.client_.get(url).status_code, 404)
        self.assertEqual(self.client_.get(reverse("portal:homework-detail", args=[self.student.pk, self.hw[18].pk])).status_code, 200)

    def test_next_lesson_moves_with_the_calendar(self):
        # A day later lesson 18 is still next (no lesson today) …
        self.assertEqual(self._next_numbers(TODAY + dt.timedelta(days=1)), [18])
        # … on the day of lesson 18 the next one is 19, then 20.
        self.assertEqual(self._next_numbers(self.lessons[18].date), [19])
        self.assertEqual(self._next_numbers(self.lessons[19].date), [20])
        self.assertEqual(self._next_numbers(self.lessons[20].date), [])

    def _next_numbers(self, today):
        from .services import data

        return [l.lesson_number for l in data.next_lessons(self.student, today)]

    def test_cancelled_lesson_is_skipped_and_its_makeup_carries_the_homework(self):
        lesson18 = self.lessons[18]
        Lesson.objects.filter(pk=lesson18.pk).update(status=Lesson.Status.CANCELLED)
        makeup = Lesson.objects.create(
            group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.teacher, lesson_number=18,
            date=lesson18.date + dt.timedelta(days=1), start_time=dt.time(16), end_time=dt.time(17, 30),
            rescheduled_from=lesson18,
        )
        Homework.objects.filter(pk=self.hw[18].pk).update(lesson=makeup)  # as services.lesson_reschedule does
        data = self.next_()
        self.assertEqual([b["lesson"]["id"] for b in data["lessons"]], [makeup.pk])
        self.assertEqual(self.titles(data), [["ДЗ к уроку 18"]])

    def test_a_moved_lesson_counts_on_its_new_date(self):
        Lesson.objects.filter(pk=self.lessons[18].pk).update(date=self.lessons[19].date + dt.timedelta(days=1))
        self.assertEqual([b["lesson"]["lesson_number"] for b in self.next_()["lessons"]], [19])

    def test_next_lesson_without_homework(self):
        self.hw[18].delete()
        data = self.next_()
        self.assertEqual([b["lesson"]["lesson_number"] for b in data["lessons"]], [18])
        self.assertEqual(self.titles(data), [[]])  # «Домашнее задание пока не назначено»

    def test_several_homeworks_for_the_next_lesson(self):
        Homework.objects.create(lesson=self.lessons[18], title="Ещё одно ДЗ к уроку 18")
        self.assertEqual(self.titles(self.next_()), [["ДЗ к уроку 18", "Ещё одно ДЗ к уроку 18"]])

    def test_no_next_lesson(self):
        Lesson.objects.filter(group=self.g1, date__gt=TODAY).update(status=Lesson.Status.CANCELLED)
        self.assertEqual(self.next_()["lessons"], [])
        Lesson.objects.filter(group=self.g1, date__gt=TODAY).update(status=Lesson.Status.SCHEDULED)
        Student.objects.filter(pk=self.student.pk).update(status=Student.Status.PAUSED, is_active=False)
        self.assertEqual(self.next_()["lessons"], [])

    def test_other_groups_homework_is_never_shown(self):
        other = self.lesson(self.g2, self.gt2, TODAY + dt.timedelta(days=1), number=18)
        foreign = Homework.objects.create(lesson=other, title="Чужое ДЗ")
        self.assertEqual(self.titles(self.next_()), [["ДЗ к уроку 18"]])
        self.assertNotIn("Чужое ДЗ", self.history())
        url = reverse("portal:homework-detail", args=[self.student.pk, foreign.pk])
        self.assertEqual(self.client_.get(url).status_code, 404)

    def test_each_program_of_the_group_has_its_own_next_lesson(self):
        english, _ = Subject.objects.get_or_create(name="English")
        gt_en = GroupTeacher.objects.create(group=self.g1, teacher=self.teacher, subject=english)
        en5 = Lesson.objects.create(group=self.g1, group_teacher=gt_en, subject=english, teacher=self.teacher,
                                    lesson_number=5, date=TODAY + dt.timedelta(days=2),
                                    start_time=dt.time(10), end_time=dt.time(11))
        Lesson.objects.create(group=self.g1, group_teacher=gt_en, subject=english, teacher=self.teacher,
                              lesson_number=6, date=TODAY + dt.timedelta(days=4),
                              start_time=dt.time(10), end_time=dt.time(11))
        Homework.objects.create(lesson=en5, title="English 5")
        self.assertEqual(self.titles(self.next_()), [["English 5"], ["ДЗ к уроку 18"]])

    def test_transferred_student_follows_the_new_group(self):
        from apps.academy.services.student_enrollment import transfer_student

        g2_next = self.lesson(self.g2, self.gt2, TODAY + dt.timedelta(days=2), number=9, status_=Lesson.Status.SCHEDULED)
        Homework.objects.create(lesson=g2_next, title="ДЗ группы 2")
        transfer_student(self.student, group=self.g2, event_date=TODAY)
        self.student.refresh_from_db()
        self.assertEqual(self.titles(self.next_()), [["ДЗ группы 2"]])
        # Homework of the old group's past lessons stays in the history.
        self.assertIn("ДЗ к уроку 16", self.history())

    def test_history_keeps_trainer_results(self):
        HomeworkResult.objects.create(homework=self.hw[16], student=self.student, status="checked", score=9,
                                      comment="Хорошо", checked_at=timezone.now())
        rows = self.client_.get(reverse("portal:homework", args=[self.student.pk]), {"state": "checked"}).data["results"]
        self.assertEqual([(r["title"], r["score"], r["state"]) for r in rows], [("ДЗ к уроку 16", 9, "checked")])
        self.assertIsNotNone(rows[0]["evaluated_at"])
        detail = self.client_.get(reverse("portal:homework-detail", args=[self.student.pk, self.hw[16].pk])).data
        self.assertEqual(detail["feedback"], "Хорошо")

    def test_teacher_api_is_unchanged(self):
        teacher = APIClient()
        teacher.force_authenticate(self.teacher.user)
        # The trainer still sees and grades homework of any lesson, future ones included.
        response = teacher.post(f"/api/v1/homework/{self.hw[20].pk}/results/",
                                [{"student": self.student.pk, "status": "checked", "score": 8, "comment": ""}], format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(teacher.get(f"/api/v1/homework/{self.hw[19].pk}/").status_code, 200)


class RedesignDataTests(PortalTestBase):
    """Read-only data behind the redesigned portal: course progress, the
    achievements page and the group on homework cards — all real records."""

    def setUp(self):
        super().setUp()
        self.client_, self.student, _ = self.portal_client()
        Student.objects.filter(pk=self.student.pk).update(enrollment_date=TODAY - dt.timedelta(days=60))

    def test_course_progress_counts_held_lessons_of_the_group(self):
        for number, delta in enumerate((-6, -3, 3, 6), start=1):
            status_ = Lesson.Status.COMPLETED if delta < 0 else Lesson.Status.SCHEDULED
            self.lesson(self.g1, self.gt1, TODAY + dt.timedelta(days=delta), number=number, status_=status_)
        self.lesson(self.g1, self.gt1, TODAY + dt.timedelta(days=9), number=9, status_=Lesson.Status.CANCELLED)
        progress = self.client_.get(reverse("portal:dashboard", args=[self.student.pk])).data["course_progress"]
        self.assertEqual((progress["lessons_done"], progress["lessons_total"], progress["percent"]), (2, 4, 50))
        self.assertEqual(progress["group"]["name"], "PRO-01")

    def test_achievements_page_uses_the_new_collection(self):
        lesson = self.lesson(self.g1, self.gt1, TODAY - dt.timedelta(days=1))
        for i in range(6):
            hw = Homework.objects.create(lesson=lesson, title=f"HW{i}")
            HomeworkResult.objects.create(homework=hw, student=self.student, status="checked", score=10 if i < 2 else 8)
        data = self.client_.get(reverse("portal:achievements", args=[self.student.pk])).data
        goals = {g["code"]: (g["current"], g["target"]) for g in data["goals"]}
        self.assertEqual(goals["homework_done"], (6, 20))
        self.assertEqual(goals["top_homework"], (2, 10))
        unlocked = {a["id"] for a in data["achievements"] if a["unlocked"]}
        self.assertTrue({"homework_done-5", "top_homework-1"} <= unlocked)
        self.assertEqual(data["xp"]["total"]["total"], 6 * 10 + 2 * 10 + 4 * 8)

    def test_achievements_are_only_for_own_children(self):
        other = Student.objects.create(first_name="Other", last_name="Kid", group=self.g1)
        self.assertEqual(self.client_.get(reverse("portal:achievements", args=[other.pk])).status_code, 404)

    def test_next_homework_card_names_the_group(self):
        upcoming = self.lesson(self.g1, self.gt1, TODAY + dt.timedelta(days=2), number=2, status_=Lesson.Status.SCHEDULED)
        Homework.objects.create(lesson=upcoming, title="Next")
        data = self.client_.get(reverse("portal:homework-next", args=[self.student.pk])).data
        self.assertEqual(data["lessons"][0]["homework"][0]["group"]["name"], "PRO-01")
