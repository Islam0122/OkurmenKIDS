"""Question rules, saving, ordering and answer checking (services/)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.testing.models import AnswerMatch, GradingStatus, Question, QuestionType, Test
from apps.testing.services import questions as svc
from apps.testing.services.grading import check_answer
from apps.testing.services.question_rules import CodeTestData, OptionData, QuestionData, validate


def single(text="Что такое Python?", correct=0, n=4):
    return QuestionData(
        question_type=QuestionType.SINGLE_CHOICE, text=text,
        options=[OptionData(f"Вариант {i + 1}", i == correct) for i in range(n)],
    )


class QuestionRulesTests(TestCase):
    def assertInvalid(self, data, field):
        with self.assertRaises(ValidationError) as ctx:
            validate(data)
        self.assertIn(field, ctx.exception.message_dict)

    def test_single_choice_needs_two_options_and_exactly_one_correct(self):
        validate(single())
        self.assertInvalid(single(n=1), "options")
        self.assertInvalid(single(correct=None), "options")
        data = single()
        data.options[1].is_correct = True
        self.assertInvalid(data, "options")

    def test_multiple_choice_allows_several_correct(self):
        data = QuestionData(QuestionType.MULTIPLE_CHOICE, "Immutable?", options=[
            OptionData("tuple", True), OptionData("str", True), OptionData("list", False),
        ])
        self.assertEqual(len(validate(data).options), 3)

    def test_blank_rows_are_dropped_and_duplicates_rejected(self):
        data = single()
        data.options.append(OptionData("   "))
        self.assertEqual(len(validate(data).options), 4)
        data.options.append(OptionData("вариант 1"))
        self.assertInvalid(data, "options")

    def test_text_question_needs_a_correct_answer(self):
        self.assertInvalid(QuestionData(QuestionType.TEXT, "Что такое Python?"), "correct_answers")
        ok = validate(QuestionData(QuestionType.TEXT, "Q", correct_answers=["Язык", " ", "Язык"]))
        self.assertEqual(ok.correct_answers, ["Язык"])

    def test_text_and_code_questions_have_no_options(self):
        self.assertInvalid(QuestionData(QuestionType.TEXT, "Q", correct_answers=["a"], options=[OptionData("x")]), "options")

    def test_code_question_needs_language_and_expected_outputs(self):
        self.assertInvalid(QuestionData(QuestionType.CODE, "Sum"), "language")
        self.assertInvalid(
            QuestionData(QuestionType.CODE, "Sum", language="python", code_tests=[CodeTestData("2 3", "")]),
            "code_tests",
        )
        ok = validate(QuestionData(QuestionType.CODE, "Sum", language="python",
                                   code_tests=[CodeTestData("2 3", "5"), CodeTestData("", "")]))
        self.assertEqual(len(ok.code_tests), 1)

    def test_question_text_is_required(self):
        self.assertInvalid(single(text="  "), "text")


class SaveQuestionTests(TestCase):
    def setUp(self):
        self.test = Test.objects.create(title="Python")

    def test_create_numbers_questions_in_order(self):
        first = svc.save_question(self.test, single("Q1"))
        second = svc.save_question(self.test, single("Q2"), points=3, is_required=False, hint="h")
        self.assertEqual((first.order, second.order), (1, 2))
        self.assertEqual((second.points, second.is_required, second.hint), (3, False, "h"))
        self.assertEqual(list(first.options.values_list("order", flat=True)), [1, 2, 3, 4])

    def test_options_keep_their_ids_on_edit(self):
        question = svc.save_question(self.test, single())
        kept = question.options.order_by("order")[1]
        data = single(correct=1, n=2)
        data.options[1] = OptionData("Новый текст", True, id=str(kept.pk))
        svc.save_question(self.test, data, question=question)
        self.assertEqual(question.options.count(), 2)
        kept.refresh_from_db()
        self.assertEqual((kept.text, kept.is_correct, kept.order), ("Новый текст", True, 2))

    def test_switching_type_clears_data_of_the_old_type(self):
        question = svc.save_question(self.test, single())
        svc.save_question(self.test, QuestionData(QuestionType.TEXT, "Q", correct_answers=["Да"]), question=question)
        question.refresh_from_db()
        self.assertEqual(question.options.count(), 0)
        self.assertEqual(question.correct_answers, ["Да"])
        svc.save_question(
            self.test,
            QuestionData(QuestionType.CODE, "Sum", language="python", code_tests=[CodeTestData("2 3", "5")]),
            question=question, starter_code="def f(a, b):\n    pass",
        )
        question.refresh_from_db()
        self.assertEqual(question.correct_answers, [])
        self.assertEqual(question.code_tests, [{"input": "2 3", "expected_output": "5"}])
        self.assertIn("def f", question.starter_code)

    def test_duplicate_goes_right_after_the_original(self):
        a = svc.save_question(self.test, single("A"))
        b = svc.save_question(self.test, single("B"))
        copy = svc.duplicate_question(a)
        order = list(self.test.questions.order_by("order").values_list("text", flat=True))
        self.assertEqual(order, ["A", "A (копия)", "B"])
        self.assertEqual(copy.options.count(), 4)
        self.assertEqual(svc.duplicate_question(a).text, "A (копия 2)")
        b.refresh_from_db()
        self.assertEqual(b.order, 4)

    def test_move_and_reorder(self):
        a, b, c = (svc.save_question(self.test, single(t)) for t in "ABC")
        svc.move_question(c, "up")
        self.assertEqual(self._texts(), ["A", "C", "B"])
        svc.move_question(a, "up")  # already first: no-op
        self.assertEqual(self._texts(), ["A", "C", "B"])
        self.assertTrue(svc.reorder_questions(self.test, [str(b.pk), str(a.pk), str(c.pk)]))
        self.assertEqual(self._texts(), ["B", "A", "C"])
        self.assertFalse(svc.reorder_questions(self.test, [str(b.pk), str(a.pk)]))

    def _texts(self):
        return list(self.test.questions.order_by("order").values_list("text", flat=True))


class CheckAnswerTests(TestCase):
    def setUp(self):
        self.test = Test.objects.create(title="Checks")

    def test_single_and_multiple_choice(self):
        q = svc.save_question(self.test, single())
        right, wrong = q.options.get(is_correct=True), q.options.filter(is_correct=False).first()
        self.assertEqual(check_answer(q, "", [str(right.pk)]), (True, GradingStatus.AUTO))
        self.assertEqual(check_answer(q, "", [str(wrong.pk)]), (False, GradingStatus.AUTO))
        self.assertEqual(check_answer(q, "", [str(right.pk), str(wrong.pk)]), (False, GradingStatus.AUTO))

        m = svc.save_question(self.test, QuestionData(QuestionType.MULTIPLE_CHOICE, "M", options=[
            OptionData("a", True), OptionData("b", True), OptionData("c", False)]))
        a, b, c = m.options.order_by("order")
        self.assertTrue(check_answer(m, "", [str(a.pk), str(b.pk)])[0])
        self.assertFalse(check_answer(m, "", [str(a.pk)])[0])

    def test_text_exact_and_case_insensitive(self):
        q = svc.save_question(self.test, QuestionData(QuestionType.TEXT, "Что такое Python?",
                                                      correct_answers=["Язык программирования", "ЯП"]))
        self.assertTrue(check_answer(q, "  язык   ПРОГРАММИРОВАНИЯ ")[0])
        self.assertTrue(check_answer(q, "яп")[0])
        self.assertFalse(check_answer(q, "Змея")[0])
        q.answer_match = AnswerMatch.EXACT
        self.assertFalse(check_answer(q, "язык программирования")[0])
        self.assertTrue(check_answer(q, "Язык  программирования")[0])

    def test_code_and_legacy_text_go_to_review(self):
        code = Question.objects.create(test=self.test, text="Sum", question_type=QuestionType.CODE, language="python")
        self.assertEqual(check_answer(code, "def f(): pass"), (None, GradingStatus.PENDING))
        self.assertEqual(check_answer(code, "   "), (False, GradingStatus.AUTO))
        legacy = Question.objects.create(test=self.test, text="Explain", question_type=QuestionType.TEXT)
        self.assertEqual(check_answer(legacy, "Because"), (None, GradingStatus.PENDING))
