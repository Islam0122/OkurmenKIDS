from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, GroupTeacher
from apps.feedback.models import QuestionOption, Survey, SurveyAnswer, SurveyQuestion, SurveyResponse
from apps.feedback.services import builder
from apps.feedback.services.analytics import FeedbackFilters, question_stats
from apps.feedback.services.export import export_responses_csv
from apps.feedback.services.submission import SubmissionData, SubmissionError, submit_response
from apps.users.models import Subject, Teacher, User

QT = SurveyQuestion.QuestionType
PASSWORD = "Str0ngPassw0rd!"


def make_admin(username="admin") -> User:
    return User.objects.create_superuser(username=username, email=f"{username}@okurmen.kg", password=PASSWORD, first_name="Admin")


def make_teacher(username="teacher") -> Teacher:
    user = User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD, first_name="T",
        role=User.Role.TEACHER, is_verified=True,
    )
    return Teacher.objects.create(user=user)


class FeedbackTestBase(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.survey = Survey.objects.create(title="Отзыв родителей", audience=Survey.Audience.PARENT,
                                            visibility_mode=Survey.VisibilityMode.BOTH, created_by=self.admin)
        self.q_text = builder.create_question(self.survey, {"text": "Что понравилось?", "question_type": QT.TEXT,
                                                           "max_length": 50, "min_length": 3})
        self.q_single = builder.create_question(self.survey, {
            "text": "Как вам тренер?", "question_type": QT.SINGLE_CHOICE,
            "options": [{"text": "Отлично"}, {"text": "Хорошо"}, {"text": "Плохо"}],
        })
        self.q_multi = builder.create_question(self.survey, {
            "text": "Какие предметы нравятся?", "question_type": QT.MULTIPLE_CHOICE, "is_required": False,
            "min_selections": 1, "max_selections": 2,
            "options": [{"text": "Python"}, {"text": "English"}, {"text": "Frontend"}],
        })

    def opt(self, question, index):
        return list(question.options.order_by("order"))[index].id

    def publish(self, survey=None):
        return builder.publish_survey(survey or self.survey, self.admin)

    def valid_answers(self, **overrides):
        answers = {
            str(self.q_text.id): "Всё отлично",
            str(self.q_single.id): self.opt(self.q_single, 0),
            str(self.q_multi.id): [self.opt(self.q_multi, 0)],
        }
        answers.update(overrides)
        return answers


# -- Builder rules -------------------------------------------------------------


class BuilderServiceTests(FeedbackTestBase):
    def test_questions_created_in_order_with_options(self):
        self.assertEqual([q.id for q in self.survey.questions.all()], [self.q_text.id, self.q_single.id, self.q_multi.id])
        self.assertEqual([o.text for o in self.q_single.options.all()], ["Отлично", "Хорошо", "Плохо"])
        self.assertFalse(self.q_text.options.exists())

    def test_empty_text_and_duplicate_or_blank_options_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            builder.create_question(self.survey, {"text": " ", "question_type": QT.TEXT})
        self.assertIn("text", ctx.exception.message_dict)
        with self.assertRaises(ValidationError) as ctx:
            builder.create_question(self.survey, {"text": "Q", "question_type": QT.SINGLE_CHOICE,
                                                  "options": [{"text": "Да"}, {"text": "да"}]})
        self.assertIn("options", ctx.exception.message_dict)
        with self.assertRaises(ValidationError):
            builder.create_question(self.survey, {"text": "Q", "question_type": QT.SINGLE_CHOICE,
                                                  "options": [{"text": "Да"}, {"text": ""}]})

    def test_selection_and_length_ranges_validated(self):
        with self.assertRaises(ValidationError) as ctx:
            builder.create_question(self.survey, {"text": "Q", "question_type": QT.MULTIPLE_CHOICE,
                                                  "min_selections": 3, "max_selections": 2,
                                                  "options": [{"text": "a"}, {"text": "b"}, {"text": "c"}]})
        self.assertIn("min_selections", ctx.exception.message_dict)
        with self.assertRaises(ValidationError) as ctx:
            builder.create_question(self.survey, {"text": "Q", "question_type": QT.MULTIPLE_CHOICE,
                                                  "max_selections": 5, "options": [{"text": "a"}, {"text": "b"}]})
        self.assertIn("max_selections", ctx.exception.message_dict)
        with self.assertRaises(ValidationError) as ctx:
            builder.create_question(self.survey, {"text": "Q", "question_type": QT.TEXT, "min_length": 10, "max_length": 5})
        self.assertIn("min_length", ctx.exception.message_dict)

    def test_update_syncs_options_edit_add_delete_reorder(self):
        ids = [o.id for o in self.q_single.options.order_by("order")]
        builder.update_question(self.q_single, {
            "text": "Как вам тренер?", "question_type": QT.SINGLE_CHOICE,
            "options": [{"id": ids[2], "text": "Плохо"}, {"id": ids[0], "text": "Супер"}, {"text": "Нормально"}],
        })
        texts = list(self.q_single.options.order_by("order").values_list("text", flat=True))
        self.assertEqual(texts, ["Плохо", "Супер", "Нормально"])
        self.assertFalse(QuestionOption.objects.filter(pk=ids[1]).exists())

    def test_option_of_another_question_cannot_be_hijacked(self):
        foreign = self.opt(self.q_multi, 0)
        with self.assertRaises(ValidationError):
            builder.update_question(self.q_single, {"text": "Q", "question_type": QT.SINGLE_CHOICE,
                                                    "options": [{"id": foreign, "text": "x"}, {"text": "y"}]})
        self.assertEqual(QuestionOption.objects.get(pk=foreign).question_id, self.q_multi.id)

    def test_type_change_clears_other_type_settings(self):
        builder.update_question(self.q_multi, {"text": "Теперь текст", "question_type": QT.TEXT, "min_selections": 1})
        self.q_multi.refresh_from_db()
        self.assertIsNone(self.q_multi.min_selections)
        self.assertFalse(self.q_multi.options.exists())

    def test_answered_question_is_locked(self):
        self.publish()
        submit_response(self.survey, SubmissionData(visibility="anonymous", answers=self.valid_answers()))
        with self.assertRaises(ValidationError):
            builder.update_question(self.q_single, {"text": "x", "question_type": QT.TEXT})
        with self.assertRaises(ValidationError):
            builder.delete_question(self.q_single)
        chosen = self.opt(self.q_single, 0)
        others = [o for o in self.q_single.options.all() if o.id != chosen]
        with self.assertRaises(ValidationError):
            builder.update_question(self.q_single, {"text": "x", "question_type": QT.SINGLE_CHOICE,
                                                    "options": [{"id": o.id, "text": o.text} for o in others]})
        # Wording fixes and new options stay possible.
        builder.update_question(self.q_single, {
            "text": "Как вам тренер? (исправлено)", "question_type": QT.SINGLE_CHOICE,
            "options": [{"id": o.id, "text": o.text} for o in self.q_single.options.all()] + [{"text": "Новый"}],
        })
        self.q_single.refresh_from_db()
        self.assertEqual(self.q_single.options.count(), 4)

    def test_reorder_requires_exact_question_set(self):
        builder.reorder_questions(self.survey, [self.q_multi.id, self.q_text.id, self.q_single.id])
        self.assertEqual(list(self.survey.questions.values_list("id", flat=True)), [self.q_multi.id, self.q_text.id, self.q_single.id])
        with self.assertRaises(ValidationError):
            builder.reorder_questions(self.survey, [self.q_multi.id, self.q_text.id])
        with self.assertRaises(ValidationError):
            builder.reorder_questions(self.survey, [self.q_multi.id, self.q_text.id, self.q_text.id])

    def test_duplicate_question_is_inserted_after_original(self):
        copy = builder.duplicate_question(self.q_single)
        ids = list(self.survey.questions.values_list("id", flat=True))
        self.assertEqual(ids, [self.q_text.id, self.q_single.id, copy.id, self.q_multi.id])
        self.assertEqual(copy.options.count(), 3)

    def test_publish_requires_questions_and_two_options(self):
        empty = Survey.objects.create(title="Пустой")
        with self.assertRaises(ValidationError):
            builder.publish_survey(empty)
        q = SurveyQuestion.objects.create(survey=empty, text="Q", question_type=QT.SINGLE_CHOICE)
        QuestionOption.objects.create(question=q, text="Один")
        self.assertTrue(any("два варианта" in p for p in builder.publish_problems(empty)))
        empty.ends_at = timezone.now() - dt.timedelta(days=1)
        self.assertTrue(any("окончания" in p for p in builder.publish_problems(empty)))

    def test_lifecycle_and_audit_log(self):
        self.publish()
        self.assertEqual(self.survey.status, Survey.Status.PUBLISHED)
        builder.close_survey(self.survey, self.admin)
        self.assertEqual(self.survey.availability(), Survey.Availability.CLOSED)
        builder.reopen_survey(self.survey, self.admin)
        self.assertEqual(self.survey.status, Survey.Status.PUBLISHED)
        self.assertIsNone(self.survey.closed_at)
        old = self.survey.public_token
        builder.regenerate_link(self.survey, self.admin)
        self.assertNotEqual(old, self.survey.public_token)
        self.assertGreaterEqual(len(self.survey.public_token), 30)
        self.assertEqual(LogEntry.objects.filter(object_id=str(self.survey.pk)).count(), 4)

    def test_duplicate_survey_is_a_draft_copy(self):
        self.publish()
        copy = builder.duplicate_survey(self.survey, self.admin)
        self.assertEqual(copy.status, Survey.Status.DRAFT)
        self.assertNotEqual(copy.public_token, self.survey.public_token)
        self.assertEqual(copy.questions.count(), 3)
        self.assertEqual(QuestionOption.objects.filter(question__survey=copy).count(), 6)

    def test_targeting_validated_against_lms_relationships(self):
        subject = Subject.objects.create(name="FB Python")
        other_subject = Subject.objects.create(name="FB English")
        course = Course.objects.create(name="FB IT", count_lesson=10)
        course.subjects.add(subject)
        group = Group.objects.create(name="G1", course=course, start_date=dt.date(2026, 1, 1))
        teacher, stranger = make_teacher("t1"), make_teacher("t2")
        GroupTeacher.objects.create(group=group, teacher=teacher, subject=subject)
        Survey(title="ok", group=group, teacher=teacher, subject=subject).clean()
        with self.assertRaises(ValidationError) as ctx:
            Survey(title="bad", group=group, teacher=stranger, subject=other_subject).clean()
        self.assertIn("teacher", ctx.exception.message_dict)
        self.assertIn("subject", ctx.exception.message_dict)


# -- Submission validation ------------------------------------------------------


class SubmissionTests(FeedbackTestBase):
    def setUp(self):
        super().setUp()
        self.publish()

    def submit(self, **kwargs):
        kwargs.setdefault("answers", self.valid_answers())
        return submit_response(self.survey, SubmissionData(**kwargs))

    def errors(self, **kwargs):
        with self.assertRaises(SubmissionError) as ctx:
            self.submit(**kwargs)
        return ctx.exception.errors

    def test_valid_open_submission_stored_relationally(self):
        response = self.submit(visibility="open", respondent_name="  Айгуль  ", child_name="Нурлан")
        self.assertEqual(response.respondent_name, "Айгуль")
        self.assertEqual(response.child_name, "Нурлан")
        self.assertEqual(response.answers.count(), 3)
        multi = SurveyAnswer.objects.get(response=response, question=self.q_multi)
        self.assertEqual(list(multi.selected_options.values_list("id", flat=True)), [self.opt(self.q_multi, 0)])

    def test_anonymous_submission_discards_identity(self):
        response = self.submit(visibility="anonymous", respondent_name="Айгуль", child_name="Нурлан")
        self.assertEqual(response.respondent_name, "")
        # child name is not collected in anonymous mode unless explicitly enabled
        self.assertEqual(response.child_name, "")
        self.assertEqual(response.display_name, "Аноним")

    def test_anonymous_child_name_only_when_enabled(self):
        self.survey.ask_child_name_when_anonymous = True
        self.survey.save()
        response = self.submit(visibility="anonymous", child_name="Нурлан")
        self.assertEqual(response.child_name, "Нурлан")

    def test_database_rejects_named_anonymous_response(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SurveyResponse.objects.create(survey=self.survey, visibility="anonymous", respondent_name="X")

    def test_visibility_rules(self):
        self.assertIn("visibility", self.errors(visibility=None))
        self.assertIn("respondent_name", self.errors(visibility="open", respondent_name=""))
        self.survey.visibility_mode = Survey.VisibilityMode.ANONYMOUS
        self.survey.save()
        self.assertIn("visibility", self.errors(visibility="open", respondent_name="A"))
        self.assertEqual(self.submit().visibility, "anonymous")  # single allowed mode is implied

    def test_child_name_required_mode(self):
        self.survey.child_name_mode = Survey.ChildNameMode.REQUIRED
        self.survey.save()
        self.assertIn("child_name", self.errors(visibility="open", respondent_name="A"))
        self.survey.child_name_mode = Survey.ChildNameMode.NOT_COLLECTED
        self.survey.save()
        self.assertEqual(self.submit(visibility="open", respondent_name="A", child_name="X").child_name, "")

    def test_student_survey_never_stores_child_name(self):
        self.survey.audience = Survey.Audience.STUDENT
        self.survey.child_name_mode = Survey.ChildNameMode.REQUIRED
        self.survey.save()
        self.assertEqual(self.submit(visibility="open", respondent_name="A", child_name="X").child_name, "")

    def test_text_rules(self):
        self.assertIn(f"q_{self.q_text.id}", self.errors(visibility="anonymous", answers=self.valid_answers(**{str(self.q_text.id): "  "})))
        self.assertIn(f"q_{self.q_text.id}", self.errors(visibility="anonymous", answers=self.valid_answers(**{str(self.q_text.id): "ab"})))
        self.assertIn(f"q_{self.q_text.id}", self.errors(visibility="anonymous", answers=self.valid_answers(**{str(self.q_text.id): "x" * 51})))
        self.assertIn(f"q_{self.q_text.id}", self.errors(visibility="anonymous", answers=self.valid_answers(**{str(self.q_text.id): ["x"]})))
        response = self.submit(visibility="anonymous", answers=self.valid_answers(**{str(self.q_text.id): "a\r\nb\x00c"}))
        self.assertEqual(response.answers.get(question=self.q_text).text_value, "a\nbc")

    def test_single_choice_rejects_foreign_or_missing_options(self):
        key = str(self.q_single.id)
        for bad in (self.opt(self.q_multi, 0), 999999, "abc", [self.opt(self.q_single, 0)], True):
            self.assertIn(f"q_{self.q_single.id}", self.errors(visibility="anonymous", answers=self.valid_answers(**{key: bad})))
        self.assertIn(f"q_{self.q_single.id}", self.errors(visibility="anonymous", answers=self.valid_answers(**{key: ""})))

    def test_multiple_choice_limits_and_duplicates(self):
        key, err = str(self.q_multi.id), f"q_{self.q_multi.id}"
        a, b, c = (self.opt(self.q_multi, i) for i in range(3))
        self.assertIn(err, self.errors(visibility="anonymous", answers=self.valid_answers(**{key: [a, b, c]})))
        self.assertIn(err, self.errors(visibility="anonymous", answers=self.valid_answers(**{key: [a, a]})))
        self.assertIn(err, self.errors(visibility="anonymous", answers=self.valid_answers(**{key: [a, self.opt(self.q_single, 0)]})))
        # optional question may be skipped entirely
        answers = self.valid_answers()
        del answers[key]
        self.assertEqual(self.submit(visibility="anonymous", answers=answers).answers.count(), 2)

    def test_unknown_question_rejected(self):
        answers = self.valid_answers()
        answers["999999"] = "x"
        self.assertIn("answers", self.errors(visibility="anonymous", answers=answers))

    def test_unavailable_states(self):
        now = timezone.now()
        cases = [
            ({"status": Survey.Status.CLOSED}, "закрыт"),
            ({"status": Survey.Status.DRAFT}, "не опубликован"),
            ({"starts_at": now + dt.timedelta(days=1)}, "не начался"),
            ({"ends_at": now - dt.timedelta(minutes=1)}, "истёк"),
        ]
        for changes, fragment in cases:
            survey = Survey.objects.get(pk=self.survey.pk)
            for k, v in changes.items():
                setattr(survey, k, v)
            Survey.objects.filter(pk=survey.pk).update(**changes)
            with self.assertRaises(SubmissionError) as ctx:
                self.submit(visibility="anonymous")
            self.assertIn(fragment, ctx.exception.errors["__all__"])
            Survey.objects.filter(pk=survey.pk).update(status=Survey.Status.PUBLISHED, starts_at=None, ends_at=None)

    def test_max_responses(self):
        Survey.objects.filter(pk=self.survey.pk).update(max_responses=1)
        self.submit(visibility="anonymous")
        with self.assertRaises(SubmissionError):
            self.submit(visibility="anonymous")
        self.assertEqual(self.survey.responses.count(), 1)


# -- Analytics / export -----------------------------------------------------------


class AnalyticsTests(FeedbackTestBase):
    def setUp(self):
        super().setUp()
        self.publish()
        a, b = self.opt(self.q_multi, 0), self.opt(self.q_multi, 1)
        submit_response(self.survey, SubmissionData("open", "Мама", "", self.valid_answers(**{str(self.q_multi.id): [a, b]})))
        submit_response(self.survey, SubmissionData("anonymous", "", "", self.valid_answers(**{str(self.q_single.id): self.opt(self.q_single, 1)})))
        answers = self.valid_answers()
        del answers[str(self.q_multi.id)]
        submit_response(self.survey, SubmissionData("anonymous", "", "", answers))

    def test_choice_distributions_use_answered_denominator(self):
        stats = {s["id"]: s for s in question_stats(self.survey, self.survey.responses.all())}
        single = stats[self.q_single.id]
        self.assertEqual(single["answered"], 3)
        self.assertEqual([o["count"] for o in single["options"]], [2, 1, 0])
        self.assertEqual(single["options"][0]["pct"], 66.7)
        multi = stats[self.q_multi.id]
        self.assertEqual(multi["answered"], 2)
        self.assertEqual([o["count"] for o in multi["options"]], [2, 1, 0])
        self.assertEqual(multi["options"][0]["pct"], 100.0)
        self.assertEqual(stats[self.q_text.id]["text_total"], 3)

    def test_filters(self):
        filters = FeedbackFilters.from_query({"visibility": "anonymous", "audience": "parent", "survey": str(self.survey.pk)})
        self.assertEqual(filters.responses().count(), 2)
        self.assertEqual(FeedbackFilters.from_query({"audience": "student"}).responses().count(), 0)
        self.assertEqual(FeedbackFilters.from_query({"date_from": "2999-01-01"}).responses().count(), 0)
        self.assertEqual(FeedbackFilters.from_query({"visibility": "junk", "survey": "x"}).responses().count(), 3)

    def test_csv_export_guards_formulas_and_hides_anonymous(self):
        submit_response(self.survey, SubmissionData("open", "=HYPERLINK(1)", "", self.valid_answers(**{str(self.q_text.id): "+cmd"})))
        csv_text = export_responses_csv(self.survey, self.survey.responses.all())
        self.assertIn("'=HYPERLINK(1)", csv_text)
        self.assertIn("'+cmd", csv_text)
        self.assertIn("Аноним", csv_text)
        self.assertIn("Python; English", csv_text)


# -- Admin JSON API -------------------------------------------------------------------


class AdminApiTests(FeedbackTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_non_admins_are_denied(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/v1/feedback/surveys/").status_code, status.HTTP_401_UNAUTHORIZED)
        teacher_client = APIClient()
        teacher_client.force_authenticate(make_teacher().user)
        for method, url in [
            ("get", "/api/v1/feedback/surveys/"),
            ("get", f"/api/v1/feedback/surveys/{self.survey.pk}/responses/"),
            ("get", f"/api/v1/feedback/surveys/{self.survey.pk}/analytics/"),
            ("post", f"/api/v1/feedback/surveys/{self.survey.pk}/publish/"),
            ("delete", f"/api/v1/feedback/questions/{self.q_text.pk}/"),
            ("get", "/api/v1/feedback/analytics/overview/"),
        ]:
            self.assertEqual(getattr(teacher_client, method)(url).status_code, status.HTTP_403_FORBIDDEN, url)

    def test_create_survey_and_status_is_not_mass_assignable(self):
        res = self.client.post("/api/v1/feedback/surveys/", {
            "title": "Студенты", "audience": "student", "visibility_mode": "open", "status": "published",
        }, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        survey = Survey.objects.get(pk=res.data["id"])
        self.assertEqual(survey.status, Survey.Status.DRAFT)
        self.assertEqual(survey.created_by, self.admin)
        res = self.client.patch(f"/api/v1/feedback/surveys/{survey.pk}/", {"status": "closed", "title": "Новое"}, format="json")
        survey.refresh_from_db()
        self.assertEqual((survey.status, survey.title), (Survey.Status.DRAFT, "Новое"))
        self.assertIn("/feedback/s/", res.data["public_url"])

    def test_survey_date_range_validated(self):
        res = self.client.patch(f"/api/v1/feedback/surveys/{self.survey.pk}/", {
            "starts_at": "2026-05-02T10:00:00Z", "ends_at": "2026-05-01T10:00:00Z"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("ends_at", res.data)

    def test_question_crud_reorder_duplicate(self):
        base = f"/api/v1/feedback/surveys/{self.survey.pk}/"
        res = self.client.post(base + "questions/", {"text": "Новый", "question_type": "single_choice",
                                                     "options": [{"text": "Да"}, {"text": "Нет"}]}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        qid = res.data["id"]
        res = self.client.put(f"/api/v1/feedback/questions/{qid}/", {"text": "Новый?", "question_type": "single_choice",
                                                                     "options": [{"text": ""}]}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("options", res.data)
        res = self.client.post(f"/api/v1/feedback/questions/{qid}/duplicate/")
        self.assertEqual(res.status_code, 201)
        detail = self.client.get(base).data
        order = [q["id"] for q in detail["questions"]]
        res = self.client.post(base + "questions/reorder/", {"order": list(reversed(order))}, format="json")
        self.assertEqual([q["id"] for q in res.data["questions"]], list(reversed(order)))
        self.assertEqual(self.client.delete(f"/api/v1/feedback/questions/{qid}/").status_code, 204)

    def test_publish_close_reopen_regenerate(self):
        base = f"/api/v1/feedback/surveys/{self.survey.pk}/"
        self.assertEqual(self.client.post(base + "publish/").data["status"], "published")
        self.assertEqual(self.client.post(base + "close/").data["status"], "closed")
        self.assertEqual(self.client.post(base + "close/").status_code, 400)
        self.assertEqual(self.client.post(base + "reopen/").data["status"], "published")
        before = self.survey.public_token
        self.client.post(base + "regenerate-link/")
        self.survey.refresh_from_db()
        self.assertNotEqual(before, self.survey.public_token)

    def test_survey_with_responses_cannot_be_deleted(self):
        self.publish()
        submit_response(self.survey, SubmissionData("anonymous", answers=self.valid_answers()))
        res = self.client.delete(f"/api/v1/feedback/surveys/{self.survey.pk}/")
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Survey.objects.filter(pk=self.survey.pk).exists())

    def test_responses_and_analytics_endpoints(self):
        self.publish()
        submit_response(self.survey, SubmissionData("open", "Мама", "", self.valid_answers()))
        submit_response(self.survey, SubmissionData("anonymous", "", "", self.valid_answers()))
        res = self.client.get(f"/api/v1/feedback/surveys/{self.survey.pk}/responses/?visibility=anonymous")
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["respondent"], "Аноним")
        res = self.client.get(f"/api/v1/feedback/surveys/{self.survey.pk}/analytics/")
        self.assertEqual(res.data["response_count"], 2)
        text_stats = next(q for q in res.data["questions"] if q["id"] == self.q_text.id)
        self.assertEqual(set(text_stats["texts"][0]), {"text", "submitted_at"})
        res = self.client.get("/api/v1/feedback/analytics/overview/?audience=parent")
        self.assertEqual((res.data["total_responses"], res.data["anonymous_responses"]), (2, 1))
        res = self.client.get(f"/api/v1/feedback/surveys/{self.survey.pk}/export/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/csv; charset=utf-8")


# -- Public API / page ---------------------------------------------------------------


class PublicApiTests(FeedbackTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = f"/api/v1/feedback/public/{self.survey.public_token}/"

    def test_draft_and_unknown_tokens_are_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/feedback/public/nope/").status_code, 404)
        self.assertEqual(self.client.post(self.url + "submit/", {}, format="json").status_code, 404)

    def test_payload_exposes_no_admin_or_respondent_data(self):
        self.publish()
        submit_response(self.survey, SubmissionData("open", "Секретное Имя", "", self.valid_answers()))
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        body = res.content.decode()
        for leaked in ("Секретное Имя", "created_by", "public_token", "response", "admin@okurmen.kg"):
            self.assertNotIn(leaked, body)
        self.assertEqual(len(res.data["questions"]), 3)

    def test_submit_then_duplicate_guard(self):
        self.publish()
        payload = {"visibility": "anonymous", "answers": self.valid_answers()}
        res = self.client.post(self.url + "submit/", payload, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["message"], self.survey.confirmation_message)
        self.assertTrue(self.client.get(self.url).data["already_submitted"])
        res = self.client.post(self.url + "submit/", payload, format="json")
        self.assertEqual(res.status_code, 409)
        Survey.objects.filter(pk=self.survey.pk).update(allow_multiple_submissions=True)
        self.assertEqual(self.client.post(self.url + "submit/", payload, format="json").status_code, 201)

    def test_invalid_submission_returns_field_errors(self):
        self.publish()
        res = self.client.post(self.url + "submit/", {"visibility": "open", "answers": {}}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("respondent_name", res.data["errors"])
        self.assertIn(f"q_{self.q_text.id}", res.data["errors"])
        self.assertEqual(SurveyResponse.objects.count(), 0)

    def test_closed_survey_reports_unavailable(self):
        self.publish()
        builder.close_survey(self.survey)
        res = self.client.get(self.url)
        self.assertEqual(res.data["availability"], "closed")
        self.assertNotIn("questions", res.data)
        res = self.client.post(self.url + "submit/", {"visibility": "anonymous", "answers": self.valid_answers()}, format="json")
        self.assertEqual(res.status_code, 400)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_submit_is_throttled(self):
        from django.core.cache import cache

        cache.clear()
        self.publish()
        Survey.objects.filter(pk=self.survey.pk).update(allow_multiple_submissions=True)
        payload = {"visibility": "anonymous", "answers": self.valid_answers()}
        codes = [self.client.post(self.url + "submit/", payload, format="json").status_code for _ in range(31)]
        self.assertEqual(codes[:30], [201] * 30)
        self.assertEqual(codes[30], 429)
        cache.clear()


class PublicPageTests(FeedbackTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("feedback_public", args=[self.survey.public_token])
        self.client = Client(enforce_csrf_checks=True)

    def form_data(self, **overrides):
        data = {
            "visibility": "anonymous",
            f"q_{self.q_text.id}": "Всё отлично",
            f"q_{self.q_single.id}": str(self.opt(self.q_single, 0)),
            f"q_{self.q_multi.id}": [str(self.opt(self.q_multi, 0))],
        }
        data.update(overrides)
        return data

    def post(self, data):
        page = self.client.get(self.url)
        data["csrfmiddlewaretoken"] = page.context["csrf_token"]
        return self.client.post(self.url, data)

    def test_draft_is_404_and_published_renders(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.publish()
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Что понравилось?")
        self.assertContains(page, "Анонимно")
        self.assertEqual(page["Cache-Control"], "max-age=0, no-cache, no-store, must-revalidate, private")

    def test_submit_flow(self):
        self.publish()
        res = self.post(self.form_data())
        self.assertRedirects(res, reverse("feedback_public_done", args=[self.survey.public_token]))
        self.assertEqual(self.survey.responses.count(), 1)
        self.assertContains(self.client.get(res["Location"]), self.survey.confirmation_message)
        self.assertContains(self.client.get(self.url), "Вы уже ответили")

    def test_invalid_submit_rerenders_with_errors_and_values(self):
        self.publish()
        res = self.post(self.form_data(**{f"q_{self.q_text.id}": "ab", "visibility": "open", "respondent_name": ""}))
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, "Минимум 3 символа", status_code=400)
        self.assertContains(res, "Укажите ваше имя", status_code=400)
        self.assertContains(res, ">ab</textarea>", status_code=400)
        self.assertEqual(self.survey.responses.count(), 0)

    def test_csrf_is_enforced(self):
        self.publish()
        self.assertEqual(self.client.post(self.url, self.form_data()).status_code, 403)

    def test_closed_survey_shows_friendly_message(self):
        self.publish()
        builder.close_survey(self.survey)
        self.assertContains(self.client.get(self.url), "Опрос недоступен")

    def test_text_is_escaped(self):
        self.publish()
        builder.update_question(self.q_text, {"text": "<script>alert(1)</script>", "question_type": QT.TEXT})
        page = self.client.get(self.url)
        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;")


# -- Admin pages -----------------------------------------------------------------------


class AdminPageTests(FeedbackTestBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.admin)

    def urls(self):
        pk = self.survey.pk
        return [
            reverse("admin:feedback_survey_changelist"),
            reverse("admin:feedback_survey_add"),
            reverse("admin:feedback_survey_change", args=[pk]),
            reverse("admin:feedback_survey_builder", args=[pk]),
            reverse("admin:feedback_survey_preview", args=[pk]),
            reverse("admin:feedback_survey_responses", args=[pk]),
            reverse("admin:feedback_survey_analytics", args=[pk]),
            reverse("admin:feedback_analytics"),
        ]

    def test_admin_pages_render(self):
        self.publish()
        submit_response(self.survey, SubmissionData("open", "Мама", "Сын", self.valid_answers()))
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_staff_non_admin_is_denied(self):
        teacher = make_teacher()
        teacher.user.is_staff = True
        teacher.user.save()
        client = Client()
        client.force_login(teacher.user)
        for url in self.urls():
            self.assertIn(client.get(url).status_code, (302, 403), url)

    def test_add_redirects_to_builder(self):
        res = self.client.post(reverse("admin:feedback_survey_add"), {
            "title": "Новый", "audience": "student", "visibility_mode": "open", "child_name_mode": "optional",
            "confirmation_message": "Спасибо",
        })
        survey = Survey.objects.get(title="Новый")
        self.assertRedirects(res, reverse("admin:feedback_survey_builder", args=[survey.pk]))
        self.assertEqual(survey.created_by, self.admin)

    def test_lifecycle_actions_via_admin(self):
        url = lambda action: reverse("admin:feedback_survey_action", args=[self.survey.pk, action])  # noqa: E731
        self.assertEqual(self.client.get(url("publish")).status_code, 405)
        self.client.post(url("publish"))
        self.survey.refresh_from_db()
        self.assertEqual(self.survey.status, Survey.Status.PUBLISHED)
        self.client.post(url("close"))
        self.survey.refresh_from_db()
        self.assertEqual(self.survey.status, Survey.Status.CLOSED)
        res = self.client.post(url("duplicate"))
        self.assertEqual(Survey.objects.count(), 2)
        self.assertEqual(res.status_code, 302)

    def test_responses_page_never_shows_anonymous_identity(self):
        self.publish()
        submit_response(self.survey, SubmissionData("anonymous", "Скрытое Имя", "Скрытый Ребёнок", self.valid_answers()))
        page = self.client.get(reverse("admin:feedback_survey_responses", args=[self.survey.pk]))
        self.assertNotContains(page, "Скрытое Имя")
        self.assertNotContains(page, "Скрытый Ребёнок")
        self.assertContains(page, "Аноним")

    def test_delete_response_ignores_external_next(self):
        self.publish()
        response = submit_response(self.survey, SubmissionData("anonymous", answers=self.valid_answers()))
        res = self.client.post(
            reverse("admin:feedback_survey_response_delete", args=[self.survey.pk, response.pk]),
            {"next": "https://evil.example/"},
        )
        self.assertEqual(res["Location"], reverse("admin:feedback_survey_responses", args=[self.survey.pk]))
        self.assertFalse(SurveyResponse.objects.exists())


class PublicPageCsrfTests(FeedbackTestBase):
    """Regression tests for the production 403 "Origin checking failed - null
    does not match any trusted origins" on the public survey form.

    Root cause: the public template shipped `<meta name="referrer"
    content="no-referrer">`, which makes browsers send `Origin: null` (and no
    Referer) with the page's own form POST. These tests run over HTTPS with
    the headers a real browser sends, and CSRF checks enforced, like Railway.
    """

    HOST = "https://testserver"

    def setUp(self):
        super().setUp()
        self.publish()
        self.url = reverse("feedback_public", args=[self.survey.public_token])
        self.client = Client(enforce_csrf_checks=True)

    def form_data(self, token):
        return {
            "csrfmiddlewaretoken": token,
            "visibility": "anonymous",
            f"q_{self.q_text.id}": "Всё отлично",
            f"q_{self.q_single.id}": str(self.opt(self.q_single, 0)),
        }

    def load_form(self):
        page = self.client.get(self.url, secure=True)
        self.assertEqual(page.status_code, 200)
        return page, str(page.context["csrf_token"])

    def browser_post(self, data, **headers):
        """A same-origin form POST as a browser sends it under our
        same-origin referrer policy."""
        headers.setdefault("HTTP_ORIGIN", self.HOST)
        headers.setdefault("HTTP_REFERER", self.HOST + self.url)
        return self.client.post(self.url, data, secure=True, **headers)

    def test_get_page_sets_csrf_cookie_and_keeps_origin_sending_referrer_policy(self):
        page, _ = self.load_form()
        self.assertIn("csrftoken", page.cookies)
        self.assertContains(page, 'name="csrfmiddlewaretoken"')
        self.assertContains(page, '<meta name="referrer" content="same-origin">')
        self.assertNotContains(page, "no-referrer")
        self.assertEqual(page["Referrer-Policy"], "same-origin")

    def test_valid_anonymous_submission_over_https_is_accepted(self):
        _, token = self.load_form()
        res = self.browser_post(self.form_data(token))
        self.assertRedirects(res, reverse("feedback_public_done", args=[self.survey.public_token]), fetch_redirect_response=False)
        response = self.survey.responses.get()
        self.assertEqual((response.visibility, response.respondent_name), ("anonymous", ""))

    def test_origin_null_is_rejected_and_logged_without_secrets(self):
        _, token = self.load_form()
        with self.assertLogs("okurmenkids.security.csrf", "WARNING") as logs:
            res = self.browser_post(self.form_data(token), HTTP_ORIGIN="null", HTTP_REFERER="")
        self.assertEqual(res.status_code, 403)
        self.assertContains(res, "Откройте ссылку на опрос заново", status_code=403)
        line = logs.output[0]
        self.assertIn("Origin checking failed - null does not match any trusted origins", line)
        self.assertIn("method=POST path=/feedback/s/<token>/ origin=null", line)
        self.assertIn("csrf_cookie=True", line)
        self.assertNotIn(self.survey.public_token, line)
        self.assertNotIn(token, line)
        self.assertNotIn(self.client.cookies["csrftoken"].value, line)
        self.assertFalse(self.survey.responses.exists())

    def test_https_post_without_origin_or_referer_is_rejected(self):
        # What a no-referrer page produces in browsers that omit Origin.
        _, token = self.load_form()
        res = self.client.post(self.url, self.form_data(token), secure=True)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(self.survey.responses.exists())

    def test_missing_csrf_token_is_rejected(self):
        self.load_form()
        data = self.form_data("")
        del data["csrfmiddlewaretoken"]
        with self.assertLogs("okurmenkids.security.csrf", "WARNING") as logs:
            res = self.browser_post(data)
        self.assertEqual(res.status_code, 403)
        self.assertIn("CSRF token missing", logs.output[0])
        self.assertFalse(self.survey.responses.exists())

    def test_invalid_csrf_token_is_rejected(self):
        self.load_form()
        with self.assertLogs("okurmenkids.security.csrf", "WARNING") as logs:
            res = self.browser_post(self.form_data("x" * 64))
        self.assertEqual(res.status_code, 403)
        self.assertIn("CSRF token from POST incorrect", logs.output[0])
        self.assertFalse(self.survey.responses.exists())

    def test_cross_site_origin_is_rejected(self):
        _, token = self.load_form()
        res = self.browser_post(self.form_data(token), HTTP_ORIGIN="https://evil.example",
                                HTTP_REFERER="https://evil.example/page")
        self.assertEqual(res.status_code, 403)
        self.assertFalse(self.survey.responses.exists())

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_html_submissions_are_rate_limited(self):
        from django.core.cache import cache

        cache.clear()
        Survey.objects.filter(pk=self.survey.pk).update(allow_multiple_submissions=True)
        _, token = self.load_form()
        codes = [self.browser_post(self.form_data(token)).status_code for _ in range(31)]
        self.assertEqual(codes[:30], [302] * 30)
        self.assertEqual(codes[30], 429)
        self.assertEqual(self.survey.responses.count(), 30)
        cache.clear()

    def test_other_paths_keep_djangos_default_csrf_page(self):
        with self.assertLogs("okurmenkids.security.csrf", "WARNING"):
            res = self.client.post(reverse("admin:login"), {"username": "a", "password": "b"}, secure=True,
                                   HTTP_ORIGIN=self.HOST)
        self.assertEqual(res.status_code, 403)
        self.assertNotContains(res, "Откройте ссылку на опрос заново", status_code=403)


class PublicPageRedesignTests(FeedbackTestBase):
    """Audience-specific wording and honest privacy notices on the public page."""

    def setUp(self):
        super().setUp()
        self.publish()
        self.url = reverse("feedback_public", args=[self.survey.public_token])
        self.done_url = reverse("feedback_public_done", args=[self.survey.public_token])

    def set(self, **fields):
        Survey.objects.filter(pk=self.survey.pk).update(**fields)

    def test_parent_intro_step_markup_and_facts(self):
        page = self.client.get(self.url)
        for text in ("Отзыв родителей", "Ваше мнение помогает нам улучшать обучение вашего ребёнка",
                     "3 вопроса", "≈ 2 мин", "Вы сами выберете", "С именем", "Анонимно",
                     "Имя и фамилия ребёнка", "Обязательный вопрос", "Необязательный вопрос",
                     'data-action="start"', 'data-action="next"', 'data-action="back"', 'data-step="review"'):
            self.assertContains(page, text)
        self.assertNotContains(page, "{#")  # template comments never leak into the page

    def test_student_wording_and_no_parent_fields(self):
        self.set(audience=Survey.Audience.STUDENT, visibility_mode=Survey.VisibilityMode.OPEN,
                 child_name_mode=Survey.ChildNameMode.REQUIRED)
        page = self.client.get(self.url)
        for text in ("Отзыв студента", "Поделись своим мнением", "О тебе", "Твоё имя", "увидит твоё имя"):
            self.assertContains(page, text)
        self.assertContains(page, '<p class="fb-eyebrow">Отзыв студента</p>', html=False)
        # (the fixture's own title is "Отзыв родителей" — admin content, not UI copy)
        for text in ("ребёнка", 'name="child_name"', '<p class="fb-eyebrow">Отзыв родителей</p>'):
            self.assertNotContains(page, text)

    def test_anonymous_claim_only_when_nothing_identifying_is_asked(self):
        self.set(visibility_mode=Survey.VisibilityMode.ANONYMOUS)
        page = self.client.get(self.url)
        self.assertContains(page, "Ваш ответ отправляется анонимно")
        self.assertNotContains(page, 'name="child_name"')
        self.set(ask_child_name_when_anonymous=True)
        page = self.client.get(self.url)
        self.assertContains(page, "не полностью анонимный")
        self.assertNotContains(page, "отправляется анонимно")
        self.assertContains(page, 'name="child_name"')

    def test_open_mode_notice(self):
        self.set(visibility_mode=Survey.VisibilityMode.OPEN)
        self.assertContains(self.client.get(self.url), "администратор увидит ваше имя рядом с ответом")

    def test_question_count_pluralisation(self):
        from apps.feedback.public_views import _plural

        self.assertEqual([_plural(n, "вопрос", "вопроса", "вопросов") for n in (1, 2, 5, 11, 21, 22)],
                         ["вопрос", "вопроса", "вопросов", "вопросов", "вопрос", "вопроса"])

    def test_character_counter_only_when_admin_set_a_limit(self):
        page = self.client.get(self.url)
        self.assertContains(page, "0 / 50")  # q_text has max_length=50
        builder.update_question(self.q_text, {"text": "Без лимита", "question_type": QT.TEXT})
        self.assertNotContains(self.client.get(self.url), "data-counter-for")

    def test_success_screen_by_audience_uses_backend_message(self):
        self.set(confirmation_message="Спасибо от академии!")
        page = self.client.get(self.done_url)
        self.assertContains(page, "Спасибо за отзыв!")
        self.assertContains(page, "Спасибо от академии!")
        self.assertContains(page, "улучшить обучение вашего ребёнка")
        self.set(audience=Survey.Audience.STUDENT)
        page = self.client.get(self.done_url)
        self.assertContains(page, "Твоё мнение важно для нас")
        self.assertNotContains(page, "ребёнка")

    def test_already_answered_uses_student_wording(self):
        self.set(audience=Survey.Audience.STUDENT)
        from django.http import HttpResponse

        from apps.feedback.public import mark_submitted

        cookie_carrier = HttpResponse()  # the signed "already answered" cookie
        mark_submitted(cookie_carrier, self.survey)
        self.client.cookies.update(cookie_carrier.cookies)
        self.assertContains(self.client.get(self.url), "Ты уже ответил(а)")


class PublicPageLightThemeTests(FeedbackTestBase):
    """The public survey is always the light White + Okurmen Green theme —
    it must not switch to dark when the phone is in dark mode."""

    def test_page_declares_light_only(self):
        self.publish()
        page = self.client.get(reverse("feedback_public", args=[self.survey.public_token]))
        self.assertContains(page, '<meta name="color-scheme" content="only light">')

    def test_stylesheet_has_no_dark_mode_override(self):
        from django.contrib.staticfiles import finders

        css = open(finders.find("feedback/css/public.css"), encoding="utf-8").read()
        self.assertNotIn("prefers-color-scheme", css)
        self.assertIn("color-scheme: only light", css)
        for token in ("#F6F9F7", "#FFFFFF", "#35A866", "#2B9258", "#E8F6ED", "#1F2937", "#6B7280", "#E5E7EB"):
            self.assertIn(token, css)
