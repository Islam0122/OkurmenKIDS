"""Bulk copy of attendance / homework results / scores (apps.bulk_copy).

Absolute imports only — full test discovery also imports modules under the
`backend.` prefix (see apps/academy/tests.py)."""
from __future__ import annotations

import datetime as dt
import itertools
import uuid
from unittest import mock

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.academy.models import Attendance, Course, Group, Homework, HomeworkResult, Lesson, Student
from apps.attendance_matrix.models import AttendanceChangeLog
from apps.bulk_copy.models import BulkCopyItem, BulkCopyOperation
from apps.bulk_copy.services import engine
from apps.users.models import Subject, Teacher, User

URL = "/api/v1/bulk-copy/operations/"
PREVIEW = f"{URL}preview/"
SEP = dt.date(2026, 9, 1)
_n = itertools.count(1)
P, A, L, E = (Attendance.Status.PRESENT, Attendance.Status.ABSENT, Attendance.Status.LATE, Attendance.Status.EXCUSED)


def user(username, role=User.Role.TEACHER, **extra) -> User:
    return User.objects.create_user(username=username, email=f"{username}@example.kg", password="Str0ng-pass!",
                                    first_name=username.capitalize(), role=role, is_verified=True, **extra)


def teacher(username) -> Teacher:
    return Teacher.objects.create(user=user(username))


