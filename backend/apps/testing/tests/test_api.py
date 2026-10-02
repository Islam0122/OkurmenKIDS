"""Test bank REST API: /api/v1/tests/ and nested /questions/."""
from __future__ import annotations

from rest_framework.test import APITestCase

from apps.testing.models import Question, Test, TestStatus
from apps.users.models import User


class TestsApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.client.force_authenticate(self.admin)

    def create_test(self, **data):
        response = self.client.post("/api/v1/tests/", {"title": "IT", "level": "medium", **data}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def add_question(self, test_id, payload):
        return self.client.post(f"/api/v1/tests/{test_id}/questions/", payload, format="json")

    def test_permissions(self):
        teacher = User.objects.create_user(username="t", email="t@okurmen.kg", password="x", role=User.Role.TEACHER)
        self.client.force_authenticate(teacher)
        self.assertEqual(self.client.get("/api/v1/tests/").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/tests/").status_code, 401)

    def test_test_crud(self):
        test = self.create_test(description="Основы", time_limit_minutes=30, passing_score=70)
        self.assertEqual((test["status"], test["question_count"]), (TestStatus.DRAFT, None))
        listing = self.client.get("/api/v1/tests/").data
        self.assertEqual(listing["results"][0]["question_count"], 0)
        detail = self.client.patch(f"/api/v1/tests/{test['id']}/", {"title": "IT 2", "shuffle_questions": True}, format="json")
        self.assertEqual((detail.data["title"], detail.data["shuffle_questions"]), ("IT 2", True))
        publish = self.client.patch(f"/api/v1/tests/{test['id']}/", {"status": "active"}, format="json")
        self.assertEqual(publish.status_code, 400)  # no questions yet
        self.assertEqual(self.client.delete(f"/api/v1/tests/{test['id']}/").status_code, 204)
        self.assertFalse(Test.objects.exists())

    def test_each_question_type(self):
        test_id = self.create_test()["id"]
        single = self.add_question(test_id, {
            "question_type": "single_choice", "text": "Backend?", "points": 2,
            "options": [{"text": "Python", "is_correct": True}, {"text": "HTML"}],
        })
        self.assertEqual(single.status_code, 201, single.data)
        self.assertEqual([o["text"] for o in single.data["options"]], ["Python", "HTML"])
        multi = self.add_question(test_id, {
            "question_type": "multiple_choice", "text": "Immutable?",
            "options": [{"text": "tuple", "is_correct": True}, {"text": "str", "is_correct": True}, {"text": "list"}],
        })
        self.assertEqual(multi.status_code, 201, multi.data)
        text = self.add_question(test_id, {"question_type": "text", "text": "Python?", "correct_answers": ["Язык"], "answer_match": "exact"})
        self.assertEqual(text.status_code, 201, text.data)
        code = self.add_question(test_id, {
            "question_type": "code", "text": "Sum", "language": "python", "starter_code": "def f(a, b):\n    pass",
            "code_tests": [{"input": "2 3", "expected_output": "5"}],
        })
        self.assertEqual(code.status_code, 201, code.data)
        listing = self.client.get(f"/api/v1/tests/{test_id}/questions/").data
        self.assertEqual([q["order"] for q in listing], [1, 2, 3, 4])
        self.assertEqual(self.client.patch(f"/api/v1/tests/{test_id}/", {"status": "active"}, format="json").status_code, 200)

    def test_question_validation(self):
        test_id = self.create_test()["id"]
        response = self.add_question(test_id, {"question_type": "single_choice", "text": "Q", "options": [
            {"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("options", response.data)
        self.assertEqual(self.add_question(test_id, {"question_type": "code", "text": "Q"}).status_code, 400)
        self.assertEqual(self.add_question(test_id, {"question_type": "text", "text": "Q"}).status_code, 400)

    def test_patch_delete_and_reorder(self):
        test_id = self.create_test()["id"]
        ids = [
            self.add_question(test_id, {"question_type": "text", "text": f"Q{i}", "correct_answers": ["a"]}).data["id"]
            for i in range(3)
        ]
        url = f"/api/v1/tests/{test_id}/questions/{ids[0]}/"
        patched = self.client.patch(url, {"points": 5, "correct_answers": ["b", "c"]}, format="json")
        self.assertEqual((patched.data["points"], patched.data["correct_answers"]), (5, ["b", "c"]))
        switched = self.client.patch(url, {"question_type": "single_choice", "options": [{"text": "x", "is_correct": True}, {"text": "y"}]}, format="json")
        self.assertEqual(switched.status_code, 200, switched.data)
        self.assertEqual(switched.data["correct_answers"], [])

        reordered = self.client.post(f"/api/v1/tests/{test_id}/questions/reorder/", {"order": list(reversed(ids))}, format="json")
        self.assertEqual([q["id"] for q in reordered.data], list(reversed(ids)))
        self.assertEqual(self.client.post(f"/api/v1/tests/{test_id}/questions/reorder/", {"order": ids[:1]}, format="json").status_code, 409)

        self.assertEqual(self.client.delete(f"/api/v1/tests/{test_id}/questions/{ids[1]}/").status_code, 204)
        self.assertEqual(list(Question.objects.order_by("order").values_list("order", flat=True)), [1, 2])

    def test_questions_are_scoped_to_their_test(self):
        a = self.create_test(title="A")["id"]
        b = self.create_test(title="B")["id"]
        q = self.add_question(a, {"question_type": "text", "text": "Q", "correct_answers": ["x"]}).data["id"]
        self.assertEqual(self.client.get(f"/api/v1/tests/{b}/questions/{q}/").status_code, 404)
