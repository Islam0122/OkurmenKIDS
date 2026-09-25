from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.academy.models import Attendance, HomeworkResult, Lesson, Student, StudentStatusEvent
from apps.scholarships.models import EligibilityStatus, SubjectAggregation
from apps.scholarships.services.generation import ScholarshipError

from .base import OCT_1, SEP_1, ScholarshipFixture

D = Decimal
FULL = (5, 5, 5, 5)


class EligibilityTests(ScholarshipFixture):
    def test_new_student_has_no_completed_period(self):
        new = self.student("New", enrolled=dt.date(2026, 9, 10))
        self.study(new, self.python, self.t_python)
        ev = self.evaluation(self.generate(), new)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.NOT_FULL_PERIOD)
        self.assertIsNone(ev.rank)
        self.assertFalse(self.generate().awards.filter(student=new).exists())

    def test_student_becomes_eligible_after_first_full_period(self):
        # Enrolled Sep 10: September is partial, October is the first full period.
        student = self.student(enrolled=dt.date(2026, 9, 10))
        lesson = self.lesson(self.python, self.t_python, dt.date(2026, 10, 5))
        self.attend(student, lesson)
        self.configure(require_complete_feedback=False)
        ev = self.evaluation(self.generate(dt.date(2026, 11, 1)), student)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.ELIGIBLE)
        self.assertEqual(ev.period.period_start, dt.date(2026, 10, 1))

    def test_enrollment_on_the_first_day_of_the_period_is_eligible(self):
        student = self.student(enrolled=SEP_1)
        self.study(student, self.python, self.t_python)
        period = self.generate_with_feedback([(student, self.python, self.t_python, FULL)])
        self.assertEqual(self.evaluation(period, student).eligibility_status, EligibilityStatus.ELIGIBLE)

    def test_students_with_different_start_dates(self):
        early = self.student("Early", enrolled=dt.date(2026, 3, 1))
        boundary = self.student("Boundary", enrolled=dt.date(2026, 9, 1))
        late = self.student("Late", enrolled=dt.date(2026, 9, 2))
        for s in (early, boundary, late):
            self.study(s, self.python, self.t_python)
        period = self.generate_with_feedback([(s, self.python, self.t_python, FULL) for s in (early, boundary, late)])
        statuses = {ev.student_id: ev.eligibility_status for ev in period.evaluations.all()}
        self.assertEqual(statuses[early.id], EligibilityStatus.ELIGIBLE)
        self.assertEqual(statuses[boundary.id], EligibilityStatus.ELIGIBLE)
        self.assertEqual(statuses[late.id], EligibilityStatus.NOT_FULL_PERIOD)

    def test_current_incomplete_month_is_never_evaluated(self):
        with self.assertRaises(ScholarshipError):
            self.generate(dt.date(2026, 11, 1), today=dt.date(2026, 10, 20))
        # Mid-October, the latest completed monthly period is September.
        period = self.generate(OCT_1, today=dt.date(2026, 10, 20))
        self.assertEqual((period.period_start, period.period_end), (SEP_1, dt.date(2026, 9, 30)))

    def test_october_lessons_do_not_leak_into_september(self):
        student = self.student()
        self.study(student, self.python, self.t_python, attended=2)
        self.attend(student, self.lesson(self.python, self.t_python, OCT_1), Attendance.Status.ABSENT)
        self.attend(student, self.lesson(self.python, self.t_python, dt.date(2026, 8, 31)), Attendance.Status.ABSENT)
        period = self.generate_with_feedback([(student, self.python, self.t_python, FULL)])
        self.assertEqual(self.evaluation(period, student).attendance_score, D("100.00"))

    def test_missing_enrollment_date_is_incomplete_data(self):
        student = self.student(enrolled=None)
        self.study(student, self.python, self.t_python)
        ev = self.evaluation(self.generate(), student)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.INCOMPLETE_DATA)
        self.assertIn("дата начала", ev.ineligibility_reason)

    def test_paused_during_period_is_inactive(self):
        student = self.student()
        self.study(student, self.python, self.t_python)
        StudentStatusEvent.objects.create(
            student=student, event_type=StudentStatusEvent.EventType.PAUSED, reason="health",
            event_date=dt.date(2026, 9, 20),
        )
        StudentStatusEvent.objects.create(
            student=student, event_type=StudentStatusEvent.EventType.CONTINUED, event_date=dt.date(2026, 9, 25),
        )
        ev = self.evaluation(self.generate(), student)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.INACTIVE)

    def test_withdrawn_student_is_listed_as_inactive(self):
        student = self.student(status=Student.Status.WITHDRAWN, is_active=False)
        self.study(student, self.python, self.t_python)
        ev = self.evaluation(self.generate(), student)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.INACTIVE)

    def test_reactivated_mid_period_did_not_study_the_full_period(self):
        student = self.student()
        self.study(student, self.python, self.t_python)
        StudentStatusEvent.objects.create(
            student=student, event_type=StudentStatusEvent.EventType.REACTIVATED, event_date=dt.date(2026, 9, 12),
        )
        self.assertEqual(self.evaluation(self.generate(), student).eligibility_status, EligibilityStatus.NOT_FULL_PERIOD)

    def test_active_student_without_lessons_is_no_data(self):
        student = self.student()
        ev = self.evaluation(self.generate(), student)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.NO_DATA)
        self.assertIsNone(ev.overall_score)

    def test_minimum_marked_lessons(self):
        self.configure(min_marked_lessons=3, require_complete_feedback=False)
        student = self.student()
        self.study(student, self.python, self.t_python, attended=2)
        self.assertEqual(self.evaluation(self.generate(), student).eligibility_status, EligibilityStatus.NO_DATA)

    def test_minimum_score_threshold(self):
        self.configure(min_overall_score=D("80"), require_complete_feedback=False)
        student = self.student()
        self.study(student, self.python, self.t_python, attended=1, missed=3)
        self.assertEqual(self.evaluation(self.generate(), student).eligibility_status, EligibilityStatus.BELOW_THRESHOLD)


