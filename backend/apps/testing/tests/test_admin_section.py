"""The «Тесты» admin section (admin.py + admin_views.py)."""
from __future__ import annotations

import json

from django.test import TestCase
from django.urls import reverse

from apps.testing.models import Question, QuestionType, Test, TestStatus
from apps.testing.services import questions as svc
from apps.testing.services.question_rules import OptionData, QuestionData
from apps.users.models import User


def choice(text="Что такое Python?"):
    return QuestionData(QuestionType.SINGLE_CHOICE, text, options=[OptionData("Язык", True), OptionData("Змея")])


class AdminFixture(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.client.force_login(self.admin)
        self.test = Test.objects.create(title="IT", description="Основы IT")

    def url(self, name, *args):
        return reverse(f"admin:{name}", args=args)


class AccessTests(AdminFixture):
    def test_teacher_staff_account_has_no_access(self):
        teacher = User.objects.create_user(
            username="t1", email="t1@okurmen.kg", password="x", role=User.Role.TEACHER, is_staff=True,
        )
        self.client.force_login(teacher)
        for url in (
            self.url("testing_test_changelist"),
            self.url("testing_test_add"),
            self.url("testing_test_change", self.test.pk),
            self.url("testing_test_settings", self.test.pk),
            self.url("testing_question_add", self.test.pk),
        ):
            self.assertIn(self.client.get(url).status_code, (302, 403), url)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(self.url("testing_test_changelist"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_no_separate_questions_section(self):
        self.assertFalse(any(name.startswith("testing_question_changelist") for name in self._admin_url_names()))
        response = self.client.get(reverse("admin:index"))
        self.assertNotContains(response, "Вопросы</p>")

    def _admin_url_names(self):
        from django.contrib import admin

        return [p.name for p in admin.site.get_urls() if getattr(p, "name", None)]


class ListAndCreateTests(AdminFixture):
    def test_list_shows_cards_with_counts_and_filters(self):
        svc.save_question(self.test, choice())
        Test.objects.create(title="English", status=TestStatus.ARCHIVED)
        response = self.client.get(self.url("testing_test_changelist"))
        self.assertContains(response, "Создать тест")
        self.assertContains(response, "1 вопрос")
        self.assertContains(response, "0 попыток")
        self.assertContains(response, "Черновик")
        self.assertEqual([t.title for t in self.client.get(self.url("testing_test_changelist"), {"status": "archived"}).context["tests"]], ["English"])
        self.assertEqual([t.title for t in self.client.get(self.url("testing_test_changelist"), {"q": "Основ"}).context["tests"]], ["IT"])
        self.assertEqual(self.client.get("/admin/tests/").status_code, 302)

    def test_create_lands_inside_the_new_test(self):
        response = self.client.post(self.url("testing_test_add"), {
            "title": "Python exam", "description": "", "level": "medium", "status": "draft",
            "time_limit_minutes": "30", "max_attempts": "2", "passing_score": "70", "_save": "1",
        })
        test = Test.objects.get(title="Python exam")
        self.assertRedirects(response, self.url("testing_test_change", test.pk))
        self.assertEqual((test.time_limit_minutes, test.max_attempts, test.passing_score), (30, 2, 70))
        self.assertFalse(test.is_active)

    def test_create_and_continue_opens_a_new_question(self):
        response = self.client.post(self.url("testing_test_add"), {
            "title": "JS", "level": "easy", "status": "draft", "passing_score": "60", "_continue": "1",
        })
        test = Test.objects.get(title="JS")
        self.assertRedirects(response, self.url("testing_question_add", test.pk))

    def test_create_validation(self):
        response = self.client.post(self.url("testing_test_add"), {"title": "", "level": "medium", "status": "draft", "passing_score": "150"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)


class WorkspaceTests(AdminFixture):
    def test_overview_saves_main_info_and_lists_questions(self):
        svc.save_question(self.test, choice("Первый"))
        response = self.client.get(self.url("testing_test_change", self.test.pk))
        self.assertContains(response, "Основная информация")
        self.assertContains(response, "Первый")
        self.assertContains(response, "Один вариант")
        response = self.client.post(self.url("testing_test_change", self.test.pk), {
            "title": "IT 2", "description": "x", "level": "hard",
        })
        self.assertRedirects(response, self.url("testing_test_change", self.test.pk))
        self.test.refresh_from_db()
        self.assertEqual((self.test.title, self.test.level), ("IT 2", "hard"))

    def test_settings(self):
        response = self.client.post(self.url("testing_test_settings", self.test.pk), {
            "status": "draft", "time_limit_minutes": "45", "max_attempts": "", "passing_score": "55",
            "questions_per_attempt": "", "shuffle_questions": "on", "show_result": "on", "allow_retry": "on",
            "available_from": "2026-10-01T09:00", "available_until": "2026-10-01T08:00",
        })
        self.assertEqual(response.status_code, 200)  # end before start
        self.assertContains(response, "позже даты начала")
        self.client.post(self.url("testing_test_settings", self.test.pk), {
            "status": "draft", "time_limit_minutes": "45", "passing_score": "55", "shuffle_questions": "on",
            "show_result": "on", "allow_retry": "on",
        })
        self.test.refresh_from_db()
        self.assertEqual((self.test.time_limit_minutes, self.test.shuffle_questions, self.test.shuffle_options), (45, True, False))

    def test_publish_needs_questions(self):
        self.client.post(self.url("testing_test_status", self.test.pk, "publish"))
        self.test.refresh_from_db()
        self.assertEqual(self.test.status, TestStatus.DRAFT)
        svc.save_question(self.test, choice())
        self.client.post(self.url("testing_test_status", self.test.pk, "publish"))
        self.test.refresh_from_db()
        self.assertEqual((self.test.status, self.test.is_active), (TestStatus.ACTIVE, True))
        self.client.post(self.url("testing_test_status", self.test.pk, "archive"))
        self.test.refresh_from_db()
        self.assertEqual((self.test.status, self.test.is_active), (TestStatus.ARCHIVED, False))

    def test_status_action_ignores_foreign_next_url_and_bad_ids_404(self):
        svc.save_question(self.test, choice())
        response = self.client.post(self.url("testing_test_status", self.test.pk, "publish"), {"next": "https://evil.example/"})
        self.assertRedirects(response, self.url("testing_test_publish", self.test.pk))
        self.assertEqual(self.client.get("/admin/testing/test/not-a-uuid/change/").status_code, 404)

    def test_stats_and_preview_render(self):
        svc.save_question(self.test, choice())
        self.assertContains(self.client.get(self.url("testing_test_stats", self.test.pk)), "Средний балл")
        preview = self.client.get(self.url("testing_test_preview", self.test.pk))
        self.assertContains(preview, "Предпросмотр")
        self.assertContains(preview, "Вопрос 1 из 1")
        self.assertContains(preview, "data-ex-preview")


class QuestionEditorTests(AdminFixture):
    def post_question(self, data, question=None):
        url = self.url("testing_question_change", self.test.pk, question.pk) if question else self.url("testing_question_add", self.test.pk)
        base = {"points": "1", "difficulty": "medium", "answer_match": "ignore_case", "is_required": "on", "_save": "1"}
        return self.client.post(url, {**base, **data})

    def test_new_question_form_preselects_type(self):
        response = self.client.get(self.url("testing_question_add", self.test.pk), {"type": "code"})
        self.assertContains(response, 'value="code" checked')
        self.assertContains(response, "data-code-editor")

    def test_create_single_choice(self):
        response = self.post_question({
            "question_type": "single_choice", "text": "Какой язык для backend?", "hint": "Не HTML",
            "option_text": ["Python", "HTML", "CSS", ""], "option_id": ["", "", "", ""],
            "option_correct_single": "0", "points": "2",
        })
        question = Question.objects.get()
        self.assertRedirects(response, self.url("testing_test_change", self.test.pk) + f"#question-{question.pk}", fetch_redirect_response=False)
        self.assertEqual((question.points, question.hint, question.options.count()), (2, "Не HTML", 3))
        self.assertEqual(question.options.get(is_correct=True).text, "Python")

    def test_create_multiple_choice(self):
        self.post_question({
            "question_type": "multiple_choice", "text": "Immutable?",
            "option_text": ["tuple", "list", "str"], "option_id": ["", "", ""], "option_correct": ["0", "2"],
        })
        self.assertEqual(sorted(Question.objects.get().options.filter(is_correct=True).values_list("text", flat=True)), ["str", "tuple"])

    def test_create_text(self):
        self.post_question({
            "question_type": "text", "text": "Что такое Python?", "correct_answer": "Язык программирования",
            "accepted_answers": "ЯП\nязык", "answer_match": "exact",
            # left-over option rows of another type are ignored
            "option_text": ["Python", "Java"], "option_id": ["", ""], "option_correct_single": "0",
        })
        question = Question.objects.get()
        self.assertEqual(question.correct_answers, ["Язык программирования", "ЯП", "язык"])
        self.assertEqual((question.answer_match, question.options.count()), ("exact", 0))

    def test_create_code(self):
        self.post_question({
            "question_type": "code", "text": "Напишите функцию суммы", "language": "typescript",
            "starter_code": "function sum(a: number, b: number) {\n}", "test_input": ["2 3", ""], "test_output": ["5", ""],
            "points": "2", "is_required": "",
        })
        question = Question.objects.get()
        self.assertEqual((question.language, question.points, question.is_required), ("typescript", 2, False))
        self.assertEqual(question.code_tests, [{"input": "2 3", "expected_output": "5"}])
        self.assertIn("function sum", question.starter_code)

    def test_validation_errors_keep_the_entered_rows(self):
        response = self.post_question({
            "question_type": "single_choice", "text": "Q", "option_text": ["Только один"], "option_id": [""],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "минимум два варианта")
        self.assertContains(response, 'value="Только один"')
        response = self.post_question({"question_type": "code", "text": "Q", "language": ""})
        self.assertContains(response, "обязателен язык")
        response = self.post_question({"question_type": "text", "text": "Q"})
        self.assertContains(response, "Укажите правильный ответ")
        self.assertFalse(Question.objects.exists())

    def test_edit_and_add_another(self):
        question = svc.save_question(self.test, choice())
        options = list(question.options.order_by("order"))
        response = self.post_question({
            "question_type": "single_choice", "text": "Изменённый", "option_text": ["Язык", "Змея", "Остров"],
            "option_id": [str(options[0].pk), str(options[1].pk), ""], "option_correct_single": "1",
            "_addanother": "1",
        }, question=question)
        self.assertRedirects(response, self.url("testing_question_add", self.test.pk) + "?type=single_choice")
        question.refresh_from_db()
        self.assertEqual(question.text, "Изменённый")
        self.assertEqual(question.options.get(is_correct=True).pk, options[1].pk)
        self.assertEqual(question.options.count(), 3)

    def test_row_actions_and_reorder(self):
        a, b, c = (svc.save_question(self.test, choice(t)) for t in "ABC")
        self.client.post(self.url("testing_question_action", self.test.pk, c.pk, "up"))
        self.client.post(self.url("testing_question_action", self.test.pk, a.pk, "duplicate"))
        self.client.post(self.url("testing_question_action", self.test.pk, b.pk, "delete"))
        self.assertEqual(self._texts(), ["A", "A (копия)", "C"])
        self.assertEqual(list(self.test.questions.order_by("order").values_list("order", flat=True)), [1, 2, 3])
        self.assertEqual(self.client.get(self.url("testing_question_action", self.test.pk, a.pk, "delete")).status_code, 405)

        ids = [str(pk) for pk in self.test.questions.order_by("-order").values_list("pk", flat=True)]
        response = self.client.post(self.url("testing_questions_reorder", self.test.pk), json.dumps({"order": ids}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._texts(), ["C", "A (копия)", "A"])
        response = self.client.post(self.url("testing_questions_reorder", self.test.pk), json.dumps({"order": ids[:1]}), content_type="application/json")
        self.assertEqual(response.status_code, 409)

    def _texts(self):
        return list(self.test.questions.order_by("order").values_list("text", flat=True))
