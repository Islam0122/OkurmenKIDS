"""Циклы и начисления по предметам: IT, English и Soft Skills одной группы
учитываются независимо, у каждого предмета свои тренеры и свои доли."""
from __future__ import annotations

import datetime as dt
import importlib
import io

from django.apps import apps as django_apps
from django.core.management import call_command

from apps.academy.models import CourseLessonPlan, GroupTeacher, Lesson
from apps.accounting.models import CourseCycle, CycleAccrual, CycleLesson, SalaryRule, SalaryType
from apps.accounting.services import estimates
from apps.accounting.services.cycles import sync_all
from apps.accounting.tests.base import FIRST, D, AccountingFixture, day, make_user
from apps.users.models import Subject, Teacher

R = SalaryRule.RuleType
API = "/api/v1/accounting"


def days(month, first, last):
    return [day(month, d) for d in range(first, last + 1)]


class SubjectFixture(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.english = Subject.objects.get_or_create(name="English")[0]
        self.soft = Subject.objects.get_or_create(name="Soft Skills")[0]
        self.course.subjects.set([self.python, self.english, self.soft])
        for subject in (self.python, self.english, self.soft):  # программа: 3 × 48 = 144 урока
            for n in range(48):
                CourseLessonPlan.objects.create(course=self.course, lesson_number=len(subject.name) * 100 + n,
                                                subject=subject, topic="t")
        self.settings = self.course_settings(price="10000", lessons=12, start=None)
        self.teachers = {self.python: (self.trainer_user, self.trainer)}
        for subject, name in ((self.english, "eng"), (self.soft, "soft")):
            user = make_user(name)
            teacher = Teacher.objects.create(user=user)
            GroupTeacher.objects.create(group=self.group_a, teacher=teacher, subject=subject)
            self.teachers[subject] = (user, teacher)
        for subject, pct in ((self.python, "10"), (self.english, "8"), (self.soft, "5")):
            self.rule(self.profile(self.teachers[subject][0], SalaryType.PERCENT), R.PERCENT, percentage=D(pct))
        for _ in range(10):
            self.student(self.group_a)

    def teach(self, subject, dates, *, teacher=None, status=Lesson.Status.COMPLETED):
        program = GroupTeacher.objects.get(group=self.group_a, subject=subject)
        with self.captureOnCommitCallbacks(execute=True):
            for d in dates:
                Lesson.objects.create(
                    group=self.group_a, group_teacher=program, teacher=teacher or program.teacher, subject=subject,
                    lesson_number=Lesson.objects.count() + 1, date=d, start_time=dt.time(9 + len(subject.name) % 8),
                    end_time=dt.time(10 + len(subject.name) % 8), status=status,
                )

    def open_cycle(self, subject):
        return CourseCycle.objects.get(group=self.group_a, subject=subject, status="IN_PROGRESS")


class IndependentProgressTests(SubjectFixture):
    def test_each_subject_has_its_own_progress(self):
        self.teach(self.python, days(9, 1, 10))
        self.teach(self.english, days(9, 1, 8))
        self.teach(self.soft, days(9, 1, 6))
        progress = {c.subject_id: (c.lessons_done, c.required_lessons) for c in
                    CourseCycle.objects.filter(group=self.group_a, status="IN_PROGRESS")}
        self.assertEqual(progress, {self.python.pk: (10, 12), self.english.pk: (8, 12), self.soft.pk: (6, 12)})
        self.assertEqual(self.open_cycle(self.english).teacher_lessons, {str(self.teachers[self.english][1].pk): 8})

    def test_it_lesson_does_not_move_other_subjects(self):
        self.teach(self.english, days(9, 1, 8))
        self.teach(self.soft, days(9, 1, 6))
        self.teach(self.python, days(9, 1, 12))
        self.assertEqual((self.open_cycle(self.english).lessons_done, self.open_cycle(self.soft).lessons_done), (8, 6))

    def test_completing_it_block_does_not_complete_others(self):
        self.teach(self.english, days(9, 1, 11))
        self.teach(self.python, days(9, 1, 12))
        done = CourseCycle.objects.get(status="COMPLETED")
        self.assertEqual((done.subject, done.number, done.lessons_done), (self.python, 1, 12))
        self.assertEqual(self.open_cycle(self.english).lessons_done, 11)
        self.assertEqual(self.open_cycle(self.python).number, 2)
        self.assertEqual(list(CycleAccrual.objects.values_list("employee", flat=True)), [self.trainer_user.pk])
        self.assertEqual(CycleLesson.objects.filter(cycle=done).count(), 12)
        self.assertFalse(CycleLesson.objects.exclude(cycle__subject=self.python).exists())

    def test_group_total_does_not_complete_a_subject_block(self):
        # 6 + 6 + 6 = 18 уроков группы, но ни один предмет не набрал 12.
        for subject in (self.python, self.english, self.soft):
            self.teach(subject, days(9, 1, 6))
        self.assertFalse(CourseCycle.objects.filter(status="COMPLETED").exists())

    def test_cancelled_lessons_only_affect_their_subject(self):
        self.teach(self.python, days(9, 1, 12))
        self.teach(self.english, days(9, 1, 12))
        lesson = Lesson.objects.get(subject=self.english, date=day(9, 3))
        with self.captureOnCommitCallbacks(execute=True):
            lesson.status = Lesson.Status.CANCELLED
            lesson.save()
        self.assertEqual(CourseCycle.objects.get(subject=self.python, number=1).status, "COMPLETED")
        self.assertTrue(CourseCycle.objects.filter(subject=self.english, number=1, status="INVALIDATED").exists())
        self.assertEqual(self.open_cycle(self.english).lessons_done, 11)


class SubjectPayrollTests(SubjectFixture):
    def test_each_subject_teacher_is_paid_separately(self):
        for subject in (self.python, self.english, self.soft):
            self.teach(subject, days(9, 1, 12))
        amounts = {a.employee_id: (a.amount, a.share) for a in CycleAccrual.objects.all()}
        self.assertEqual(amounts, {
            self.trainer_user.pk: (D("10000.00"), D("1")),
            self.teachers[self.english][0].pk: (D("8000.00"), D("1")),
            self.teachers[self.soft][0].pk: (D("5000.00"), D("1")),
        })
        line = self.calc(FIRST).lines.get()
        self.assertEqual((line.amount, line.metadata["subject"]), (D("10000.00"), "Python"))

    def test_substitute_does_not_trigger_review_and_shares_follow_lessons(self):
        eng_user, eng_teacher = self.teachers[self.english]
        self.teach(self.python, days(9, 1, 9))
        self.teach(self.python, days(9, 10, 12), teacher=eng_teacher)  # английский ведёт 3 урока IT
        main = CycleAccrual.objects.get(employee=self.trainer_user)
        sub = CycleAccrual.objects.get(employee=eng_user)
        self.assertEqual((main.status, main.review_reasons, main.lessons_taught, main.amount),
                         (CycleAccrual.Status.ACCRUED, [], 9, D("7500.00")))
        # Своя ставка замены (8 %) × 3/12 — не полная сумма за блок.
        self.assertEqual((sub.status, sub.lessons_taught, sub.amount), (CycleAccrual.Status.ACCRUED, 3, D("2000.00")))

    def test_teacher_without_rule_is_not_paid_and_nobody_gets_his_share(self):
        stranger = Teacher.objects.create(user=make_user("stranger"))
        self.teach(self.python, days(9, 1, 8))
        self.teach(self.python, days(9, 9, 12), teacher=stranger)
        [accrual] = CycleAccrual.objects.all()
        self.assertEqual((accrual.employee, accrual.amount), (self.trainer_user, D("6666.67")))
        cycle = self.client_for(self.accountant).get(f"{API}/cycles/?status=COMPLETED").json()["results"][0]
        self.assertIn("без правила «Процент»", cycle["warnings"][0])

    def test_rerun_does_not_duplicate(self):
        self.teach(self.python, days(9, 1, 12))
        self.teach(self.english, days(9, 1, 12))
        for _ in range(3):
            sync_all()
            call_command("payroll_autorun", "--date", "2026-09-13", stdout=io.StringIO())
            self.calc(FIRST)
        self.assertEqual(CycleAccrual.objects.count(), 2)
        self.assertEqual(CourseCycle.objects.filter(status="COMPLETED").count(), 2)
        self.assertEqual(self.calc(FIRST).lines.count(), 1)

    def test_estimates_per_subject(self):
        self.teach(self.python, days(10, 1, 8))
        self.teach(self.english, days(10, 1, 3))
        rows = {r["subject_name"]: r for r in estimates.all_open()}
        self.assertEqual((rows["Python"]["lessons_done"], rows["Python"]["expected_amount"]), (8, D("10000.00")))
        self.assertEqual((rows["English"]["lessons_done"], rows["English"]["expected_amount"]), (3, D("8000.00")))
        self.assertEqual(rows["Soft Skills"]["lessons_done"], 0)
        mine = estimates.for_employee(self.teachers[self.english][0], today=day(10, 10))
        self.assertEqual([r["subject_name"] for r in mine], ["English"])


class LegacyCutoverTests(SubjectFixture):
    def test_lessons_paid_by_old_group_cycle_are_not_paid_again(self):
        """Общий цикл группы (до предметного учёта) оплатил первые 12 уроков
        группы; они не попадают в предметные циклы повторно."""
        self.teach(self.python, days(9, 1, 6))
        self.teach(self.english, days(9, 1, 6))
        rows = list(Lesson.objects.filter(group=self.group_a).order_by("date", "start_time", "id"))
        CourseCycle.objects.filter(group=self.group_a).update(status="INVALIDATED")
        legacy = CourseCycle.objects.create(
            group=self.group_a, course=self.course, per_subject=False, number=1, status="COMPLETED",
            required_lessons=12, lessons_done=12, lessons_total=12, completed_on=rows[-1].date,
            last_lesson_id=rows[-1].pk, student_count=10, course_price=D("10000"),
        )
        CourseCycle.objects.create(group=self.group_a, course=self.course, per_subject=False, number=2,
                                   status="IN_PROGRESS", required_lessons=12)
        self.teach(self.python, days(9, 7, 18))  # ещё 12 уроков IT после общего цикла
        legacy.refresh_from_db()
        self.assertEqual(legacy.status, "COMPLETED")
        it_cycle = CourseCycle.objects.get(subject=self.python, status="COMPLETED")
        self.assertEqual(it_cycle.start_date, day(9, 7))
        self.assertFalse(CourseCycle.objects.filter(per_subject=False, status="IN_PROGRESS").exists())
        self.assertEqual(self.open_cycle(self.english).lessons_done, 0)

    def test_rollback_refuses_after_subject_cycles_completed(self):
        mig = importlib.import_module("apps.accounting.migrations.0008_close_legacy_open_cycles")
        self.teach(self.python, days(9, 1, 12))
        with self.assertRaises(RuntimeError):
            mig.reopen_legacy(django_apps, None)
        self.assertEqual(CourseCycle.objects.filter(status="COMPLETED").count(), 1)


class CyclesApiTests(SubjectFixture):
    def test_filters_tabs_and_subject_details(self):
        eng_teacher = self.teachers[self.english][1]
        self.teach(self.python, days(9, 1, 12))
        self.teach(self.english, days(9, 1, 8))
        acc = self.client_for(self.accountant)
        open_rows = acc.get(f"{API}/cycles/?status=IN_PROGRESS&group={self.group_a.pk}").json()["results"]
        by_subject = {r["subject_name"]: r for r in open_rows}
        self.assertEqual(set(by_subject), {"Python", "English", "Soft Skills"})
        eng = by_subject["English"]
        self.assertEqual((eng["lessons_done"], eng["lessons_remaining"], eng["progress_percent"],
                          eng["subject_plan_lessons"]), (8, 4, 67, 48))
        self.assertEqual(eng["trainer_lessons"], [{"teacher": eng_teacher.pk, "name": "Eng Test", "lessons": 8}])
        done = acc.get(f"{API}/cycles/?status=COMPLETED").json()["results"]
        self.assertEqual([(r["subject_name"], r["number"]) for r in done], [("Python", 1)])
        only_eng = acc.get(f"{API}/cycles/?status=IN_PROGRESS&subject={self.english.pk}").json()["results"]
        # English есть у обеих групп курса — у каждой свой цикл.
        self.assertEqual(sorted(r["group_name"] for r in only_eng), ["Group A", "Group B"])
        by_trainer = acc.get(f"{API}/cycles/?status=IN_PROGRESS&trainer={eng_teacher.pk}").json()["results"]
        self.assertEqual([r["subject_name"] for r in by_trainer], ["English"])
        self.assertEqual(acc.get(f"{API}/cycles/?search=nothing").json()["count"], 0)
        self.assertEqual(acc.get(f"{API}/cycles/?search=group a&status=IN_PROGRESS").json()["count"], 3)
        options = acc.get(f"{API}/options/").json()
        self.assertIn({"value": "BY_LESSONS", "label": "Пропорционально проведённым урокам"},
                      options["trainer_split_rules"])