class ComponentScoreTests(ScholarshipFixture):
    def test_attendance_late_counts_excused_is_excluded(self):
        self.configure(require_complete_feedback=False)
        student = self.student()
        statuses = [Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.ABSENT, Attendance.Status.EXCUSED]
        for index, status in enumerate(statuses):
            self.attend(student, self.lesson(self.python, self.t_python, SEP_1 + dt.timedelta(days=index)), status)
        ev = self.evaluation(self.generate(), student)
        row = ev.subject_scores.get()
        self.assertEqual((row.lessons_attended, row.lessons_missed, row.lessons_excused), (2, 1, 1))
        self.assertEqual(ev.attendance_score, D("66.67"))  # 2/3, ROUND_HALF_UP

    def test_cancelled_lessons_are_excluded(self):
        self.configure(require_complete_feedback=False)
        student = self.student()
        self.attend(student, self.lesson(self.python, self.t_python, SEP_1))
        cancelled = self.lesson(self.python, self.t_python, dt.date(2026, 9, 2), status=Lesson.Status.CANCELLED)
        self.attend(student, cancelled, Attendance.Status.ABSENT)
        self.assertEqual(self.evaluation(self.generate(), student).attendance_score, D("100.00"))

    def test_homework_completion_partial_credit_and_missing_results(self):
        self.configure(require_complete_feedback=False)
        student = self.student()
        lessons = [self.lesson(self.python, self.t_python, SEP_1 + dt.timedelta(days=i)) for i in range(4)]
        for lesson in lessons:
            self.attend(student, lesson)
        hws = [self.homework(lesson) for lesson in lessons]
        self.hw_result(hws[0], student, HomeworkResult.Status.CHECKED)
        self.hw_result(hws[1], student, HomeworkResult.Status.LATE)  # 0.5 credit
        self.hw_result(hws[2], student, HomeworkResult.Status.NOT_SUBMITTED)
        # hws[3] has no result row at all -> 0 and a warning
        ev = self.evaluation(self.generate(), student)
        self.assertEqual(ev.homework_score, D("37.50"))  # 1.5 / 4
        self.assertTrue(any("без результата" in w for w in ev.data_warnings))

    def test_homework_not_required_and_excused_lessons_are_not_counted(self):
        self.configure(require_complete_feedback=False)
        student = self.student()
        free = self.lesson(self.python, self.t_python, SEP_1, homework_not_required=True)
        excused = self.lesson(self.python, self.t_python, dt.date(2026, 9, 2))
        normal = self.lesson(self.python, self.t_python, dt.date(2026, 9, 3))
        self.attend(student, free)
        self.attend(student, excused, Attendance.Status.EXCUSED)
        self.attend(student, normal)
        for lesson in (free, excused):
            self.homework(lesson)
        self.hw_result(self.homework(normal), student)
        row = self.evaluation(self.generate(), student).subject_scores.get()
        self.assertEqual((row.homework_required, row.homework_score), (1, D("100.00")))

    def test_feedback_scale(self):
        student = self.student()
        self.study(student, self.python, self.t_python)
        period = self.generate_with_feedback([(student, self.python, self.t_python, (4, 4, 5, 5))])
        self.assertEqual(self.evaluation(period, student).feedback_score, D("90.00"))

    def test_weighted_overall_score(self):
        student = self.student()
        # attendance 3/4 = 75, homework 1/2 = 50, feedback (3,3,3,3) = 60
        self.study(student, self.python, self.t_python, attended=3, missed=1, homework_total=2, homework_done=1)
        period = self.generate_with_feedback([(student, self.python, self.t_python, (3, 3, 3, 3))])
        ev = self.evaluation(period, student)
        self.assertEqual((ev.attendance_score, ev.homework_score, ev.feedback_score), (D("75.00"), D("50.00"), D("60.00")))
        self.assertEqual(ev.overall_score, D("63.00"))  # 75*.4 + 50*.3 + 60*.3

    def test_configurable_weights_are_snapshotted(self):
        self.configure(attendance_weight=D("0.50"), homework_weight=D("0.25"), feedback_weight=D("0.25"))
        student = self.student()
        self.study(student, self.python, self.t_python, attended=3, missed=1, homework_total=2, homework_done=1)
        period = self.generate_with_feedback([(student, self.python, self.t_python, (3, 3, 3, 3))])
        self.assertEqual(self.evaluation(period, student).overall_score, D("65.00"))  # 37.5 + 12.5 + 15
        # Changing the configuration later does not rewrite the period.
        self.configure(attendance_weight=D("0.40"), homework_weight=D("0.30"), feedback_weight=D("0.30"))
        period.refresh_from_db()
        from apps.scholarships.services.generation import recalculate_period

        recalculate_period(period)
        self.assertEqual(self.evaluation(period, student).overall_score, D("65.00"))

    def test_weights_must_total_one(self):
        self.config.homework_weight = D("0.40")
        with self.assertRaises(ValidationError):
            self.config.full_clean()

    def test_missing_feedback_is_never_a_perfect_score(self):
        self.configure(require_complete_feedback=False)
        student = self.student()
        self.study(student, self.python, self.t_python, homework_total=1)
        ev = self.evaluation(self.generate(), student)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.ELIGIBLE)
        self.assertEqual(ev.feedback_score, D("0.00"))
        self.assertEqual(ev.overall_score, D("70.00"))  # 100*.4 + 100*.3 + 0*.3

    def test_missing_feedback_makes_student_incomplete_when_required(self):
        student = self.student()
        self.study(student, self.python, self.t_python)
        ev = self.evaluation(self.generate(), student)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.INCOMPLETE_DATA)
        self.assertIn("Python", ev.ineligibility_reason)


