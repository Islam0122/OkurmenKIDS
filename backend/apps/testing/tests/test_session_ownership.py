"""«Экзамены»: a trainer sees only the exam sessions that belong to them —
TestSession.objects.for_teacher (session.teacher, or for a session without
one the group's program for the test's subject) — never every session of a
group they also teach in, nor of a subject they also teach. Checked on the
API itself (list + detail + participants + start + monitoring), not in the
UI. Admin / Team Lead keep every session.

The real case: Prog SOFT 1 — English with Aizhan, Soft Skills with Nurisa;
«Soft Skills — Month 1» (Nurisa's) was listed for Aizhan.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, GroupTeacher, Student
from apps.academy.tests import make_admin, make_teacher
from apps.testing.models import StudentAttempt, Test, TestSession
from apps.users.models import Subject, User


class OwnershipFixture(TestCase):
    def setUp(self):
        self.aizhan = make_teacher("aizhan_exam")
        self.nurisa = make_teacher("nurisa_exam")
        self.soft = Subject.objects.get_or_create(name="Soft Skills")[0]
        self.english = Subject.objects.get_or_create(name="English")[0]
        self.it = Subject.objects.get_or_create(name="IT")[0]
        course = Course.objects.create(name="Prog", count_lesson=0)
        self.prog_soft = Group.objects.create(name="Prog SOFT 1", course=course, start_date="2026-09-01")
        self.prog_soft_2 = Group.objects.create(name="Prog SOFT 2", course=course, start_date="2026-09-01")
        self.prog_it = Group.objects.create(name="Prog IT 1", course=course, start_date="2026-09-01")
        # Prog SOFT 1: English — Aizhan, Soft Skills — Nurisa.
        GroupTeacher.objects.create(group=self.prog_soft, teacher=self.aizhan, subject=self.english)
        GroupTeacher.objects.create(group=self.prog_soft, teacher=self.nurisa, subject=self.soft)
        # Prog SOFT 2: Soft Skills — Aizhan (both teach Soft Skills).
        GroupTeacher.objects.create(group=self.prog_soft_2, teacher=self.aizhan, subject=self.soft)
        # Prog IT 1: IT — Aizhan (she teaches several subjects).
        GroupTeacher.objects.create(group=self.prog_it, teacher=self.aizhan, subject=self.it)

        self.soft_test = Test.objects.create(title="Soft Skills — Month 1", subject=self.soft)
        self.english_test = Test.objects.create(title="English — Month 1", subject=self.english)
        self.it_test = Test.objects.create(title="IT — Month 1", subject=self.it)

        self.nurisa_soft = self.session(self.soft_test, self.prog_soft, self.nurisa)       # the bug's exam
        self.aizhan_english = self.session(self.english_test, self.prog_soft, self.aizhan)
        self.aizhan_soft_2 = self.session(self.soft_test, self.prog_soft_2, self.aizhan)
        self.aizhan_it = self.session(self.it_test, self.prog_it, self.aizhan)

        self.admin = make_admin("exam_admin")
        self.lead = User.objects.create_user(username="exam_lead", email="el@okurmen.kg", password="x",
                                             first_name="Lead", role=User.Role.TEAM_LEAD)
        self.api = APIClient()

    @staticmethod
    def session(test, group, teacher):
        return TestSession.objects.create(test=test, group=group, teacher=teacher, title=test.title)

    def ids(self, user, **params):
        self.api.force_authenticate(user)
        response = self.api.get("/api/v1/teacher/sessions/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["id"] for row in response.data["results"]}

    def detail(self, user, session, suffix=""):
        self.api.force_authenticate(user)
        return self.api.get(f"/api/v1/teacher/sessions/{session.pk}/{suffix}")


class ExamListTests(OwnershipFixture):
    # Test 1 — another trainer's exam is not returned
    def test_1_other_trainers_exam_is_not_in_the_list(self):
        self.assertNotIn(str(self.nurisa_soft.pk), self.ids(self.aizhan.user))
        self.api.force_authenticate(self.aizhan.user)
        titles = [(r["title"], r["teacher_name"]) for r in self.api.get("/api/v1/teacher/sessions/").data["results"]]
        self.assertNotIn(("Soft Skills — Month 1", str(self.nurisa)), titles)

    # Test 2 — the owner sees it
    def test_2_owner_sees_their_exam(self):
        self.assertIn(str(self.nurisa_soft.pk), self.ids(self.nurisa.user))
        self.assertEqual(self.ids(self.nurisa.user), {str(self.nurisa_soft.pk)})

    # Test 3 — Admin and Team Lead see every exam
    def test_3_admin_and_team_lead_see_all(self):
        everything = {str(s.pk) for s in TestSession.objects.all()}
        self.assertEqual(self.ids(self.admin), everything)
        self.assertEqual(self.ids(self.lead), everything)
        for user in (self.admin, self.lead):
            self.assertEqual(self.detail(user, self.nurisa_soft).status_code, 200)

    # Test 4 — several groups: only the exams of her own programs
    def test_4_trainer_with_several_groups_sees_only_her_exams(self):
        self.assertEqual(
            self.ids(self.aizhan.user),
            {str(self.aizhan_english.pk), str(self.aizhan_soft_2.pk), str(self.aizhan_it.pk)},
        )
        # The group filter can't widen it either.
        self.assertEqual(self.ids(self.aizhan.user, group=self.prog_soft.pk), {str(self.aizhan_english.pk)})

    # Test 5 — same subject, different trainers: no cross-visibility
    def test_5_same_subject_does_not_share_exams(self):
        aizhan, nurisa = self.ids(self.aizhan.user), self.ids(self.nurisa.user)
        self.assertIn(str(self.aizhan_soft_2.pk), aizhan)
        self.assertNotIn(str(self.nurisa_soft.pk), aizhan)
        self.assertNotIn(str(self.aizhan_soft_2.pk), nurisa)

    # Test 6 — several subjects: only her assignments' exams
    def test_6_several_subjects_only_own_assignments(self):
        it_other = self.session(self.it_test, self.prog_it, self.nurisa)  # IT exam recorded under someone else
        english_elsewhere = self.session(self.english_test, self.prog_soft_2, None)  # no English program for her there
        visible = self.ids(self.aizhan.user)
        self.assertIn(str(self.aizhan_it.pk), visible)
        self.assertNotIn(str(it_other.pk), visible)
        self.assertNotIn(str(english_elsewhere.pk), visible)

    def test_session_without_teacher_belongs_to_the_groups_program_for_its_subject(self):
        legacy = self.session(self.soft_test, self.prog_soft, None)
        self.assertIn(str(legacy.pk), self.ids(self.nurisa.user))      # Soft Skills program of Prog SOFT 1
        self.assertNotIn(str(legacy.pk), self.ids(self.aizhan.user))   # she teaches English there
        GroupTeacher.objects.filter(group=self.prog_soft, teacher=self.nurisa).update(is_active=False)
        self.assertNotIn(str(legacy.pk), self.ids(self.nurisa.user))   # inactive program — no access


class DirectAccessTests(OwnershipFixture):
    def test_detail_participants_and_result_of_another_trainers_exam_are_404(self):
        student = Student.objects.create(first_name="Айдай", group=self.prog_soft)
        participant = self.nurisa_soft.participants.create(student=student)
        for suffix in ("", "participants/", f"participants/{participant.pk}/result/"):
            self.assertEqual(self.detail(self.aizhan.user, self.nurisa_soft, suffix).status_code, 404, suffix)
        self.assertEqual(self.detail(self.nurisa.user, self.nurisa_soft).status_code, 200)
        self.assertEqual(self.detail(self.nurisa.user, self.nurisa_soft, "participants/").status_code, 200)

    def test_trainer_cannot_start_or_create(self):
        self.api.force_authenticate(self.aizhan.user)
        self.assertEqual(self.api.post(f"/api/v1/teacher/sessions/{self.nurisa_soft.pk}/start/").status_code, 403)
        self.assertEqual(self.api.post(f"/api/v1/teacher/sessions/{self.aizhan_it.pk}/start/").status_code, 403)

    def test_monitoring_does_not_leak_another_trainers_exam(self):
        student = Student.objects.create(first_name="Айдай", group=self.prog_soft)
        foreign = StudentAttempt.objects.create(session=self.nurisa_soft, student=student, student_name="Айдай")
        own = StudentAttempt.objects.create(session=self.aizhan_english, student=student, student_name="Айдай")
        self.api.force_authenticate(self.aizhan.user)
        rows = {r["id"] for r in self.api.get("/api/v1/monitoring/attempts/").data["results"]}
        self.assertIn(str(own.pk), rows)
        self.assertNotIn(str(foreign.pk), rows)
        self.assertEqual(self.api.get(f"/api/v1/monitoring/attempts/{foreign.pk}/").status_code, 404)
        options = self.api.get("/api/v1/monitoring/filters/").data
        self.assertNotIn(str(self.nurisa_soft.pk), {s["id"] for s in options["sessions"]})
        self.api.force_authenticate(self.lead)
        rows = {r["id"] for r in self.api.get("/api/v1/monitoring/attempts/").data["results"]}
        self.assertTrue({str(own.pk), str(foreign.pk)} <= rows)
