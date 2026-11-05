"""Rule-based recommendation engine, WhatsApp texts and page layout."""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.reports.services import layout, recommendations, text_generator

from .base import OctoberFixture


def facts(**values):
    base = {"attendance_rate": None, "homework_rate": None, "average_score": None, "test_average": None,
            "status": None, "attendance_change": None, "homework_change": None, "score_change": None,
            "test_change": None}
    return {**base, **values}


def keys(result, section):
    return [item["key"] for item in result[section]]


def texts(result, section):
    return [item["text"] for item in result[section]]


class RuleTests(SimpleTestCase):
    def build(self, scope="student", language="ru", **values):
        return recommendations.build(facts(**values), scope=scope, language=language)

    def test_low_attendance(self):
        result = self.build(attendance_rate=65)
        self.assertIn("Необходимо обратить внимание на регулярность посещения занятий.", texts(result, "attention"))
        self.assertIn("parents_attendance", keys(result, "parents"))

    def test_excellent_attendance(self):
        result = self.build(attendance_rate=96)
        self.assertEqual(texts(result, "strengths")[0], "Отличная посещаемость! Ученик регулярно посещает занятия.")
        self.assertNotIn("attendance_low", keys(result, "attention"))

    def test_homework_score_and_tests(self):
        result = self.build(homework_rate=50, average_score=4.5, test_average=55)
        attention = texts(result, "attention")
        self.assertIn("Рекомендуется уделить больше внимания выполнению домашних заданий.", attention)
        self.assertIn("Рекомендуется повторить пройденные темы и закрепить материал.", attention)
        self.assertIn("Необходимо дополнительно подготовиться к тестированию.", attention)
        self.assertIn("Отличные академические результаты.", texts(self.build(average_score=9.2), "strengths"))

    def test_thresholds_are_exact(self):
        self.assertNotIn("attendance_low", keys(self.build(attendance_rate=70), "attention"))
        self.assertIn("attendance_excellent", keys(self.build(attendance_rate=95), "strengths"))
        self.assertNotIn("homework_low", keys(self.build(homework_rate=60), "attention"))
        self.assertIn("score_excellent", keys(self.build(average_score=9), "strengths"))
        self.assertNotIn("score_low", keys(self.build(average_score=5), "attention"))
        self.assertNotIn("tests_low", keys(self.build(test_average=60), "attention"))

    def test_missing_metric_produces_no_statement(self):
        # Only homework is known: nothing may be said about attendance, scores or tests.
        result = self.build(homework_rate=95)
        every_key = keys(result, "strengths") + keys(result, "attention") + keys(result, "parents")
        for prefix in ("attendance", "score", "tests", "parents_attendance", "parents_tests", "parents_score"):
            self.assertFalse([key for key in every_key if key.startswith(prefix)], prefix)
        self.assertEqual(keys(result, "attention"), ["attention_default"])

    def test_no_data_at_all(self):
        for language, text in (("ru", "Недостаточно данных за выбранный период."), ("ky", "Тандалган мезгил боюнча маалымат жетишсиз.")):
            result = self.build(language=language)
            for section in recommendations.SECTIONS:
                self.assertEqual(texts(result, section), [text])

    def test_every_section_has_a_true_fallback(self):
        result = self.build(attendance_rate=80, homework_rate=80, average_score=7, test_average=75)
        self.assertEqual(keys(result, "attention"), ["attendance_medium"])
        self.assertTrue(result["strengths"])
        self.assertTrue(result["parents"])

    def test_comparison_rules(self):
        result = self.build(attendance_rate=90, attendance_change=12.5, score_change=-1.5)
        self.assertIn("Посещаемость выросла на 12,5 п.п. по сравнению с прошлым периодом.", texts(result, "strengths"))
        self.assertIn("Средний балл снизился на 1,5.", texts(result, "attention"))

    def test_kyrgyz(self):
        result = self.build(language="ky", attendance_rate=65, homework_rate=50, average_score=9.5, test_average=50)
        self.assertIn("Сабактарга үзгүлтүксүз катышууга көңүл буруу зарыл.", texts(result, "attention"))
        self.assertIn("Үй тапшырмаларын аткарууга көбүрөөк көңүл буруу сунушталат.", texts(result, "attention"))
        self.assertIn("Эң сонун окуу жыйынтыктары.", texts(result, "strengths"))
        self.assertIn("Тестирлөөгө кошумча даярдануу зарыл.", texts(result, "attention"))

    def test_group_scope_counts_with_plurals(self):
        group = recommendations.build({**facts(attendance_rate=90), "excellent_count": 3, "attention_count": 1},
                                      scope="group", language="ru")
        self.assertIn("3 ученика с отличными результатами.", texts(group, "strengths"))
        self.assertIn("1 ученику требуется дополнительное внимание.", texts(group, "attention"))
        five = recommendations.build({**facts(attendance_rate=90), "excellent_count": 5, "attention_count": 0},
                                     scope="group", language="ru")
        self.assertIn("5 учеников с отличными результатами.", texts(five, "strengths"))
        # Student-only rules never appear in a group report.
        self.assertNotIn("parents_praise", keys(self.build(scope="group", attendance_rate=99, status="excellent"), "parents"))

    def test_at_most_four_items_per_section(self):
        result = self.build(attendance_rate=40, homework_rate=10, average_score=2, test_average=10,
                            attendance_change=-30, homework_change=-40, score_change=-3)
        for section in recommendations.SECTIONS:
            self.assertLessEqual(len(result[section]), recommendations.MAX_ITEMS)