class MultiSubjectTests(ScholarshipFixture):
    def test_one_subject(self):
        student = self.student()
        self.study(student, self.python, self.t_python, homework_total=2)
        period = self.generate_with_feedback([(student, self.python, self.t_python, FULL)])
        ev = self.evaluation(period, student)
        self.assertEqual((ev.subjects_count, ev.overall_score), (1, D("100.00")))

    def test_two_subjects_equal_weighting(self):
        student = self.student()
        self.study(student, self.python, self.t_python, attended=4, homework_total=1)  # 100
        self.study(student, self.english, self.t_english, attended=1, missed=1, homework_total=1)  # att 50
        period = self.generate_with_feedback([
            (student, self.python, self.t_python, FULL),
            (student, self.english, self.t_english, FULL),
        ])
        ev = self.evaluation(period, student)
        english = ev.subject_scores.get(subject=self.english)
        self.assertEqual(english.subject_score, D("80.00"))  # 50*.4 + 100*.3 + 100*.3
        self.assertEqual(ev.subjects_count, 2)
        self.assertEqual(ev.overall_score, D("90.00"))  # (100 + 80) / 2
        self.assertEqual(ev.attendance_score, D("75.00"))  # (100 + 50) / 2

    def test_three_subjects_are_all_included(self):
        student = self.student()
        self.study(student, self.python, self.t_python, homework_total=1)
        self.study(student, self.cyber, self.t_cyber, attended=2, missed=2, homework_total=1)
        self.study(student, self.english, self.t_english, homework_total=1)
        period = self.generate_with_feedback([
            (student, self.python, self.t_python, FULL),
            (student, self.cyber, self.t_cyber, FULL),
            (student, self.english, self.t_english, FULL),
        ])
        ev = self.evaluation(period, student)
        self.assertEqual(
            sorted(ev.subject_scores.values_list("subject_name", flat=True)), ["CyberSecurity", "English", "Python"]
        )
        # Cyber: 50*.4 + 100*.3 + 100*.3 = 80
        self.assertEqual(ev.overall_score, D("93.33"))  # (100 + 80 + 100) / 3

    def test_missing_feedback_in_one_of_three_subjects_blocks_the_award(self):
        student = self.student()
        for subject, teacher in ((self.python, self.t_python), (self.cyber, self.t_cyber), (self.english, self.t_english)):
            self.study(student, subject, teacher)
        period = self.generate_with_feedback([
            (student, self.python, self.t_python, FULL),
            (student, self.english, self.t_english, FULL),
        ])
        ev = self.evaluation(period, student)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.INCOMPLETE_DATA)
        self.assertIn("CyberSecurity", ev.ineligibility_reason)

    def test_lesson_weighted_aggregation(self):
        self.configure(subject_aggregation=SubjectAggregation.LESSON_WEIGHTED)
        student = self.student()
        self.study(student, self.python, self.t_python, attended=6, homework_total=1)  # 100, 6 lessons
        self.study(student, self.english, self.t_english, attended=1, missed=1, homework_total=1)  # 80, 2 lessons
        period = self.generate_with_feedback([
            (student, self.python, self.t_python, FULL),
            (student, self.english, self.t_english, FULL),
        ])
        self.assertEqual(self.evaluation(period, student).overall_score, D("95.00"))  # (600 + 160) / 8

    def test_fewer_subjects_are_not_an_advantage(self):
        one = self.student("One")
        three = self.student("Three")
        self.study(one, self.python, self.t_python, homework_total=1)
        for subject, teacher in ((self.python, self.t_python), (self.cyber, self.t_cyber), (self.english, self.t_english)):
            self.study(three, subject, teacher, homework_total=1)
        rows = [(one, self.python, self.t_python, FULL)] + [
            (three, s, t, FULL) for s, t in ((self.python, self.t_python), (self.cyber, self.t_cyber), (self.english, self.t_english))
        ]
        period = self.generate_with_feedback(rows)
        self.assertEqual(self.evaluation(period, one).overall_score, self.evaluation(period, three).overall_score)

    def test_subject_without_homework_is_renormalised(self):
        student = self.student()
        self.study(student, self.english, self.t_english, attended=1, missed=1)  # no homework
        period = self.generate_with_feedback([(student, self.english, self.t_english, FULL)])
        row = self.evaluation(period, student).subject_scores.get()
        self.assertIsNone(row.homework_score)
        # (50*.4 + 100*.3) / .7 = 71.43
        self.assertEqual(row.subject_score, D("71.43"))

    def test_subject_with_only_excused_lessons_is_shown_but_not_counted(self):
        student = self.student()
        self.study(student, self.python, self.t_python)
        self.attend(student, self.lesson(self.english, self.t_english, SEP_1), Attendance.Status.EXCUSED)
        period = self.generate_with_feedback([(student, self.python, self.t_python, FULL)])
        ev = self.evaluation(period, student)
        english = ev.subject_scores.get(subject=self.english)
        self.assertEqual(english.aggregation_weight, 0)
        self.assertEqual(ev.subjects_count, 1)
        self.assertEqual(ev.eligibility_status, EligibilityStatus.ELIGIBLE)
        self.assertTrue(any("English" in w and "не учитывается" in w for w in ev.data_warnings))

    def test_student_changing_groups_keeps_lessons_from_both(self):
        student = self.student(group=self.other_group)
        self.study(student, self.python, self.t_python, attended=2, group=self.other_group)
        student.group = self.group
        student.save()
        self.study(student, self.cyber, self.t_cyber, attended=1, missed=1)
        period = self.generate_with_feedback([
            (student, self.python, self.t_python, FULL),
            (student, self.cyber, self.t_cyber, FULL),
        ])
        ev = self.evaluation(period, student)
        self.assertEqual(ev.lessons_count, 4)
        self.assertEqual(ev.subjects_count, 2)
        self.assertEqual(ev.group_name, self.group.name)

    def test_multiple_trainers_for_one_subject_are_averaged(self):
        second = self.t_cyber
        student = self.student()
        self.study(student, self.python, self.t_python, attended=2)
        self.attend(student, self.lesson(self.python, second, dt.date(2026, 9, 20)))
        period = self.generate_with_feedback([
            (student, self.python, self.t_python, (5, 5, 5, 5)),
            (student, self.python, second, (3, 3, 3, 3)),
        ])
        row = self.evaluation(period, student).subject_scores.get()
        self.assertEqual((row.feedback_expected, row.feedback_received, row.feedback_score), (2, 2, D("80.00")))

    def test_unmarked_lessons_are_warnings_not_absences(self):
        student = self.student()
        self.study(student, self.python, self.t_python, attended=2)
        self.lesson(self.python, self.t_python, dt.date(2026, 9, 25))  # no attendance record
        self.lesson(self.english, self.t_english, dt.date(2026, 9, 26))  # a whole unmarked subject
        period = self.generate_with_feedback([(student, self.python, self.t_python, FULL)])
        ev = self.evaluation(period, student)
        self.assertEqual(ev.attendance_score, D("100.00"))
        self.assertEqual(ev.subject_scores.get(subject=self.python).lessons_unmarked, 1)
        english = ev.subject_scores.get(subject=self.english)
        self.assertEqual((english.lessons_unmarked, english.aggregation_weight), (1, 0))
        self.assertEqual(ev.eligibility_status, EligibilityStatus.ELIGIBLE)
        self.assertTrue(any("без отметки" in w for w in ev.data_warnings))

    def test_lessons_without_subject_get_their_own_bucket(self):
        self.configure(require_complete_feedback=False)
        student = self.student()
        self.attend(student, self.lesson(None, self.t_python, SEP_1))
        ev = self.evaluation(self.generate(), student)
        row = ev.subject_scores.get()
        self.assertEqual((row.subject_name, row.subject_id, row.feedback_score), ("Без предмета", None, None))
        self.assertEqual(ev.overall_score, D("100.00"))