class Fixture(TestCase):
    """Group A: IT lessons L1 (1 Sep), L2 (8 Sep); Soft Skills M1 (2 Sep), M2 (9 Sep), M3 (16 Sep).

    Attendance  L1: s1 present «молодец», s2 excused «болел», s3 absent
                L2: s1 late, s2 —, s3 present
    Target M1 already has s3 present.
    Homework    H1 on L1 → T1 on M1. H1 results: s1 checked 9 «хорошо», s2 submitted (no score).
    """

    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", email="a@example.kg", password="Str0ng-pass!")
        self.it = Subject.objects.get_or_create(name="IT")[0]
        self.soft = Subject.objects.get_or_create(name="Soft Skills")[0]
        self.t_it, self.t_soft = teacher("islam"), teacher("aijan")
        course = Course.objects.create(name="Prog SOFT", count_lesson=48)
        course.subjects.set([self.it, self.soft])
        self.group = Group.objects.create(name="Prog SOFT 1", course=course, start_date=dt.date(2026, 1, 10))
        self.group_b = Group.objects.create(name="Prog SOFT 2", course=course, start_date=dt.date(2026, 1, 10))
        self.s1, self.s2, self.s3 = (Student.objects.create(first_name=n, last_name="Test", group=self.group,
                                                            enrollment_date=dt.date(2026, 8, 1)) for n in ("Aibek", "Bekzat", "Chyngyz"))
        self.L1, self.L2 = self.lesson(self.it, self.t_it, 0), self.lesson(self.it, self.t_it, 7)
        self.M1, self.M2, self.M3 = (self.lesson(self.soft, self.t_soft, d) for d in (1, 8, 15))
        self.mark(self.L1, self.s1, P, comment="молодец")
        self.mark(self.L1, self.s2, E, reason="болел")
        self.mark(self.L1, self.s3, A)
        self.mark(self.L2, self.s1, L)
        self.mark(self.L2, self.s3, P)
        self.existing = self.mark(self.M1, self.s3, P, comment="был активен")
        self.H1 = Homework.objects.create(lesson=self.L1, title="Функции")
        self.T1 = Homework.objects.create(lesson=self.M1, title="Эссе")
        now = timezone.now()
        HomeworkResult.objects.create(homework=self.H1, student=self.s1, status=HomeworkResult.Status.CHECKED, score=9,
                                      comment="хорошо", submitted_at=now, checked_at=now)
        HomeworkResult.objects.create(homework=self.H1, student=self.s2, status=HomeworkResult.Status.SUBMITTED, submitted_at=now)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def lesson(self, subject, t, days, group=None, **extra) -> Lesson:
        return Lesson.objects.create(group=group or self.group, teacher=t, subject=subject, lesson_number=next(_n),
                                     date=extra.pop("date", SEP + dt.timedelta(days=days)), start_time=dt.time(10),
                                     end_time=dt.time(11),
                                     status=extra.pop("status", Lesson.Status.COMPLETED), **extra)

    def mark(self, lesson, student, status, comment="", reason="") -> Attendance:
        return Attendance.objects.create(lesson=lesson, student=student, status=status, comment=comment, excuse_reason=reason)

    def body(self, **extra) -> dict:
        data = {"source_group": self.group.pk, "source_subject": self.it.pk, "source_start": "2026-09-01",
                "source_end": "2026-09-30", "target_group": self.group.pk, "target_subject": self.soft.pk,
                "target_start": "2026-09-01", "target_end": "2026-09-30", "categories": ["attendance"]}
        data.update(extra)
        return data

    def preview(self, **extra) -> dict:
        response = self.client.post(PREVIEW, self.body(**extra), format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def apply(self, expect=201, preview=None, **extra):
        preview = preview or self.preview(**extra)
        payload = self.body(fingerprint=preview["fingerprint"], operation_id=str(uuid.uuid4()), **extra)
        response = self.client.post(URL, payload, format="json")
        self.assertEqual(response.status_code, expect, response.content)
        return response

    def att(self, lesson, student):
        return Attendance.objects.filter(lesson=lesson, student=student).first()

    def actions(self, data, kind="attendance") -> dict:
        return {(r["pair"], r["student"]): r["action"] for r in data["records"] if r["kind"] == kind}


class PreviewTests(Fixture):
    def test_suggested_mapping_and_counts(self):
        data = self.preview()
        self.assertEqual([(p["source"], p["target"]) for p in data["pairs"]], [(self.L1.pk, self.M1.pk), (self.L2.pk, self.M2.pk)])
        acts = self.actions(data)
        self.assertEqual(acts[(0, self.s1.pk)], engine.CREATE)
        self.assertEqual(acts[(0, self.s2.pk)], engine.CREATE)
        self.assertEqual(acts[(0, self.s3.pk)], engine.SKIP_EXISTING)
        self.assertEqual(acts[(1, self.s2.pk)], engine.EMPTY)
        s = data["summary"]
        self.assertEqual((s["students_matched"], s["to_copy"], s["empty"], s["existing_target"], s["overwrite"]), (3, 4, 1, 1, 0))
        self.assertEqual(s["billing_lessons"], 2)
        self.assertEqual(Attendance.objects.filter(lesson__subject=self.soft).count(), 1, "preview never writes")

    def test_invalid_mappings_are_reported_and_skipped(self):
        future = self.lesson(self.soft, self.t_soft, 0, date=timezone.localdate() + dt.timedelta(days=3),
                             status=Lesson.Status.SCHEDULED)
        L3, L4 = self.lesson(self.it, self.t_it, 20), self.lesson(self.it, self.t_it, 21)
        data = self.preview(target_end=(timezone.localdate() + dt.timedelta(days=10)).isoformat(), lesson_map=[
            {"source": self.L1.pk, "target": self.M3.pk},       # valid manual mapping
            {"source": self.L2.pk, "target": self.M3.pk},       # target used twice
            {"source": L3.pk, "target": self.L1.pk},            # target outside the target subject
            {"source": L4.pk, "target": future.pk},             # not held yet
        ])
        problems = [p["problem"] for p in data["pairs"]]
        self.assertIsNone(problems[0])
        self.assertIn("уже выбрано", problems[1])
        self.assertIn("не входит", problems[2])
        self.assertIn("ещё не прошло", problems[3])
        self.assertEqual(data["summary"]["invalid_pairs"], 3)
        self.assertEqual({r["pair"] for r in data["records"]}, {0})

    def test_homework_pairs_need_matching_assignments(self):
        Homework.objects.create(lesson=self.M1, title="Второе")
        data = self.preview(categories=["homework"])
        self.assertIn("Разное число", data["pairs"][0]["homework_problem"])
        self.assertEqual(data["summary"]["to_copy"], 0)


class AttendanceCopyTests(Fixture):
    def test_attendance_only_copies_status_and_reason_matching_by_id(self):
        response = self.apply()
        self.assertEqual(self.att(self.M1, self.s1).status, P)
        self.assertEqual(self.att(self.M1, self.s1).comment, "", "comments only on request")
        self.assertEqual((self.att(self.M1, self.s2).status, self.att(self.M1, self.s2).excuse_reason), (E, "болел"))
        self.assertEqual(self.att(self.M1, self.s3).comment, "был активен", "existing record preserved")
        self.assertEqual(self.att(self.M2, self.s1).status, L)
        self.assertIsNone(self.att(self.M2, self.s2), "an empty source never creates or deletes")
        self.assertEqual(HomeworkResult.objects.filter(homework=self.T1).count(), 0, "attendance only")
        op = BulkCopyOperation.objects.get()
        self.assertEqual((op.copied_count, op.overwritten_count, op.created_by), (4, 0, self.admin))
        self.assertEqual(op.skipped_details, {engine.SKIP_EXISTING: 1, engine.EMPTY: 1})
        self.assertEqual(response.data["operation_id"], str(op.operation_id))
        log = AttendanceChangeLog.objects.get(lesson=self.M1, student=self.s1)
        self.assertEqual(log.changes["attendance"], [None, P])
        self.assertEqual(log.actor, self.admin)

    def test_overwrite_needs_confirmation_and_is_audited(self):
        preview = self.preview(conflict="overwrite")
        payload = self.body(conflict="overwrite", fingerprint=preview["fingerprint"], operation_id=str(uuid.uuid4()))
        self.assertEqual(self.client.post(URL, payload, format="json").status_code, 428)
        self.assertEqual(self.att(self.M1, self.s3).status, P)
        payload["confirm_overwrite"] = True
        self.assertEqual(self.client.post(URL, payload, format="json").status_code, 201)
        self.assertEqual(self.att(self.M1, self.s3).status, A)
        self.assertEqual(self.att(self.M1, self.s3).comment, "был активен", "comment kept without «copy comments»")
        item = BulkCopyItem.objects.get(action=BulkCopyItem.Action.OVERWRITTEN)
        self.assertEqual((item.before["status"], item.after["status"]), (P, A))

    def test_copy_comments_and_skip_empty(self):
        Attendance.objects.filter(pk=self.existing.pk).update(status=A)  # equals the source status
        # Source comment of s3 on L1 is empty: kept with skip_empty …
        data = self.preview(conflict="overwrite", copy_comments=True)
        self.assertEqual(self.actions(data)[(0, self.s3.pk)], engine.UNCHANGED)
        # … and cleared without it.
        self.apply(conflict="overwrite", copy_comments=True, skip_empty=False, confirm_overwrite=True)
        self.assertEqual(self.att(self.M1, self.s3).comment, "")
        self.assertEqual(self.att(self.M1, self.s1).comment, "молодец")

    def test_same_group_same_subject_other_lessons(self):
        self.apply(target_subject=self.it.pk, lesson_map=[{"source": self.L1.pk, "target": self.L2.pk}], conflict="overwrite",
                   confirm_overwrite=True)
        self.assertEqual(self.att(self.L2, self.s1).status, P)
        self.assertEqual(self.att(self.L2, self.s2).status, E)

    def test_cross_group_matches_by_id_and_lists_unmatched(self):
        other = Student.objects.create(first_name="Dana", last_name="B", group=self.group_b, enrollment_date=SEP)
        moved = Student.objects.create(first_name="Erlan", last_name="B", group=self.group_b, enrollment_date=SEP)
        lb = self.lesson(self.it, self.t_it, 2, group=self.group_b)
        self.mark(lb, other, P)
        self.mark(lb, moved, L)
        Student.objects.filter(pk=moved.pk).update(group=self.group)  # moved to group A since
        data = self.preview(source_group=self.group_b.pk, lesson_map=[{"source": lb.pk, "target": self.M2.pk}])
        status = {s["id"]: s["status"] for s in data["students"]}
        self.assertEqual(status[other.pk], "not_in_target_group")
        self.assertEqual(status[moved.pk], "matched")
        self.assertEqual(status[self.s1.pk], "no_source_records")
        self.apply(preview=data, source_group=self.group_b.pk, lesson_map=[{"source": lb.pk, "target": self.M2.pk}])
        self.assertEqual(self.att(self.M2, moved).status, L)
        self.assertIsNone(self.att(self.M2, other))

    def test_selected_students(self):
        self.apply(mode="selected", student_ids=[self.s2.pk])
        self.assertIsNotNone(self.att(self.M1, self.s2))
        self.assertIsNone(self.att(self.M1, self.s1))


class HomeworkAndScoreTests(Fixture):
    def result(self, student):
        return HomeworkResult.objects.filter(homework=self.T1, student=student).first()

    def test_homework_only_copies_status_not_score(self):
        self.apply(categories=["homework"])
        r1 = self.result(self.s1)
        self.assertEqual((r1.status, r1.score, r1.comment), (HomeworkResult.Status.CHECKED, None, ""))
        self.assertIsNotNone(r1.checked_at)
        self.assertEqual(self.result(self.s2).status, HomeworkResult.Status.SUBMITTED)
        self.assertFalse(Attendance.objects.filter(lesson=self.M1, student=self.s1).exists())

    def test_scores_only_overwrites_the_score(self):
        HomeworkResult.objects.create(homework=self.T1, student=self.s1, status=HomeworkResult.Status.CHECKED, score=5,
                                      comment="своё")
        self.apply(categories=["scores"], conflict="overwrite", confirm_overwrite=True)
        r1 = self.result(self.s1)
        self.assertEqual((r1.score, r1.comment), (9, "своё"))
        # A result created for a score keeps the source status (a score never exists alone).
        self.assertEqual(self.result(self.s2).status, HomeworkResult.Status.SUBMITTED)

    def test_full_copy_with_comments(self):
        self.apply(categories=["attendance", "homework", "scores"], copy_comments=True)
        r1 = self.result(self.s1)
        self.assertEqual((r1.status, r1.score, r1.comment), (HomeworkResult.Status.CHECKED, 9, "хорошо"))
        self.assertEqual(self.att(self.M1, self.s1).comment, "молодец")
        op = BulkCopyOperation.objects.get()
        self.assertEqual(sorted(op.categories), ["attendance", "homework", "scores"])
        self.assertEqual(op.items.filter(kind=BulkCopyItem.Kind.HOMEWORK_RESULT).count(), 2)


class SafetyTests(Fixture):
    def test_stale_preview_is_refused(self):
        preview = self.preview()
        Attendance.objects.filter(lesson=self.L1, student=self.s1).update(status=A)
        self.assertEqual(self.apply(expect=409, preview=preview).data["code"], "conflict")
        self.assertIsNone(self.att(self.M1, self.s1))

    def test_operation_id_is_idempotent(self):
        preview = self.preview()
        payload = self.body(fingerprint=preview["fingerprint"], operation_id=str(uuid.uuid4()))
        first, second = (self.client.post(URL, payload, format="json") for _ in range(2))
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertTrue(second.data["replayed"])
        self.assertEqual(BulkCopyOperation.objects.count(), 1)

    def test_repeated_copy_changes_nothing(self):
        self.apply()
        again = self.preview()
        self.assertEqual(again["summary"]["to_copy"], 0)
        self.assertEqual(self.apply(expect=400, preview=again).data["detail"][:13], "Нечего копиро")

    def test_error_rolls_back_everything(self):
        real = engine._write_attendance
        calls = itertools.count(1)

        def flaky(rec, u):
            if next(calls) == 3:
                raise ValidationError("сбой записи")
            return real(rec, u)

        with mock.patch.object(engine, "_write_attendance", side_effect=flaky):
            response = self.apply(expect=400)
        self.assertIn("сбой записи", response.data["detail"])
        self.assertEqual(Attendance.objects.filter(lesson__subject=self.soft).count(), 1, "first writes rolled back")
        self.assertFalse(AttendanceChangeLog.objects.exists())
        op = BulkCopyOperation.objects.get()
        self.assertEqual(op.status, BulkCopyOperation.Status.FAILED)
        self.assertFalse(op.items.exists())


class UndoTests(Fixture):
    def test_undo_restores_deletes_and_resyncs_billing(self):
        op_id = self.apply(categories=["attendance", "scores"], conflict="overwrite", confirm_overwrite=True).data["id"]
        with mock.patch("apps.billing.services.lessons.sync_lesson_safely") as sync, \
                self.captureOnCommitCallbacks(execute=True):
            data = self.client.post(f"{URL}{op_id}/undo/").data
        self.assertEqual(data["status"], BulkCopyOperation.Status.REVERTED)
        self.assertEqual(self.att(self.M1, self.s3).status, P, "overwritten mark restored")
        self.assertIsNone(self.att(self.M1, self.s1), "created mark removed")
        self.assertFalse(HomeworkResult.objects.filter(homework=self.T1).exists())
        self.assertEqual({c.args[0] for c in sync.call_args_list}, {self.M1.pk, self.M2.pk})
        self.assertEqual(self.client.post(f"{URL}{op_id}/undo/").status_code, 409)

    def test_undo_keeps_later_manual_changes(self):
        op_id = self.apply().data["id"]
        Attendance.objects.filter(lesson=self.M1, student=self.s1).update(status=L)
        data = self.client.post(f"{URL}{op_id}/undo/").data
        self.assertEqual(data["status"], BulkCopyOperation.Status.PARTIALLY_REVERTED)
        self.assertEqual(self.att(self.M1, self.s1).status, L)
        self.assertIsNone(self.att(self.M1, self.s2))
        undo = {i["student"]: i["undo_result"] for i in data["items"] if i["target_lesson"]["id"] == self.M1.pk}
        self.assertEqual(undo[self.s1.pk], BulkCopyItem.UndoResult.SKIPPED_CHANGED)


class PermissionTests(Fixture):
    def blocked(self, client, codes):
        for method, url in (("get", URL), ("get", f"{URL}options/"), ("post", PREVIEW), ("post", URL)):
            self.assertIn(getattr(client, method)(url, self.body(), format="json").status_code, codes, url)

    def test_anonymous_trainer_and_portal_are_refused(self):
        self.blocked(APIClient(), (401,))
        trainer = APIClient()
        trainer.force_authenticate(self.t_soft.user)
        self.blocked(trainer, (403,))
        family = user("family", role=User.Role.STUDENT_PARENT)
        portal = APIClient()
        portal.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(family).access_token}")
        self.blocked(portal, (403,))
        family.user_permissions.add(Permission.objects.get(codename="run_bulk_copy"))
        direct = APIClient()
        direct.force_authenticate(User.objects.get(pk=family.pk))
        self.blocked(direct, (403,))
        self.assertEqual(Attendance.objects.filter(lesson__subject=self.soft).count(), 1)

    def test_permitted_trainer_is_limited_to_own_lessons(self):
        t = self.t_soft.user
        t.user_permissions.add(Permission.objects.get(codename="run_bulk_copy"))
        client = APIClient()
        client.force_authenticate(User.objects.get(pk=t.pk))
        # Source IT lessons are taught by someone else but the group is visible; targets are her own.
        response = client.post(PREVIEW, self.body(), format="json")
        self.assertEqual(response.status_code, 200, response.content)  # she teaches this group
        self.assertTrue(all(p["valid"] for p in response.data["pairs"]))
        # Copying INTO the IT trainer's lessons is refused per pair.
        data = client.post(PREVIEW, self.body(target_subject=self.it.pk, lesson_map=[{"source": self.M1.pk, "target": self.L2.pk}],
                                              source_subject=self.soft.pk), format="json").data
        self.assertFalse(data["pairs"][0]["valid"])
        self.assertIn("свои", data["pairs"][0]["problem"])
