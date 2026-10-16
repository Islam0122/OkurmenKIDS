"""Transferring a student to another group (POST students/<pk>/transfer/,
services.student_enrollment.transfer_student).

The student row is locked with SELECT ... FOR UPDATE. `Student.group` is
nullable, so locking together with select_related("group") (a LEFT OUTER
JOIN) failed on PostgreSQL with «FOR UPDATE cannot be applied to the
nullable side of an outer join» — SQLite ignores FOR UPDATE and never
showed it. Run with TEST_DATABASE_URL pointing at PostgreSQL to exercise
the real lock, including the concurrency tests at the bottom.
"""
from __future__ import annotations

import datetime as dt
import threading
from unittest import skipUnless

from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, Student, StudentStatusEvent
from apps.academy.services.student_enrollment import transfer_student
from apps.assistant.tests import PASSWORD, TODAY, AssistantTestBase
from apps.users.models import User

TRANSFERRED = StudentStatusEvent.EventType.TRANSFERRED


def transfers_of(student: Student):
    return StudentStatusEvent.objects.filter(student=student, event_type=TRANSFERRED)


class TransferApiTests(AssistantTestBase):
    def transfer(self, student, group_id, client=None, **extra):
        return (client or self.client).post(
            self.url("student-transfer", student.pk), {"group": group_id, **extra}, format="json"
        )

    def test_successful_transfer_persists_group_and_records_one_event(self):
        event_date = TODAY - dt.timedelta(days=3)
        response = self.transfer(self.s1, self.g2.pk, event_date=event_date.isoformat(), comment="  Время  ")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.s1.refresh_from_db()
        self.assertEqual(self.s1.group_id, self.g2.pk)
        self.assertEqual(self.s1.status, Student.Status.ACTIVE)  # a transfer is not a departure
        self.assertEqual(Student.objects.filter(first_name="Islam").count(), 1)  # same row, not re-created

        event = transfers_of(self.s1).get()
        self.assertEqual((event.from_group_id, event.group_id), (self.g1.pk, self.g2.pk))
        self.assertEqual(event.event_date, event_date)
        self.assertEqual(event.comment, "Время")
        self.assertEqual(event.performed_by, self.assistant)
        self.assertEqual(event.previous_status, Student.Status.ACTIVE)
        self.assertTrue(
            LogEntry.objects.filter(object_id=str(self.s1.pk), change_message__startswith="Перевод: PRO-01 → PRO-02")
            .exists()
        )

    def test_event_date_defaults_to_today(self):
        self.assertEqual(self.transfer(self.s1, self.g2.pk).status_code, status.HTTP_200_OK)
        self.assertEqual(transfers_of(self.s1).get().event_date, dt.date.today())

    def test_student_without_a_group_can_be_transferred(self):
        orphan = Student.objects.create(first_name="Nur", last_name="B", group=None)
        response = self.transfer(orphan, self.g2.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        orphan.refresh_from_db()
        self.assertEqual(orphan.group_id, self.g2.pk)
        event = transfers_of(orphan).get()
        self.assertIsNone(event.from_group_id)
        self.assertEqual(event.group_id, self.g2.pk)
        self.assertTrue(
            LogEntry.objects.filter(object_id=str(orphan.pk), change_message__startswith="Перевод: без группы → PRO-02")
            .exists()
        )

    def test_repeating_the_same_transfer_never_writes_a_second_event(self):
        self.assertEqual(self.transfer(self.s1, self.g2.pk).status_code, status.HTTP_200_OK)
        again = self.transfer(self.s1, self.g2.pk)
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(transfers_of(self.s1).count(), 1)

    def test_chained_transfers_keep_the_route(self):
        self.transfer(self.s1, self.g2.pk)
        self.transfer(self.s1, self.g1.pk)
        route = list(transfers_of(self.s1).order_by("pk").values_list("from_group_id", "group_id"))
        self.assertEqual(route, [(self.g1.pk, self.g2.pk), (self.g2.pk, self.g1.pk)])

    def test_invalid_destination_is_refused_and_nothing_changes(self):
        missing = Group.objects.order_by("-pk").first().pk + 100
        self.assertEqual(self.transfer(self.s1, missing).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.transfer(self.s1, None).status_code, status.HTTP_400_BAD_REQUEST)

        self.g2.status = Group.Status.CANCELLED
        self.g2.save()
        self.assertEqual(self.transfer(self.s1, self.g2.pk).status_code, status.HTTP_400_BAD_REQUEST)

        full = Group.objects.create(name="PRO-03", course=self.course, start_date=TODAY, max_students=1)
        Student.objects.create(first_name="Seat", last_name="Taken", group=full)
        self.assertEqual(self.transfer(self.s1, full.pk).status_code, status.HTTP_400_BAD_REQUEST)

        self.s1.refresh_from_db()
        self.assertEqual(self.s1.group_id, self.g1.pk)
        self.assertFalse(transfers_of(self.s1).exists())

    def test_withdrawn_student_is_not_transferred(self):
        Student.objects.filter(pk=self.s1.pk).update(status=Student.Status.WITHDRAWN, is_active=False)
        self.assertEqual(self.transfer(self.s1, self.g2.pk).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(transfers_of(self.s1).exists())

    def test_unknown_student_is_404(self):
        missing = Student.objects.order_by("-pk").first().pk + 100
        response = self.client.post(self.url("student-transfer", missing), {"group": self.g2.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_only_assistant_or_admin_may_transfer(self):
        lead = User.objects.create_user(username="lead", email="l@o.kg", password=PASSWORD, role=User.Role.TEAM_LEAD)
        for user in (self.islam.user, lead):
            client = APIClient()
            client.force_authenticate(user)
            self.assertEqual(self.transfer(self.s1, self.g2.pk, client=client).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.transfer(self.s1, self.g2.pk, client=APIClient()).status_code,
                         status.HTTP_401_UNAUTHORIZED)
        self.s1.refresh_from_db()
        self.assertEqual(self.s1.group_id, self.g1.pk)
        self.assertFalse(transfers_of(self.s1).exists())

        admin = User.objects.create_superuser(username="admin", email="a@o.kg", password=PASSWORD)
        client = APIClient()
        client.force_authenticate(admin)
        self.assertEqual(self.transfer(self.s1, self.g2.pk, client=client).status_code, status.HTTP_200_OK)


@skipUnless(connection.vendor == "postgresql", "needs real row locks and concurrent transactions (PostgreSQL)")
class TransferConcurrencyTests(TransactionTestCase):
    """Two requests transfer the same student at the same moment. A real
    TransactionTestCase: the rows must be committed for the other
    connections to see them."""

    def setUp(self):
        course = Course.objects.create(name="Prog", count_lesson=4)
        self.g1 = Group.objects.create(name="PRO-01", course=course, start_date=TODAY)
        self.g2 = Group.objects.create(name="PRO-02", course=course, start_date=TODAY)
        self.g3 = Group.objects.create(name="PRO-03", course=course, start_date=TODAY)
        self.student = Student.objects.create(first_name="Islam", last_name="D", group=self.g1)

    def race(self, *targets):
        barrier = threading.Barrier(len(targets))
        done, refused, errors = [], [], []

        def worker(group):
            try:
                barrier.wait(timeout=10)
                # Each thread starts from its own stale in-memory copy.
                done.append(transfer_student(Student.objects.get(pk=self.student.pk), group=group))
            except ValidationError as exc:
                refused.append(exc)
            except Exception as exc:  # e.g. the old NotSupportedError — surfaced below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(group,)) for group in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(errors, [])
        return done, refused

    def test_simultaneous_identical_transfers_write_one_event(self):
        done, refused = self.race(self.g2, self.g2)
        self.assertEqual((len(done), len(refused)), (1, 1))
        self.student.refresh_from_db()
        self.assertEqual(self.student.group_id, self.g2.pk)
        self.assertEqual(transfers_of(self.student).count(), 1)

    def test_simultaneous_transfers_to_different_groups_serialize(self):
        done, refused = self.race(self.g2, self.g3)
        self.assertEqual((len(done), len(refused)), (2, 0))
        route = list(transfers_of(self.student).order_by("pk").values_list("from_group_id", "group_id"))
        # The second transfer saw the first one's result under the lock:
        # the history is one unbroken chain ending at the current group.
        self.assertEqual(route[0][0], self.g1.pk)
        self.assertEqual(route[1][0], route[0][1])
        self.student.refresh_from_db()
        self.assertEqual(self.student.group_id, route[1][1])

    def test_student_without_a_group_on_postgresql(self):
        Student.objects.filter(pk=self.student.pk).update(group=None)
        done, refused = self.race(self.g2)
        self.assertEqual((len(done), len(refused)), (1, 0))
        self.assertIsNone(done[0].from_group_id)
