from __future__ import annotations

import datetime as dt
from unittest import mock

from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.scholarships.models import ScholarshipPeriod, TrainerFeedback
from apps.scholarships.services.generation import approve_period
from apps.users.models import User

from .base import OCT_1, ScholarshipFixture, make_user

FEEDBACK = {"progress": 4, "participation": 5, "discipline": 5, "understanding": 4, "comment": "Молодец"}


class ScholarshipAPITestBase(ScholarshipFixture):
    def setUp(self):
        super().setUp()
        self.configure(require_complete_feedback=False)
        self.s1 = self.student("Aibek")
        self.s2 = self.student("Nurai")
        self.study(self.s1, self.python, self.t_python)
        self.study(self.s2, self.english, self.t_english)
        self.period = self.generate()
        self.client = APIClient()

    def as_admin(self):
        self.client.force_authenticate(self.admin)

    def as_teacher(self, teacher=None):
        self.client.force_authenticate((teacher or self.t_python).user)

    def url(self, name, *args):
        return reverse(name, args=args)


class AdminAPITests(ScholarshipAPITestBase):
    def test_admin_lists_periods_with_counts(self):
        self.as_admin()
        response = self.client.get(self.url("scholarship-period-list"))
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertEqual((row["evaluations_count"], row["eligible_count"], row["recipients_count"]), (2, 2, 2))
        self.assertEqual(row["max_recipients"], 20)

    def test_ranking_and_student_history(self):
        self.as_admin()
        response = self.client.get(self.url("scholarship-period-ranking", self.period.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["rank"] for r in response.data["results"]], [1, 2])
        self.assertEqual(response.data["results"][0]["award_status"], "pending")

        response = self.client.get(self.url("scholarship-evaluation-student-history", self.s1.pk))
        self.assertEqual(response.status_code, 200)
        [item] = response.data["results"]
        # English shows up too: s2's English lessons are in s1's group and
        # s1 has no attendance mark for them — reported, not scored.
        rows = {row["subject_name"]: row for row in item["subject_scores"]}
        self.assertEqual(rows["Python"]["lessons_attended"], 4)
        self.assertEqual((rows["English"]["lessons_unmarked"], rows["English"]["aggregation_weight"]), (4, "0.00"))

    def test_evaluation_detail_has_subject_breakdown(self):
        self.as_admin()
        ev = self.period.evaluations.get(student=self.s1)
        response = self.client.get(self.url("scholarship-evaluation-detail", ev.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("subject_scores", response.data)
        self.assertIn("data_warnings", response.data)

    def test_generate_is_idempotent(self):
        self.as_admin()
        with mock.patch("django.utils.timezone.localdate", return_value=OCT_1):
            response = self.client.post(self.url("scholarship-period-generate"), {"award_day": 1, "award_date": "2026-10-01"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "exists")
        self.assertEqual(ScholarshipPeriod.objects.count(), 1)

    def test_generate_rejects_invalid_input(self):
        self.as_admin()
        response = self.client.post(self.url("scholarship-period-generate"), {"award_day": 1, "award_date": "2026-10-02"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(self.url("scholarship-period-generate"), {"award_day": 7})
        self.assertEqual(response.status_code, 400)
        future = (dt.date.today().replace(day=1) + dt.timedelta(days=62)).replace(day=1)
        response = self.client.post(self.url("scholarship-period-generate"), {"award_day": 1, "award_date": future.isoformat()})
        self.assertEqual(response.status_code, 400)

    def test_generate_new_period(self):
        self.as_admin()
        response = self.client.post(self.url("scholarship-period-generate"), {"award_day": 1, "award_date": "2026-09-01"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["period_start"], "2026-08-01")

    def test_recalculate_approve_analytics_export(self):
        self.as_admin()
        self.assertEqual(self.client.post(self.url("scholarship-period-recalculate", self.period.pk)).status_code, 200)
        response = self.client.post(self.url("scholarship-period-approve", self.period.pk))
        self.assertEqual((response.status_code, response.data["status"]), (200, "approved"))
        self.assertEqual(self.client.post(self.url("scholarship-period-approve", self.period.pk)).status_code, 400)
        self.assertEqual(self.client.post(self.url("scholarship-period-recalculate", self.period.pk)).status_code, 400)

        analytics = self.client.get(self.url("scholarship-period-analytics", self.period.pk)).data
        self.assertEqual((analytics["total_eligible"], analytics["total_recipients"]), (2, 2))
        self.assertEqual({s["subject_name"] for s in analytics["subjects"]}, {"Python", "English"})

        export = self.client.get(self.url("scholarship-period-export", self.period.pk))
        self.assertEqual(export.status_code, 200)
        self.assertIn("Aibek", export.content.decode("utf-8"))

        summary = self.client.get(self.url("scholarship-period-summary")).data
        self.assertEqual(summary["awards_by_month"], [{"year": 2026, "month": 10, "total": 2, "approved": 2}])
        awards = self.client.get(self.url("scholarship-award-list")).data["results"]
        self.assertEqual({a["status"] for a in awards}, {"approved"})

    def test_admin_enters_feedback_on_behalf_of_a_trainer(self):
        self.as_admin()
        body = {"period": self.period.pk, "student": self.s1.pk, "subject": self.python.pk, **FEEDBACK}
        response = self.client.post(self.url("scholarship-feedback-list"), body)
        self.assertEqual(response.status_code, 400)  # teacher is required for admins
        response = self.client.post(self.url("scholarship-feedback-list"), {**body, "teacher": self.t_python.pk})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["score"], "90.00")

    def test_non_admin_staff_needs_explicit_permission(self):
        # A superuser/ADMIN role always passes; an ADMIN-role user without
        # superuser still passes via role — the explicit permission is for
        # any other account an owner decides to trust.
        admin_role = make_user("adminrole", role=User.Role.ADMIN)
        self.client.force_authenticate(admin_role)
        self.assertEqual(self.client.post(self.url("scholarship-period-approve", self.period.pk)).status_code, 200)


class TeacherAPITests(ScholarshipAPITestBase):
    def test_teacher_sees_period_dates_only(self):
        self.as_teacher()
        response = self.client.get(self.url("scholarship-period-list"))
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertNotIn("max_recipients", row)
        self.assertNotIn("recipients_count", row)

    def test_teacher_cannot_see_rankings_evaluations_or_awards(self):
        self.as_teacher()
        ev = self.period.evaluations.first()
        for url in (
            self.url("scholarship-period-ranking", self.period.pk),
            self.url("scholarship-period-analytics", self.period.pk),
            self.url("scholarship-period-export", self.period.pk),
            self.url("scholarship-period-summary"),
            self.url("scholarship-evaluation-list"),
            self.url("scholarship-evaluation-detail", ev.pk),
            self.url("scholarship-evaluation-student-history", self.s1.pk),
            self.url("scholarship-award-list"),
        ):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_teacher_cannot_generate_recalculate_or_approve(self):
        self.as_teacher()
        self.assertEqual(self.client.post(self.url("scholarship-period-generate"), {"award_day": 1}).status_code, 403)
        self.assertEqual(self.client.post(self.url("scholarship-period-recalculate", self.period.pk)).status_code, 403)
        self.assertEqual(self.client.post(self.url("scholarship-period-approve", self.period.pk)).status_code, 403)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, ScholarshipPeriod.Status.DRAFT)

    def test_required_feedback_list(self):
        self.as_teacher()
        response = self.client.get(self.url("scholarship-feedback-required"), {"period": self.period.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["total"], response.data["missing"]), (1, 1))
        self.assertEqual(response.data["items"][0]["student"], self.s1.pk)
        self.assertFalse(response.data["items"][0]["is_submitted"])

    def test_teacher_submits_and_updates_own_feedback(self):
        self.as_teacher()
        body = {"period": self.period.pk, "student": self.s1.pk, "subject": self.python.pk, **FEEDBACK}
        response = self.client.post(self.url("scholarship-feedback-list"), body)
        self.assertEqual(response.status_code, 201, response.data)
        feedback = TrainerFeedback.objects.get()
        self.assertEqual((feedback.teacher, feedback.created_by), (self.t_python, self.t_python.user))

        duplicate = self.client.post(self.url("scholarship-feedback-list"), body)
        self.assertEqual(duplicate.status_code, 400)

        response = self.client.patch(self.url("scholarship-feedback-detail", feedback.pk), {"progress": 5, "student": self.s2.pk})
        self.assertEqual(response.status_code, 200)
        feedback.refresh_from_db()
        self.assertEqual((feedback.progress, feedback.student), (5, self.s1))  # re-targeting is ignored

        listing = self.client.get(self.url("scholarship-feedback-required"), {"period": self.period.pk}).data
        self.assertEqual(listing["missing"], 0)

    def test_teacher_cannot_assess_students_they_did_not_teach(self):
        self.as_teacher()
        body = {"period": self.period.pk, "student": self.s2.pk, "subject": self.english.pk, **FEEDBACK}
        self.assertEqual(self.client.post(self.url("scholarship-feedback-list"), body).status_code, 400)
        body = {"period": self.period.pk, "student": self.s1.pk, "subject": self.english.pk, **FEEDBACK}
        self.assertEqual(self.client.post(self.url("scholarship-feedback-list"), body).status_code, 400)

    def test_teacher_cannot_touch_another_teachers_feedback(self):
        other = self.feedback(self.period, self.s2, self.english, self.t_english)
        self.as_teacher()
        self.assertEqual(self.client.get(self.url("scholarship-feedback-detail", other.pk)).status_code, 404)
        self.assertEqual(self.client.patch(self.url("scholarship-feedback-detail", other.pk), {"progress": 1}).status_code, 404)
        self.assertEqual(self.client.get(self.url("scholarship-feedback-list")).data["results"], [])

    def test_feedback_is_closed_after_approval(self):
        mine = self.feedback(self.period, self.s1, self.python, self.t_python)
        approve_period(self.period)
        self.as_teacher()
        self.assertEqual(self.client.patch(self.url("scholarship-feedback-detail", mine.pk), {"progress": 1}).status_code, 400)
        mine.refresh_from_db()
        self.assertEqual(mine.progress, 5)

    def test_feedback_validation(self):
        self.as_teacher()
        body = {"period": self.period.pk, "student": self.s1.pk, "subject": self.python.pk, **FEEDBACK, "progress": 6}
        self.assertEqual(self.client.post(self.url("scholarship-feedback-list"), body).status_code, 400)
        self.assertEqual(self.client.get(self.url("scholarship-feedback-required")).status_code, 400)

    def test_admin_cannot_use_teacher_required_list(self):
        self.as_admin()
        self.assertEqual(
            self.client.get(self.url("scholarship-feedback-required"), {"period": self.period.pk}).status_code, 403
        )


class AnonymousAPITests(ScholarshipAPITestBase):
    def test_every_endpoint_requires_authentication(self):
        for url in (
            self.url("scholarship-period-list"),
            self.url("scholarship-evaluation-list"),
            self.url("scholarship-award-list"),
            self.url("scholarship-feedback-list"),
        ):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED, url)
        self.assertEqual(self.client.post(self.url("scholarship-period-generate")).status_code, 401)

    def test_account_without_teacher_profile_is_refused(self):
        self.client.force_authenticate(make_user("orphan"))
        self.assertEqual(self.client.get(self.url("scholarship-period-list")).status_code, 403)
        self.assertEqual(self.client.get(self.url("scholarship-feedback-list")).status_code, 403)


class AdminPanelTests(ScholarshipAPITestBase):
    def setUp(self):
        super().setUp()
        self.web = self.client_class()
        self.web.force_login(self.admin)

    def test_dashboard_pages_render(self):
        ev = self.period.evaluations.get(student=self.s1)
        for url in (
            reverse("admin:scholarships_scholarshipperiod_changelist"),
            reverse("admin:scholarships_scholarshipperiod_change", args=[self.period.pk]),
            reverse("admin:scholarships_scholarshipevaluation_changelist"),
            reverse("admin:scholarships_scholarshipevaluation_change", args=[ev.pk]),
            reverse("admin:scholarships_scholarshipaward_changelist"),
            reverse("admin:scholarships_trainerfeedback_changelist"),
            reverse("admin:scholarships_scholarshipconfiguration_changelist"),
            reverse("admin:scholarships_scholarshiprunlog_changelist"),
            reverse("admin:scholarships_generate"),
        ):
            response = self.web.get(url)
            self.assertEqual(response.status_code, 200, url)
        detail = self.web.get(reverse("admin:scholarships_scholarshipperiod_change", args=[self.period.pk]))
        self.assertContains(detail, "Aibek")
        self.assertContains(detail, "Утвердить стипендии")
        student_page = self.web.get(reverse("admin:scholarships_scholarshipevaluation_change", args=[ev.pk]))
        self.assertContains(student_page, "Разбивка по предметам")
        self.assertContains(student_page, "История оценок студента")

    def test_generate_recalculate_approve_export_from_admin(self):
        response = self.web.post(reverse("admin:scholarships_generate"), {"award_day": 1, "award_date": "2026-09-01"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ScholarshipPeriod.objects.count(), 2)

        response = self.web.post(reverse("admin:scholarships_generate"), {"award_day": 1, "award_date": "2026-09-02"})
        self.assertContains(response, "не совпадает с днём цикла")

        self.web.post(reverse("admin:scholarships_recalculate", args=[self.period.pk]))
        self.web.post(reverse("admin:scholarships_approve", args=[self.period.pk]))
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, ScholarshipPeriod.Status.APPROVED)

        export = self.web.get(reverse("admin:scholarships_export", args=[self.period.pk]))
        self.assertEqual(export["Content-Type"], "text/csv; charset=utf-8")

    def test_approve_requires_post(self):
        self.web.get(reverse("admin:scholarships_approve", args=[self.period.pk]))
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, ScholarshipPeriod.Status.DRAFT)

    def test_staff_without_permission_cannot_approve(self):
        staff = make_user("staffer")
        staff.is_staff = True
        staff.save()
        staff.user_permissions.add(Permission.objects.get(codename="view_scholarshipperiod"))
        web = self.client_class()
        web.force_login(staff)
        response = web.post(reverse("admin:scholarships_approve", args=[self.period.pk]))
        self.assertEqual(response.status_code, 403)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, ScholarshipPeriod.Status.DRAFT)

    def test_feedback_admin_rejects_untaught_student(self):
        response = self.web.post(reverse("admin:scholarships_trainerfeedback_add"), {
            "period": self.period.pk, "student": self.s2.pk, "subject": self.python.pk, "teacher": self.t_python.pk,
            "progress": 5, "participation": 5, "discipline": 5, "understanding": 5, "comment": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "не вёл у студента")
        self.assertFalse(TrainerFeedback.objects.exists())
