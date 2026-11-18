"""Bulk copy of trainer scores between subjects (services.score_copy).

Absolute imports only — see apps/scholarships/tests/base.py."""
from __future__ import annotations

import datetime as dt
import uuid
from unittest import mock

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.scholarships.models import ScholarshipPeriod, ScoreCopyItem, ScoreCopyOperation, TrainerFeedback
from apps.scholarships.services import score_copy as svc
from apps.scholarships.tests.base import SEP_1, ScholarshipFixture, make_teacher, make_user
from apps.users.models import Subject, User

LIST_URL = "/api/v1/scholarship-score-copies/"
PREVIEW_URL = f"{LIST_URL}preview/"


def scores(fb: TrainerFeedback) -> tuple:
    return (fb.progress, fb.participation, fb.discipline, fb.understanding)


class ScoreCopyFixture(ScholarshipFixture):
    """Prog SOFT 1 in September: IT (Python, trainer tpython) and Soft Skills
    (trainer tsoft) lessons.

    * Aibek — IT score (5,4,3,2), Soft Skills lessons, no Soft Skills score → create
    * Bekzat — IT (3,3,3,3), Soft Skills score (1,1,1,1) already there → existing
    * Chyngyz — IT (4,4,4,4) but no Soft Skills lessons → unmatched
    * Dana — Soft Skills lessons, no IT score → empty
    * two students both named «Ali Same» with different IT scores — matched by id.
    """

    def setUp(self):
        super().setUp()
        self.soft = Subject.objects.get_or_create(name="Soft Skills")[0]
        self.course.subjects.add(self.soft)
        self.t_soft = make_teacher("tsoft")
        self.aibek = self.student("Aibek")
        self.bekzat = self.student("Bekzat")
        self.chyngyz = self.student("Chyngyz")
        self.dana = self.student("Dana")
        self.same1 = self.student("Ali", last_name="Same")
        self.same2 = self.student("Ali", last_name="Same")
        it_lesson = self.lesson(self.python, self.t_python, SEP_1)
        soft_lesson = self.lesson(self.soft, self.t_soft, SEP_1 + dt.timedelta(days=1))
        for s in (self.aibek, self.bekzat, self.chyngyz, self.dana, self.same1, self.same2):
            self.attend(s, it_lesson)
        for s in (self.aibek, self.bekzat, self.dana, self.same1, self.same2):
            self.attend(s, soft_lesson)
        self.period = self.generate()
        self.feedback(self.period, self.aibek, self.python, self.t_python, (5, 4, 3, 2))
        self.feedback(self.period, self.bekzat, self.python, self.t_python, (3, 3, 3, 3))
        self.feedback(self.period, self.chyngyz, self.python, self.t_python, (4, 4, 4, 4))
        self.feedback(self.period, self.same1, self.python, self.t_python, (1, 2, 3, 4))
        self.feedback(self.period, self.same2, self.python, self.t_python, (4, 3, 2, 1))
        self.existing = self.feedback(self.period, self.bekzat, self.soft, self.t_soft, (1, 1, 1, 1))
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def body(self, **extra) -> dict:
        return {"group": self.group.pk, "source_subject": self.python.pk, "target_subject": self.soft.pk,
                "source_period": self.period.pk, "target_period": self.period.pk, **extra}

    def preview(self, **extra):
        response = self.client.post(PREVIEW_URL, self.body(**extra), format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def apply(self, preview=None, expect=201, **extra):
        preview = preview or self.preview(**extra)
        payload = self.body(fingerprint=preview["fingerprint"], operation_id=str(uuid.uuid4()), **extra)
        response = self.client.post(LIST_URL, payload, format="json")
        self.assertEqual(response.status_code, expect, response.content)
        return response

    def soft_scores(self, student):
        return scores(TrainerFeedback.objects.get(period=self.period, student=student, subject=self.soft))

    def row(self, data, student):
        return next(r for r in data["rows"] if r["student_id"] == student.pk)


class PreviewTests(ScoreCopyFixture):
    def test_preview_classifies_every_student_by_id(self):
        data = self.preview()
        actions = {r["student_id"]: r["action"] for r in data["rows"]}
        self.assertEqual(actions[self.aibek.pk], svc.CREATE)
        self.assertEqual(actions[self.bekzat.pk], svc.SKIP_EXISTING)
        self.assertEqual(actions[self.chyngyz.pk], svc.UNMATCHED_TARGET)
        self.assertEqual(actions[self.dana.pk], svc.SKIP_EMPTY)
        summary = data["summary"]
        self.assertEqual(summary["students"], 6)
        self.assertEqual(summary["copyable"], 3)  # Aibek + both «Ali Same»
        self.assertEqual(summary["empty"], 1)
        self.assertEqual(summary["existing_target"], 1)
        self.assertEqual(summary["unmatched"], 1)
        self.assertEqual(summary["overwrite"], 0)
        self.assertEqual(self.row(data, self.aibek)["target_teacher"]["id"], self.t_soft.pk)
        self.assertEqual(TrainerFeedback.objects.filter(subject=self.soft).count(), 1, "preview never writes")

    def test_overwrite_preview_lists_old_and_new_values(self):
        data = self.preview(conflict="overwrite")
        row = self.row(data, self.bekzat)
        self.assertEqual(row["action"], svc.OVERWRITE)
        self.assertEqual(row["target"]["progress"], 1)
        self.assertEqual(row["after"]["progress"], 3)
        self.assertEqual(data["summary"]["overwrite"], 1)

    def test_same_source_and_target_is_refused(self):
        response = self.client.post(PREVIEW_URL, self.body(target_subject=self.python.pk), format="json")
        self.assertEqual(response.status_code, 400)

    def test_approved_target_period_is_refused(self):
        ScholarshipPeriod.objects.filter(pk=self.period.pk).update(status=ScholarshipPeriod.Status.APPROVED)
        response = self.client.post(PREVIEW_URL, self.body(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("утверждён", response.data["detail"])

    def test_options_list_groups_periods_and_group_subjects(self):
        data = self.client.get(f"{LIST_URL}options/", {"group": self.group.pk}).data
        self.assertIn(self.group.pk, [g["id"] for g in data["groups"]])
        self.assertIn(self.period.pk, [p["id"] for p in data["periods"]])
        self.assertIn("Soft Skills", [s["name"] for s in data["subjects"]])


class ApplyTests(ScoreCopyFixture):
    def test_copy_preserves_existing_and_matches_by_id(self):
        response = self.apply()
        self.assertEqual(self.soft_scores(self.aibek), (5, 4, 3, 2))
        self.assertEqual(self.soft_scores(self.bekzat), (1, 1, 1, 1), "existing score preserved")
        # Same name, different students: each keeps its own values.
        self.assertEqual(self.soft_scores(self.same1), (1, 2, 3, 4))
        self.assertEqual(self.soft_scores(self.same2), (4, 3, 2, 1))
        self.assertFalse(TrainerFeedback.objects.filter(student=self.chyngyz, subject=self.soft).exists())
        self.assertFalse(TrainerFeedback.objects.filter(student=self.dana, subject=self.soft).exists())
        created = TrainerFeedback.objects.get(student=self.aibek, subject=self.soft)
        self.assertEqual(created.teacher, self.t_soft)
        self.assertEqual(created.created_by, self.admin)

        op = ScoreCopyOperation.objects.get()
        self.assertEqual((op.copied_count, op.overwritten_count, op.skipped_count), (3, 0, 3))
        self.assertEqual(op.created_by, self.admin)
        self.assertEqual((op.source_subject_name, op.target_subject_name, op.group_name),
                         ("Python", "Soft Skills", self.group.name))
        self.assertEqual(op.skipped_details, {svc.SKIP_EXISTING: 1, svc.SKIP_EMPTY: 1, svc.UNMATCHED_TARGET: 1})
        self.assertEqual(str(op.operation_id), response.data["operation_id"])
        self.assertEqual(op.items.count(), 3)

    def test_overwrite_requires_explicit_confirmation(self):
        preview = self.preview(conflict="overwrite")
        payload = self.body(conflict="overwrite", fingerprint=preview["fingerprint"], operation_id=str(uuid.uuid4()))
        response = self.client.post(LIST_URL, payload, format="json")
        self.assertEqual(response.status_code, 428)
        self.assertEqual(self.soft_scores(self.bekzat), (1, 1, 1, 1))
        self.assertFalse(ScoreCopyOperation.objects.exists())

        payload["confirm_overwrite"] = True
        self.assertEqual(self.client.post(LIST_URL, payload, format="json").status_code, 201)
        self.assertEqual(self.soft_scores(self.bekzat), (3, 3, 3, 3))
        op = ScoreCopyOperation.objects.get()
        self.assertEqual(op.overwritten_count, 1)
        item = op.items.get(student=self.bekzat)
        self.assertEqual(item.before["progress"], 1)
        self.assertEqual(item.after["progress"], 3)

    def test_comment_is_kept_unless_asked(self):
        TrainerFeedback.objects.filter(pk=self.existing.pk).update(comment="Soft note")
        TrainerFeedback.objects.filter(student=self.bekzat, subject=self.python).update(comment="IT note")
        preview = self.preview(conflict="overwrite")
        self.client.post(LIST_URL, self.body(conflict="overwrite", fingerprint=preview["fingerprint"],
                                             operation_id=str(uuid.uuid4()), confirm_overwrite=True), format="json")
        self.assertEqual(TrainerFeedback.objects.get(pk=self.existing.pk).comment, "Soft note")

    def test_selected_students_only(self):
        self.apply(mode="selected", student_ids=[self.same2.pk])
        self.assertEqual(self.soft_scores(self.same2), (4, 3, 2, 1))
        self.assertFalse(TrainerFeedback.objects.filter(student__in=[self.aibek, self.same1], subject=self.soft).exists())

    def test_stale_preview_is_refused_and_nothing_written(self):
        preview = self.preview()
        TrainerFeedback.objects.filter(student=self.aibek, subject=self.python).update(progress=1)
        response = self.apply(preview=preview, expect=409)
        self.assertIn("изменились", response.data["detail"])
        self.assertEqual(TrainerFeedback.objects.filter(subject=self.soft).count(), 1)
        self.assertFalse(ScoreCopyOperation.objects.exists())

    def test_same_operation_id_is_applied_once(self):
        preview = self.preview()
        payload = self.body(fingerprint=preview["fingerprint"], operation_id=str(uuid.uuid4()))
        first = self.client.post(LIST_URL, payload, format="json")
        second = self.client.post(LIST_URL, payload, format="json")
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertTrue(second.data["replayed"])
        self.assertEqual(ScoreCopyOperation.objects.count(), 1)
        self.assertEqual(TrainerFeedback.objects.filter(subject=self.soft).count(), 4)

    def test_repeating_the_copy_changes_nothing(self):
        self.apply()
        again = self.preview()
        self.assertEqual(again["summary"]["copyable"], 0)
        self.assertEqual(again["summary"]["unchanged"], 3)
        response = self.apply(preview=again, expect=400)
        self.assertIn("Нечего копировать", response.data["detail"])
        self.assertEqual(ScoreCopyOperation.objects.count(), 1)

    def test_error_mid_copy_rolls_everything_back(self):
        preview = self.preview()
        real = svc.validate_feedback_target
        calls = {"n": 0}

        def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ValidationError("boom")
            return real(**kwargs)

        with mock.patch.object(svc, "validate_feedback_target", side_effect=flaky):
            response = self.apply(preview=preview, expect=400)
        self.assertIn("boom", response.data["detail"])
        self.assertEqual(TrainerFeedback.objects.filter(subject=self.soft).count(), 1, "the first row was rolled back")
        self.assertFalse(ScoreCopyOperation.objects.exists())
        self.assertFalse(ScoreCopyItem.objects.exists())

    def test_ambiguous_target_trainer_needs_a_choice(self):
        t_soft2 = make_teacher("tsoft2")
        lesson = self.lesson(self.soft, t_soft2, SEP_1 + dt.timedelta(days=2))
        self.attend(self.aibek, lesson)
        self.assertEqual(self.row(self.preview(), self.aibek)["action"], svc.UNMATCHED_TARGET_AMBIGUOUS)
        data = self.preview(target_teacher=t_soft2.pk)
        self.assertEqual(self.row(data, self.aibek)["action"], svc.CREATE)
        self.apply(preview=data, target_teacher=t_soft2.pk)
        self.assertEqual(TrainerFeedback.objects.get(student=self.aibek, subject=self.soft).teacher, t_soft2)

    def test_disagreeing_source_trainers_are_not_guessed(self):
        t_python2 = make_teacher("tpython2")
        lesson = self.lesson(self.python, t_python2, SEP_1 + dt.timedelta(days=3))
        self.attend(self.aibek, lesson)
        self.feedback(self.period, self.aibek, self.python, t_python2, (1, 1, 1, 1))
        self.assertEqual(self.row(self.preview(), self.aibek)["action"], svc.UNMATCHED_SOURCE)
        data = self.preview(source_teacher=t_python2.pk)
        self.assertEqual(self.row(data, self.aibek)["after"]["progress"], 1)


class UndoTests(ScoreCopyFixture):
    def test_undo_restores_and_deletes_exactly_what_the_copy_did(self):
        preview = self.preview(conflict="overwrite")
        op_id = self.client.post(LIST_URL, self.body(conflict="overwrite", fingerprint=preview["fingerprint"],
                                                     operation_id=str(uuid.uuid4()), confirm_overwrite=True),
                                 format="json").data["id"]
        response = self.client.post(f"{LIST_URL}{op_id}/undo/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["status"], ScoreCopyOperation.Status.REVERTED)
        self.assertEqual(self.soft_scores(self.bekzat), (1, 1, 1, 1), "overwritten row restored")
        self.assertEqual(TrainerFeedback.objects.filter(subject=self.soft).count(), 1, "created rows removed")
        self.assertEqual(self.client.post(f"{LIST_URL}{op_id}/undo/").status_code, 409, "undo only once")

    def test_undo_never_overwrites_later_manual_changes(self):
        op_id = self.apply().data["id"]
        manual = TrainerFeedback.objects.get(student=self.aibek, subject=self.soft)
        manual.progress = 2
        manual.save()
        data = self.client.post(f"{LIST_URL}{op_id}/undo/").data
        self.assertEqual(data["status"], ScoreCopyOperation.Status.PARTIALLY_REVERTED)
        self.assertEqual(self.soft_scores(self.aibek), (2, 4, 3, 2), "manual edit kept")
        self.assertFalse(TrainerFeedback.objects.filter(student=self.same1, subject=self.soft).exists())
        results = {item["student_id"]: item["undo_result"] for item in data["items"]}
        self.assertEqual(results[self.aibek.pk], ScoreCopyItem.UndoResult.SKIPPED_CHANGED)
        self.assertEqual(results[self.same1.pk], ScoreCopyItem.UndoResult.DELETED)

    def test_undo_refused_after_period_approval(self):
        op_id = self.apply().data["id"]
        ScholarshipPeriod.objects.filter(pk=self.period.pk).update(status=ScholarshipPeriod.Status.APPROVED)
        self.assertEqual(self.client.post(f"{LIST_URL}{op_id}/undo/").status_code, 400)
        self.assertEqual(TrainerFeedback.objects.filter(subject=self.soft).count(), 4)

    def test_history_lists_operations(self):
        self.apply()
        rows = self.client.get(LIST_URL).data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["copied"], 3)
        self.assertTrue(rows[0]["can_undo"])


class PermissionTests(ScoreCopyFixture):
    def assert_blocked(self, client, expected=(401, 403)):
        for method, url in (("get", LIST_URL), ("get", f"{LIST_URL}options/"), ("post", PREVIEW_URL), ("post", LIST_URL)):
            response = getattr(client, method)(url, self.body(), format="json")
            self.assertIn(response.status_code, expected, f"{method} {url}")
        self.assertEqual(TrainerFeedback.objects.filter(subject=self.soft).count(), 1)

    def test_anonymous_and_trainer_are_refused(self):
        self.assert_blocked(APIClient(), expected=(401,))
        trainer = APIClient()
        trainer.force_authenticate(self.t_soft.user)
        self.assert_blocked(trainer, expected=(403,))

    def test_student_parent_account_is_refused(self):
        family = make_user("family", role=User.Role.STUDENT_PARENT)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(family).access_token}")
        self.assert_blocked(client, expected=(403,))
        direct = APIClient()  # even past the isolation middleware the view refuses
        direct.force_authenticate(family)
        self.assert_blocked(direct, expected=(403,))

    def test_staff_with_explicit_permission_may_copy(self):
        staff = make_user("ops", role=User.Role.OPERATIONS_DIRECTOR)
        client = APIClient()
        client.force_authenticate(staff)
        self.assertEqual(client.post(PREVIEW_URL, self.body(), format="json").status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="copy_scores"))
        staff = User.objects.get(pk=staff.pk)  # drop the permission cache
        client.force_authenticate(staff)
        self.assertEqual(client.post(PREVIEW_URL, self.body(), format="json").status_code, 200)