class TextTests(OctoberFixture):
    options = {"include_table": True, "include_group_stats": True, "include_recommendations": True, "include_comparison": True}

    def test_group_message_ru(self):
        text = text_generator.group_message(self.data(), language="ru", options=self.options)
        self.assertTrue(text.startswith("Уважаемые родители!"))
        self.assertIn("ежемесячный отчёт", text)
        self.assertIn("*PY-01*", text)
        self.assertIn("01.10.2026 — 31.10.2026", text)
        for item in ("Посещаемость", "Выполнение домашних заданий", "Средние оценки", "Результаты тестирования", "Индивидуальный прогресс"):
            self.assertIn(f"• {item}", text)
        self.assertIn("Средняя посещаемость: 66,7%", text)
        self.assertIn("Средний балл: 7,5 / 10", text)
        self.assertIn("Результаты тестов: Нет данных", text)
        self.assertIn("Благодарим вас за сотрудничество", text)
        # The group chat message never names a student.
        self.assertNotIn("Анна", text)

    def test_group_message_options(self):
        text = text_generator.group_message(
            self.data(), language="ru",
            options={**self.options, "include_group_stats": False, "include_recommendations": False, "include_table": False},
        )
        self.assertNotIn("Коротко о группе", text)
        self.assertNotIn("Рекомендации родителям", text)
        self.assertNotIn("Индивидуальный прогресс", text)

    def test_group_message_ky(self):
        text = text_generator.group_message(self.data(), language="ky", options=self.options)
        self.assertTrue(text.startswith("Саламатсыздарбы, урматтуу ата-энелер!"))
        self.assertIn("Тест жыйынтыктары: Маалымат жок", text)
        self.assertIn("рахмат", text)

    def test_student_message(self):
        data = self.data()
        text = text_generator.student_message(data, self.entry(data, self.anna), language="ru", options=self.options)
        self.assertIn("*Анна Алиева*", text)
        self.assertIn("Посещаемость: 100% (3 из 3 занятий)", text)
        self.assertIn("Домашние задания: 100% (2 из 2)", text)
        self.assertIn("Тесты: Нет данных", text)
        self.assertIn("посещаемость +50 п.п.", text)
        self.assertIn("средний балл +2", text)
        self.assertIn("Сильные стороны", text)
        self.assertNotIn("Бек", text)

    def test_student_message_without_comparison(self):
        data = self.data()
        text = text_generator.student_message(
            data, self.entry(data, self.anna), language="ky", options={**self.options, "include_comparison": False},
        )
        self.assertNotIn("салыштырганда", text)
        self.assertIn("Катышуу: 100%", text)


class LayoutTests(SimpleTestCase):
    def rows(self, n):
        return [{"no": i} for i in range(1, n + 1)]

    def test_small_group_fits_one_page(self):
        pages = layout.paginate(self.rows(10), table=True, kpis=True, sections=True)
        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0].show_kpis and pages[0].show_sections)

    def test_large_group_gets_more_pages_not_smaller_rows(self):
        for n in (11, 25, 40, 80):
            pages = layout.paginate(self.rows(n), table=True, kpis=True, sections=True)
            self.assertGreater(len(pages), 1)
            self.assertEqual(sum(len(page.students) for page in pages), n)
            self.assertEqual([row["no"] for page in pages for row in page.students], list(range(1, n + 1)))
            self.assertTrue(pages[0].show_kpis)
            self.assertFalse(any(page.show_kpis for page in pages[1:]))
            self.assertEqual([page.show_sections for page in pages], [False] * (len(pages) - 1) + [True])
            for page in pages:
                capacity = layout._capacity(first=page.first, kpis=page.show_kpis, sections=page.show_sections)
                self.assertLessEqual(len(page.students), capacity)
            # Pages before the last one are filled, not spread thin.
            for page in pages[:-2]:
                self.assertEqual(len(page.students), layout._capacity(first=page.first, kpis=page.show_kpis, sections=False))

    def test_table_that_fits_one_page_is_not_split(self):
        fits = layout._capacity(first=True, kpis=True, sections=False)
        pages = layout.paginate(self.rows(fits), table=True, kpis=True, sections=True)
        self.assertEqual([len(page.students) for page in pages], [fits, 0])
        self.assertEqual([page.show_sections for page in pages], [False, True])
        # Without sections there is nothing to move: one page.
        self.assertEqual(len(layout.paginate(self.rows(fits), table=True, kpis=True, sections=False)), 1)

    def test_without_table(self):
        pages = layout.paginate(self.rows(30), table=False, kpis=True, sections=True)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].students, [])
