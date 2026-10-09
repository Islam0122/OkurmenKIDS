"""Team Lead work log, tasks and reports (section 6).

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.testing.tests.base import TestingFixture, make_teacher
from apps.users.models import User
from apps.worklog.models import ReportKind, TaskStatus, TeamLeadReport, WorkLogEntry, WorkType

ENTRIES = "/api/v1/worklog/entries/"
REPORTS = "/api/v1/worklog/reports/"
OPTIONS = "/api/v1/worklog/options/"


class WorklogFixture(TestingFixture):
    def setUp(self):
        super().setUp()
        self.lead = User.objects.create_user(
            username="lead", email="lead@okurmen.kg", password="x", first_name="Нурлан", role=User.Role.TEAM_LEAD,
        )
        self.lead2 = User.objects.create_user(
            username="lead2", email="lead2@okurmen.kg", password="x", role=User.Role.TEAM_LEAD,
        )
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.api = APIClient()
        self.api.force_authenticate(self.lead)
        self.today = timezone.localdate()

    def log(self, **overrides):
        body = {
            "work_type": WorkType.LESSON_CONTROL,
            "date": self.today.isoformat(),
            "time_from": "10:00", "time_to": "11:30",
            "group": self.group.pk, "teacher": self.teacher.pk,
            "description": "Посетил занятие",
            "result": "Тренер не проверил ДЗ",
            "next_action": "Повторная проверка",
            "responsible": "Тренер", "deadline": (self.today + dt.timedelta(days=3)).isoformat(),
        }
        body.update(overrides)
        return self.api.post(ENTRIES, body, format="json")

    def task(self, **overrides):
        body = {
            "entry_kind": "task", "work_type": WorkType.TRAINER, "title": "Проверить журнал",
            "responsible": "Айбек", "deadline": (self.today + dt.timedelta(days=2)).isoformat(),
            "priority": "high",
        }
        body.update(overrides)
        return self.api.post(ENTRIES, body, format="json")


class WorkLogEntryTests(WorklogFixture):
    def test_log_entry_answers_the_five_questions(self):
        res = self.log()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["author"]["id"], self.lead.pk)
        self.assertIn("Результат: Тренер не проверил ДЗ", res.data["summary"])
        self.assertIn("группа Group 12", res.data["summary"])
        self.assertTrue(res.data["can_edit"])

    def test_log_entry_requires_what_who_result_next(self):
        res = self.log(description="", group=None, teacher=None, result="", next_action="")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ("description", "with_whom", "result", "next_action"):
            self.assertIn(field, res.data)

    def test_with_whom_text_is_enough(self):
        res = self.log(group=None, teacher=None, with_whom="Команда тренеров")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

    def test_next_action_with_deadline_needs_responsible(self):
        res = self.log(responsible="")
        self.assertIn("responsible", res.data)

    def test_time_order(self):
        res = self.log(time_from="12:00", time_to="11:00")
        self.assertIn("time_to", res.data)

    def test_task_requires_title_responsible_deadline(self):
        res = self.task(title="", responsible="", deadline=None)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ("title", "responsible", "deadline"):
            self.assertIn(field, res.data)

    def test_overdue_is_computed_and_filterable(self):
        late = self.task(deadline=(self.today - dt.timedelta(days=1)).isoformat()).data
        self.task()
        self.task(deadline=(self.today - dt.timedelta(days=5)).isoformat(), status="done")
        self.assertEqual(late["effective_status"], TaskStatus.OVERDUE)
        self.assertTrue(late["is_overdue"])
        res = self.api.get(ENTRIES, {"status": "overdue"})
        rows = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual([e["id"] for e in rows], [late["id"]])
        res = self.api.get(ENTRIES + "summary/")
        self.assertEqual(res.data["overdue"], 1)
        self.assertEqual(res.data["open"], 2)

    def test_only_author_edits(self):
        entry_id = self.log().data["id"]
        other = APIClient()
        other.force_authenticate(self.lead2)
        self.assertEqual(other.get(f"{ENTRIES}{entry_id}/").status_code, status.HTTP_200_OK)
        self.assertEqual(other.patch(f"{ENTRIES}{entry_id}/", {"result": "x"}, format="json").status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertEqual(other.delete(f"{ENTRIES}{entry_id}/").status_code, status.HTTP_403_FORBIDDEN)
        res = self.api.patch(f"{ENTRIES}{entry_id}/", {"status": "done"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)

    def test_trainer_and_anonymous_have_no_access(self):
        trainer = APIClient()
        trainer.force_authenticate(self.teacher.user)
        for url in (ENTRIES, REPORTS, OPTIONS):
            self.assertEqual(trainer.get(url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.log().status_code, status.HTTP_201_CREATED)
        self.assertEqual(trainer.post(ENTRIES, {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(APIClient().get(ENTRIES).status_code, (401, 403))

    def test_admin_reads_but_does_not_edit_others(self):
        entry_id = self.log().data["id"]
        admin = APIClient()
        admin.force_authenticate(self.admin)
        self.assertEqual(admin.get(f"{ENTRIES}{entry_id}/").status_code, status.HTTP_200_OK)
        self.assertEqual(admin.patch(f"{ENTRIES}{entry_id}/", {"result": "x"}, format="json").status_code,
                         status.HTTP_403_FORBIDDEN)


class ReportTests(WorklogFixture):
    def create(self, **body):
        return self.api.post(REPORTS, body, format="json")

    def test_options_describe_every_kind(self):
        res = self.api.get(OPTIONS)
        self.assertEqual(res.status_code, 200)
        kinds = {k["kind"] for k in res.data["report_kinds"]}
        self.assertEqual(kinds, set(ReportKind.values))
        self.assertEqual(len(res.data["work_types"]), 11)
        self.assertEqual({g["name"] for g in res.data["groups"]}, {"Group 12", "Group 13"})
        self.assertEqual([t["id"] for t in res.data["teachers"]], [self.teacher.pk])
        self.assertEqual(res.data["students"][0]["group"], self.group.pk)

    def test_draft_may_be_incomplete_submitted_may_not(self):
        res = self.create(kind="daily", date=self.today.isoformat(), data={"problems": ["Нет кабинета"]})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["status"], "draft")
        res = self.api.patch(f"{REPORTS}{res.data['id']}/", {"status": "submitted"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("decisions", res.data["data"])
        self.assertIn("plan_next_day", res.data["data"])

    def test_daily_report_lists_the_day_entries(self):
        self.log()
        self.log(date=(self.today - dt.timedelta(days=1)).isoformat())
        res = self.create(kind="daily", date=self.today.isoformat(), status="submitted", data={
            "working_hours": "10:00–18:00", "problems": "Нет кабинета\nОпоздал тренер",
            "decisions": ["Перенести"], "plan_next_day": ["Проверить группу"],
        })
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["data"]["problems"], ["Нет кабинета", "Опоздал тренер"])
        self.assertEqual(len(res.data["day_entries"]), 1)
        self.assertEqual(res.data["metrics"], {"entries": 1})

    def test_kind_cannot_change_and_status_must_fit(self):
        rid = self.create(kind="daily", date=self.today.isoformat()).data["id"]
        self.assertIn("kind", self.api.patch(f"{REPORTS}{rid}/", {"kind": "weekly"}, format="json").data)
        self.assertIn("status", self.api.patch(f"{REPORTS}{rid}/", {"status": "resolved"}, format="json").data)

    def test_weekly_report_computes_metrics(self):
        start = self.today - dt.timedelta(days=6)
        res = self.create(kind="weekly", period_start=start.isoformat(), period_end=self.today.isoformat())
        self.assertEqual(res.status_code, 201, res.data)
        m = res.data["metrics"]
        for section in ("groups", "trainers", "students", "homework", "kpi", "tests", "quality"):
            self.assertIn(section, m)
        self.assertEqual(m["groups"]["total"], 2)

    def test_range_required_and_ordered(self):
        self.assertIn("period_start", self.create(kind="monthly").data)
        res = self.create(kind="monthly", period_start="2026-09-30", period_end="2026-09-01")
        self.assertIn("period_end", res.data)

    def test_monthly_has_exams_and_closed_groups(self):
        res = self.create(kind="monthly", period_start="2026-09-01", period_end="2026-09-30")
        self.assertIn("exams", res.data["metrics"])
        self.assertIn("closed", res.data["metrics"]["groups"])

    def test_lesson_visit_fills_from_lesson_and_needs_eight_criteria(self):
        res = self.create(kind="lesson_visit", lesson=self.lesson.pk, status="submitted", data={"overall": 4})
        self.assertEqual(res.status_code, 400)
        self.assertIn("preparation", res.data["data"])
        scores = {k: 4 for k in ("preparation", "structure", "explanation", "engagement",
                                 "discipline", "practice", "homework", "lms")}
        res = self.create(kind="lesson_visit", lesson=self.lesson.pk, status="submitted", data={
            **scores, "overall": 4, "good": "Структура", "improve": "Практика", "recommendations": "Больше задач",
        })
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["group"], self.group.pk)
        self.assertEqual(res.data["teacher"], self.teacher.pk)
        self.assertEqual(res.data["date"], "2026-09-02")
        self.assertEqual(res.data["metrics"]["group"]["name"], "Group 12")

    def test_score_out_of_range(self):
        res = self.create(kind="lesson_visit", lesson=self.lesson.pk, data={"overall": 7})
        self.assertIn("overall", res.data["data"])

    def test_problem_student_takes_group_and_new_may_be_incomplete(self):
        res = self.create(kind="problem_student", student=self.student.pk, status="new",
                          data={"problems": ["Низкая посещаемость"]})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["group"], self.group.pk)
        self.assertEqual(res.data["status_label"], "Новая")
        self.assertEqual(res.data["metrics"]["student"]["id"], self.student.pk)
        res = self.api.patch(f"{REPORTS}{res.data['id']}/", {"status": "in_progress"}, format="json")
        self.assertIn("action", res.data["data"])

    def test_problem_student_rejects_unknown_problem(self):
        res = self.create(kind="problem_student", student=self.student.pk, status="new", data={"problems": ["Лень"]})
        self.assertIn("problems", res.data["data"])

    def test_trainer_review_requires_teacher_and_computes(self):
        self.assertIn("teacher", self.create(kind="trainer_review", period_start="2026-09-01",
                                             period_end="2026-09-30").data)
        res = self.create(kind="trainer_review", teacher=self.teacher.pk,
                          period_start="2026-09-01", period_end="2026-09-30")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["metrics"]["teacher"]["id"], self.teacher.pk)

    def test_internship_rows_and_decision(self):
        newbie = make_teacher("newbie")
        res = self.create(kind="internship", teacher=newbie.pk, period_start="2026-09-01", period_end="2026-09-03",
                          status="submitted", data={
                              "days": [{"date": "2026-09-01", "learned": "LMS", "showed": "", "improve": "Темп"}, {}],
                              "decision": "Рекомендуется к испытательному сроку",
                          })
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["data"]["days"], [{"date": "2026-09-01", "learned": "LMS", "improve": "Темп"}])
        res = self.create(kind="internship", teacher=newbie.pk, period_start="2026-09-01", period_end="2026-09-03",
                          data={"decision": "Возможно"})
        self.assertIn("decision", res.data["data"])

    def test_probation_handed_to_management_visible_to_admin(self):
        res = self.create(kind="probation", teacher=self.teacher.pk, period_start="2026-09-01",
                          period_end="2026-09-30", status="submitted", data={
                              "lesson_quality": 4, "discipline": 5, "communication": 4, "lms_work": 3,
                              "strengths": "a", "problems": "b", "dynamics": "c", "recommendations": "d",
                              "decision": "Продлить испытательный срок",
                          })
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["status_label"], "Передан руководству")
        admin = APIClient()
        admin.force_authenticate(self.admin)
        listing = admin.get(REPORTS, {"kind": "probation", "status": "submitted"}).data
        rows = listing["results"] if isinstance(listing, dict) else listing
        self.assertEqual([r["id"] for r in rows], [res.data["id"]])
        self.assertFalse(rows[0]["can_edit"])

    def test_meeting_decisions_are_tasks(self):
        meeting = self.create(kind="meeting", date=self.today.isoformat(), status="submitted", data={
            "participants": ["Айбек", "Мира"], "discussed": ["Экзамены"],
        })
        self.assertEqual(meeting.status_code, 201, meeting.data)
        self.task(report=meeting.data["id"], title="Подготовить экзамен")
        detail = self.api.get(f"{REPORTS}{meeting.data['id']}/").data
        self.assertEqual([t["title"] for t in detail["tasks"]], ["Подготовить экзамен"])
        self.assertEqual(detail["tasks"][0]["responsible"], "Айбек")

    def test_recalculate_author_only(self):
        rid = self.create(kind="weekly", period_start="2026-09-01", period_end="2026-09-07").data["id"]
        TeamLeadReport.objects.filter(pk=rid).update(metrics={})
        res = self.api.post(f"{REPORTS}{rid}/recalculate/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("groups", res.data["metrics"])
        other = APIClient()
        other.force_authenticate(self.lead2)
        self.assertEqual(other.post(f"{REPORTS}{rid}/recalculate/").status_code, 403)

    def test_quality_counts_visits_and_problems(self):
        self.log()
        self.log(work_type=WorkType.PROBLEM, problem="Студент пропускает", status="done")
        self.task(work_type=WorkType.LESSON_CONTROL, teacher=make_teacher("other").pk)  # planned, not done
        WorkLogEntry.objects.update(date=dt.date(2026, 9, 3))
        res = self.create(kind="weekly", period_start="2026-09-01", period_end="2026-09-07")
        q = res.data["metrics"]["quality"]
        self.assertEqual(q["lessons_visited"], 1)
        self.assertEqual(q["trainers_checked"], 1)
        self.assertEqual(q["problems_found"], 1)
        self.assertEqual(q["problems_resolved"], 1)


def _pdf_text(content: bytes) -> str:
    """Text of a PDF via poppler's pdftotext (skips the test if it's missing)."""
    import shutil
    import subprocess
    import unittest

    if not shutil.which("pdftotext"):
        raise unittest.SkipTest("pdftotext is not available")
    return subprocess.run(["pdftotext", "-layout", "-", "-"], input=content, capture_output=True, check=True).stdout.decode()


def _pdf_pages(content: bytes) -> int:
    import re

    return len(re.findall(rb"/Type\s*/Page[^s]", content))


class ReportPdfTests(WorklogFixture):
    def create(self, **body):
        res = self.api.post(REPORTS, body, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def pdf(self, rid, client=None):
        return (client or self.api).get(f"{REPORTS}{rid}/pdf/")

    def test_monthly_pdf_is_an_attachment_named_by_kind_and_period(self):
        report = self.create(kind="monthly", period_start="2026-09-01", period_end="2026-09-30", status="submitted", data={
            "hackathons": 2, "main_problems": ["Нехватка кабинетов"], "done": ["Провели хакатон"],
            "next_month_plan": ["Экзамены"],
        })
        res = self.pdf(report["id"])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertEqual(res["Content-Disposition"], 'attachment; filename="teamlead_report_monthly_2026_09.pdf"')
        self.assertEqual(res["Cache-Control"], "no-store")
        self.assertTrue(res.content.startswith(b"%PDF"))

    def test_pdf_has_the_page_data_title_author_period_and_metrics(self):
        report = self.create(kind="weekly", period_start="2026-09-01", period_end="2026-09-07", status="submitted", data={
            "trainers_internship": 1, "problem_groups": ["Group 12"],
            "summary": "Неделя прошла спокойно", "next_week_plan": ["Проверить ДЗ", "Собрание"],
        })
        text = _pdf_text(self.pdf(report["id"]).content)
        for expected in ("ОТЧЁТ TEAM LEAD", "Еженедельный отчёт", "01.09.2026 — 07.09.2026", "Нурлан · Team Lead",
                         "Дата формирования", "Сдан", "Неделя прошла спокойно", "Проверить ДЗ",
                         "Тренеров на стажировке", "ДАННЫЕ LMS", "KPI академии", "Контроль качества",
                         "Страница 1 из"):
            self.assertIn(expected, text)
        # The figures are the stored snapshot the page shows, not a recalculation.
        groups_total = report["metrics"]["groups"]["total"]
        self.assertRegex(text, rf"Всего\s+{groups_total}")
        self.assertNotIn("сом", text)  # no finance in this report

    def test_filename_of_other_kinds(self):
        daily = self.create(kind="daily", date="2026-09-04")
        self.assertIn('filename="teamlead_report_daily_2026_09_04.pdf"', self.pdf(daily["id"])["Content-Disposition"])
        weekly = self.create(kind="weekly", period_start="2026-09-01", period_end="2026-09-07")
        self.assertIn("teamlead_report_weekly_2026_09_01-2026_09_07.pdf", self.pdf(weekly["id"])["Content-Disposition"])
        partial = self.create(kind="monthly", period_start="2026-09-01", period_end="2026-09-15")
        self.assertIn("teamlead_report_monthly_2026_09_01-2026_09_15.pdf", self.pdf(partial["id"])["Content-Disposition"])

    def test_kyrgyz_text_and_long_tables_span_pages_with_repeated_header(self):
        self.log(description="Кыргызча: өнүгүү, үйрөнүү, маңыз — " + "узун сөз " * 30)
        for i in range(45):
            self.log(time_from=f"{8 + i % 12:02d}:00", time_to=f"{8 + i % 12:02d}:30",
                     description=f"Запись {i}: Айжаркын Өмүрбекова-Сыдыкбекова текшерди", result="Жыйынтык " * 6)
        report = self.create(kind="daily", date=self.today.isoformat(), data={
            "problems": ["Өтө көп сабак"], "decisions": ["Чечим кабыл алынды"], "plan_next_day": ["Үй тапшырма"],
        })
        content = self.pdf(report["id"]).content
        text = _pdf_text(content)
        for word in ("өнүгүү", "үйрөнүү", "маңыз", "Өмүрбекова", "Өтө көп сабак", "Чечим кабыл алынды"):
            self.assertIn(word, text)
        self.assertGreaterEqual(_pdf_pages(content), 3)
        self.assertGreaterEqual(text.count("продолжение таблицы"), 1)
        self.assertGreaterEqual(text.count("Группа / тренер"), 2)  # header repeated on the next page
        self.assertIn("Запись 44", text)  # nothing lost at the end

    def test_meeting_decisions_rows_and_visit_scores(self):
        meeting = self.create(kind="meeting", date=self.today.isoformat(), status="submitted", data={
            "participants": ["Айбек", "Мира"], "discussed": ["Экзамены"],
        })
        self.task(report=meeting["id"], title="Подготовить экзамен")
        text = _pdf_text(self.pdf(meeting["id"]).content)
        for expected in ("Решения", "Подготовить экзамен", "Айбек", "Высокий", "Участники", "Мира"):
            self.assertIn(expected, text)
        scores = {k: 4 for k in ("preparation", "structure", "explanation", "engagement", "discipline", "practice", "homework", "lms")}
        visit = self.create(kind="lesson_visit", lesson=self.lesson.pk, status="submitted", data={
            **scores, "overall": 5, "good": "Структура", "improve": "Практика", "recommendations": "Больше задач",
        })
        text = _pdf_text(self.pdf(visit["id"]).content)
        self.assertIn("5 из 5", text)
        self.assertIn("Group 12", text)

    def test_internship_rows_table(self):
        newbie = make_teacher("newbie")
        report = self.create(kind="internship", teacher=newbie.pk, period_start="2026-09-01", period_end="2026-09-03",
                             data={"days": [{"date": "2026-09-01", "learned": "LMS", "improve": "Темп"}]})
        text = _pdf_text(self.pdf(report["id"]).content)
        for expected in ("Дни стажировки", "Что изучил", "01.09.2026", "LMS", "Темп"):
            self.assertIn(expected, text)

    def test_access_same_as_the_report_page(self):
        rid = self.create(kind="daily", date=self.today.isoformat())["id"]
        admin = APIClient()
        admin.force_authenticate(self.admin)
        self.assertEqual(self.pdf(rid, admin).status_code, 200)
        trainer = APIClient()
        trainer.force_authenticate(self.teacher.user)
        self.assertEqual(self.pdf(rid, trainer).status_code, 403)
        self.assertEqual(self.pdf(rid, APIClient()).status_code, 401)
        self.assertEqual(self.pdf(999999).status_code, 404)
        # A query parameter can't swap the report: the id in the path decides.
        other = self.create(kind="daily", date=(self.today - dt.timedelta(days=1)).isoformat())["id"]
        res = self.api.get(f"{REPORTS}{rid}/pdf/", {"id": other, "pk": other})
        self.assertIn(f"_{self.today:%Y_%m_%d}.pdf", res["Content-Disposition"])

    def test_pdf_does_not_recalculate_or_change_the_report(self):
        rid = self.create(kind="weekly", period_start="2026-09-01", period_end="2026-09-07")["id"]
        TeamLeadReport.objects.filter(pk=rid).update(metrics={"groups": {"total": 777}})
        before = TeamLeadReport.objects.get(pk=rid).updated_at
        text = _pdf_text(self.pdf(rid).content)
        self.assertRegex(text, r"Всего\s+777")
        after = TeamLeadReport.objects.get(pk=rid)
        self.assertEqual(after.metrics, {"groups": {"total": 777}})
        self.assertEqual(after.updated_at, before)
