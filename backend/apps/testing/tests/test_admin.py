"""Django admin for tests/questions (apps/testing/admin.py)."""
from __future__ import annotations

import json

from django.test import TestCase
from django.urls import reverse

from apps.testing.models import Question, QuestionOption, Test
from apps.testing.templatetags.question_bank import question_count_label
from apps.users.models import User


class TestingAdminFixture(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.client.force_login(self.admin)
        self.test = Test.objects.create(title="Python first month", level="easy")
        self.questions = [
            Question.objects.create(test=self.test, text=f"Q{i}", order=i) for i in range(1, 4)
        ]

    def option_formset(self, rows, total_initial=0):
        data = {
            "options-TOTAL_FORMS": str(len(rows)),
            "options-INITIAL_FORMS": str(total_initial),
            "options-MIN_NUM_FORMS": "0",
            "options-MAX_NUM_FORMS": "1000",
        }
        for i, (text, correct, order) in enumerate(rows):
            data[f"options-{i}-text"] = text
            data[f"options-{i}-order"] = str(order)
            if correct:
                data[f"options-{i}-is_correct"] = "on"
        return data


class TestAdminListTests(TestingAdminFixture):
    def test_changelist_shows_badges_and_question_count(self):
        Test.objects.create(title="Empty test", level="hard", is_active=False)
        response = self.client.get(reverse("admin:testing_test_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3 вопроса")
        self.assertContains(response, "0 вопросов")
        self.assertContains(response, "Лёгкий")
        self.assertContains(response, "Неактивен")
        self.assertContains(response, "Добавить тест")

    def test_filters_and_search(self):
        Test.objects.create(title="JS final", level="hard", is_active=False, description="javascript")
        url = reverse("admin:testing_test_changelist")
        self.assertEqual(self.client.get(url, {"status": "inactive"}).context["cl"].result_count, 1)
        self.assertEqual(self.client.get(url, {"level__exact": "easy"}).context["cl"].result_count, 1)
        self.assertEqual(self.client.get(url, {"q": "javascript"}).context["cl"].result_count, 1)

    def test_activate_and_deactivate_actions(self):
        url = reverse("admin:testing_test_changelist")
        self.client.post(url, {"action": "deactivate_tests", "_selected_action": [self.test.pk]})
        self.test.refresh_from_db()
        self.assertFalse(self.test.is_active)
        self.client.post(url, {"action": "activate_tests", "_selected_action": [self.test.pk]})
        self.test.refresh_from_db()
        self.assertTrue(self.test.is_active)

    def test_question_count_label_pluralises(self):
        self.assertEqual(question_count_label(0), "0 вопросов")
        self.assertEqual(question_count_label(1), "1 вопрос")
        self.assertEqual(question_count_label(3), "3 вопроса")
        self.assertEqual(question_count_label(155), "155 вопросов")
        self.assertEqual(question_count_label(111), "111 вопросов")


class TestAdminChangePageTests(TestingAdminFixture):
    def test_change_page_lists_questions(self):
        response = self.client.get(reverse("admin:testing_test_change", args=[self.test.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Тест: Python first month")
        self.assertContains(response, 'id="questions"')
        self.assertEqual([q.pk for q in response.context["test_questions"]], [q.pk for q in self.questions])
        self.assertContains(response, f"?test={self.test.pk}&amp;_from=test")

    def test_reorder_questions(self):
        url = reverse("admin:testing_test_reorder_questions", args=[self.test.pk])
        new_order = [str(self.questions[2].pk), str(self.questions[0].pk), str(self.questions[1].pk)]
        response = self.client.post(url, json.dumps({"order": new_order}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        orders = {str(q.pk): q.order for q in Question.objects.filter(test=self.test)}
        self.assertEqual([orders[i] for i in new_order], [1, 2, 3])

    def test_reorder_rejects_stale_or_foreign_lists(self):
        url = reverse("admin:testing_test_reorder_questions", args=[self.test.pk])
        other = Question.objects.create(test=Test.objects.create(title="Other"), text="X")
        partial = [str(self.questions[0].pk), str(other.pk)]
        response = self.client.post(url, json.dumps({"order": partial}), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_reorder_requires_change_permission(self):
        staff = User.objects.create_user(username="viewer", email="v@okurmen.kg", password="x", is_staff=True)
        self.client.force_login(staff)
        url = reverse("admin:testing_test_reorder_questions", args=[self.test.pk])
        response = self.client.post(url, json.dumps({"order": []}), content_type="application/json")
        self.assertEqual(response.status_code, 403)


class QuestionAdminTests(TestingAdminFixture):
    def post_question(self, extra, query=""):
        data = {"test": str(self.test.pk), "text": "Что такое Python?", "difficulty": "easy",
                "language": "python", "order": "4"}
        data.update(extra)
        return self.client.post(reverse("admin:testing_question_add") + query, data)

    def test_add_form_prefills_test_and_next_order(self):
        response = self.client.get(reverse("admin:testing_question_add"), {"test": self.test.pk, "_from": "test"})
        self.assertEqual(response.status_code, 200)
        initial = response.context["adminform"].form.initial
        self.assertEqual(initial["order"], 4)
        self.assertEqual(response.context["parent_test"], self.test)

    def test_single_choice_with_options_redirects_back_to_test(self):
        data = {"question_type": "single_choice", "_save": "1"}
        data.update(self.option_formset([("Python", True, 1), ("Java", False, 2)]))
        response = self.post_question(data, query="?_from=test")
        self.assertRedirects(
            response, reverse("admin:testing_test_change", args=[self.test.pk]) + "#questions",
            fetch_redirect_response=False,
        )
        question = Question.objects.get(text="Что такое Python?")
        self.assertEqual(question.options.count(), 2)

    def test_single_choice_needs_exactly_one_correct_option(self):
        data = {"question_type": "single_choice"}
        data.update(self.option_formset([("Python", True, 1), ("Java", True, 2)]))
        response = self.post_question(data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "только один вариант")

        data = {"question_type": "single_choice"}
        data.update(self.option_formset([("Python", False, 1), ("Java", False, 2)]))
        self.assertContains(self.post_question(data), "хотя бы один правильный")

    def test_text_question_rejects_options_and_saves_without(self):
        data = {"question_type": "text"}
        data.update(self.option_formset([("Python", True, 1)]))
        self.assertContains(self.post_question(data), "варианты ответа не нужны")

        data = {"question_type": "text"}
        data.update(self.option_formset([("", False, 1)]))
        response = self.post_question(data)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuestionOption.objects.exists())

    def test_code_question_requires_language(self):
        data = {"question_type": "code", "language": ""}
        data.update(self.option_formset([]))
        response = self.post_question(data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "обязателен язык")

    def test_changelist_filters_and_difficulty_action(self):
        url = reverse("admin:testing_question_changelist")
        response = self.client.get(url, {"q": "Python first"})
        self.assertEqual(response.context["cl"].result_count, 3)
        self.client.post(url, {"action": "set_difficulty_hard",
                               "_selected_action": [q.pk for q in self.questions[:2]]})
        self.assertEqual(Question.objects.filter(difficulty="hard").count(), 2)
