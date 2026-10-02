"""Optional images on tests, questions and answer options — stored as URLs
only (no upload), http(s) only, shown to students only when set."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.testing.models import QuestionOption, QuestionType, SessionType, StudentAttempt, Test, TestSession, TestStatus
from apps.testing.services import questions as svc
from apps.testing.services.question_rules import OptionData, QuestionData, validate
from apps.testing.templatetags.question_bank import safe_image_url
from apps.users.models import User

IMG = "https://cdn.example.com/test/python-loop.jpg"
BAD_URLS = ["javascript:alert(1)", "data:image/png;base64,AAAA", "file:///etc/passwd", "ftp://example.com/a.png", "not a url"]


class ImageUrlRulesTests(TestCase):
    def setUp(self):
        self.test = Test.objects.create(title="Images")

    def test_models_accept_only_http_and_https(self):
        for url in ("https://example.com/a.png", "http://example.com/a.png"):
            Test(title=f"T {url}", image_url=url).full_clean()
        for url in BAD_URLS:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                Test(title="Bad", image_url=url).full_clean()

    def test_images_are_optional_everywhere(self):
        Test(title="No image").full_clean()
        question = svc.save_question(self.test, QuestionData(
            QuestionType.SINGLE_CHOICE, "Без картинок", options=[OptionData("a", True), OptionData("b")]))
        self.assertEqual(question.image_url, "")
        self.assertEqual(set(question.options.values_list("image_url", flat=True)), {""})

    def test_question_and_option_images_are_validated(self):
        with self.assertRaises(ValidationError) as ctx:
            validate(QuestionData(QuestionType.TEXT, "Q", image_url="javascript:alert(1)", correct_answers=["a"]))
        self.assertIn("image_url", ctx.exception.message_dict)
        with self.assertRaises(ValidationError) as ctx:
            validate(QuestionData(QuestionType.SINGLE_CHOICE, "Q", options=[
                OptionData("a", True, image_url="data:image/png;base64,AA"), OptionData("b")]))
        self.assertIn("Вариант 1", ctx.exception.message_dict["options"][0])

    def test_picture_only_options(self):
        question = svc.save_question(self.test, QuestionData(
            QuestionType.SINGLE_CHOICE, "Какой логотип у Python?", image_url=IMG,
            options=[OptionData("", True, image_url="https://ex.com/py.png"), OptionData("", image_url="https://ex.com/js.png")],
        ))
        self.assertEqual(question.image_url, IMG)
        self.assertEqual(list(question.options.values_list("text", "image_url")),
                         [("", "https://ex.com/py.png"), ("", "https://ex.com/js.png")])
        copy = svc.duplicate_question(question)
        self.assertEqual((copy.image_url, copy.options.first().image_url), (IMG, "https://ex.com/py.png"))

    def test_safe_image_url_filter(self):
        self.assertEqual(safe_image_url(IMG), IMG)
        for url in BAD_URLS[:3] + ["", None]:
            self.assertEqual(safe_image_url(url), "")


class AdminImageTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser(username="root", email="r@okurmen.kg", password="x"))
        self.test = Test.objects.create(title="IT")

    def test_test_image_in_info_form(self):
        url = reverse("admin:testing_test_change", args=[self.test.pk])
        response = self.client.post(url, {"title": "IT", "level": "medium", "image_url": "javascript:alert(1)"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'src="javascript')
        self.client.post(url, {"title": "IT", "level": "medium", "image_url": IMG})
        self.test.refresh_from_db()
        self.assertEqual(self.test.image_url, IMG)
        page = self.client.get(url)
        self.assertContains(page, "data-image-url-field")
        self.assertContains(page, f'src="{IMG}"')
        self.client.post(url, {"title": "IT", "level": "medium", "image_url": ""})
        self.test.refresh_from_db()
        self.assertEqual(self.test.image_url, "")

    def test_question_editor_saves_question_and_option_images(self):
        response = self.client.post(reverse("admin:testing_question_add", args=[self.test.pk]), {
            "question_type": "single_choice", "text": "Выберите логотип Python", "image_url": IMG,
            "option_text": ["", "JavaScript"], "option_id": ["", ""],
            "option_image": ["https://ex.com/py.png", ""], "option_correct_single": "0",
            "points": "1", "difficulty": "medium", "answer_match": "ignore_case", "is_required": "on",
        })
        self.assertEqual(response.status_code, 302)
        question = self.test.questions.get()
        self.assertEqual(question.image_url, IMG)
        right = question.options.get(is_correct=True)
        self.assertEqual((right.text, right.image_url), ("", "https://ex.com/py.png"))
        page = self.client.get(reverse("admin:testing_question_change", args=[self.test.pk, question.pk]))
        self.assertContains(page, 'value="https://ex.com/py.png"')

    def test_question_editor_rejects_bad_scheme(self):
        response = self.client.post(reverse("admin:testing_question_add", args=[self.test.pk]), {
            "question_type": "text", "text": "Q", "image_url": "javascript:alert(1)", "correct_answer": "a",
            "points": "1", "difficulty": "medium", "answer_match": "ignore_case",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "http:// или https://")
        self.assertNotContains(response, 'src="javascript')
        self.assertFalse(self.test.questions.exists())


class ApiImageTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_superuser(username="root", email="r@okurmen.kg", password="x"))
        self.test = Test.objects.create(title="IT")

    def test_image_url_or_null(self):
        data = self.api.get(f"/api/v1/tests/{self.test.pk}/").data
        self.assertIsNone(data["image_url"])
        data = self.api.patch(f"/api/v1/tests/{self.test.pk}/", {"image_url": IMG}, format="json").data
        self.assertEqual(data["image_url"], IMG)
        data = self.api.patch(f"/api/v1/tests/{self.test.pk}/", {"image_url": None}, format="json").data
        self.assertIsNone(data["image_url"])
        bad = self.api.patch(f"/api/v1/tests/{self.test.pk}/", {"image_url": "javascript:alert(1)"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_question_and_options(self):
        response = self.api.post(f"/api/v1/tests/{self.test.pk}/questions/", {
            "question_type": "single_choice", "text": "Какой язык?", "image_url": IMG,
            "options": [{"text": "", "image_url": "https://ex.com/py.png", "is_correct": True}, {"text": "Java"}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["image_url"], IMG)
        self.assertEqual([o["image_url"] for o in response.data["options"]], ["https://ex.com/py.png", None])
        plain = self.api.post(f"/api/v1/tests/{self.test.pk}/questions/", {
            "question_type": "text", "text": "Что такое Python?", "correct_answers": ["Язык"],
        }, format="json")
        self.assertIsNone(plain.data["image_url"])
        bad = self.api.post(f"/api/v1/tests/{self.test.pk}/questions/", {
            "question_type": "single_choice", "text": "Q",
            "options": [{"text": "a", "is_correct": True, "image_url": "file:///etc/passwd"}, {"text": "b"}],
        }, format="json")
        self.assertEqual(bad.status_code, 400)


class StudentImageTests(TestCase):
    def setUp(self):
        self.test = Test.objects.create(title="Logo", status=TestStatus.ACTIVE, image_url="https://ex.com/cover.png")
        self.with_image = svc.save_question(self.test, QuestionData(
            QuestionType.SINGLE_CHOICE, "Какой логотип у Python?", image_url=IMG,
            options=[OptionData("", True, image_url="https://ex.com/py.png"), OptionData("JavaScript")]))
        self.code = svc.save_question(self.test, QuestionData(
            QuestionType.CODE, "Реализуйте структуру с картинки", language="python", image_url="https://ex.com/task.png"))
        self.plain = svc.save_question(self.test, QuestionData(
            QuestionType.TEXT, "Без картинки?", correct_answers=["да"]))
        self.session = TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING)
        self.session.start()

    def test_images_show_only_where_set(self):
        join = self.client.get(reverse("testing_public_join"), {"key": self.session.key})
        self.assertContains(join, 'src="https://ex.com/cover.png"')
        self.client.post(reverse("testing_public_join"), {"key": self.session.key, "student_name": "A", "start": "1"})
        attempt = StudentAttempt.objects.get()
        page = self.client.get(reverse("testing_public_take", args=[attempt.pk])).content.decode()
        # one figure per question that has an image, none for the plain one
        self.assertEqual(page.count('class="ex-figure"'), 2)
        self.assertIn(f'src="{IMG}"', page)
        self.assertIn('src="https://ex.com/py.png"', page)
        self.assertIn('alt="Вариант 1"', page)  # picture-only option is still labelled
        # the image is above the question text, and above the code editor
        self.assertLess(page.index(IMG), page.index("Какой логотип у Python?"))
        self.assertLess(page.index("https://ex.com/task.png"), page.index("data-code-editor"))

    def test_preview_shows_images(self):
        self.client.force_login(User.objects.create_superuser(username="root", email="r@okurmen.kg", password="x"))
        preview = self.client.get(reverse("admin:testing_test_preview", args=[self.test.pk]))
        self.assertContains(preview, f'src="{IMG}"')

    def test_option_without_text_is_saved_as_blank(self):
        option = QuestionOption.objects.get(image_url="https://ex.com/py.png")
        self.assertEqual(option.text, "")
