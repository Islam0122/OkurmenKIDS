"""PNG generation (Playwright) and the HTML it is rendered from.

The rendering tests need a headless Chromium (``playwright install chromium``
or ``REPORTS_CHROMIUM_EXECUTABLE``); without one they are skipped. The HTML
and failure-path tests always run.
"""
from __future__ import annotations

import io
import re
import zipfile
from unittest import mock, skipUnless

from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from apps.reports.models import ParentReport
from apps.reports.services import generation, image_generator, layout, presentation
from apps.users.models import User

from .base import TODAY, OctoberFixture, chromium_available, make_user
from .test_permissions import _today

OPTIONS = dict(generation.DEFAULT_OPTIONS)


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return Image.open(io.BytesIO(data)).size


class HtmlTests(OctoberFixture):
    def test_html_is_self_contained(self):
        html = image_generator.group_html(self.data(), language="ru", options=OPTIONS)
        # Logo and fonts are embedded; the browser is never sent to the network.
        self.assertIsNone(re.search(r"(src|href)=\"https?://", html))
        self.assertNotIn("url(http", html)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("Отчёт по студентам", html)
        self.assertIn("PY-01", html)
        self.assertIn("Python для детей", html)
        self.assertIn("01.10.2026 — 31.10.2026", html)
        # No tests in the period → «Нет данных», never 0%.
        self.assertIn("Нет данных", html)
        for title in ("Наши сильные стороны", "На что стоит обратить внимание", "Рекомендации родителям"):
            self.assertIn(title, html)

    def test_kyrgyz_html(self):
        html = image_generator.group_html(self.data(), language="ky", options=OPTIONS)
        self.assertIn("Окуучулар боюнча отчёт", html)
        self.assertIn("Маалымат жок", html)

    def test_bar_widths_are_not_localized(self):
        html = image_generator.group_html(self.data(), language="ru", options=OPTIONS)
        widths = re.findall(r"width: ([^;\"]+)%", html)
        self.assertTrue(widths)
        for width in widths:
            float(width)  # «66,7» would break the CSS

    def test_options_hide_blocks(self):
        html = image_generator.group_html(
            self.data(), language="ru",
            options={**OPTIONS, "include_table": False, "include_recommendations": False, "include_group_stats": False},
        )
        self.assertNotIn("<table", html)
        self.assertNotIn("Наши сильные стороны", html)
        self.assertNotIn('class="kpis"', html)

    def test_student_html(self):
        data = self.data()
        entry = self.entry(data, self.anna)
        html = image_generator.student_html(data, entry, language="ru", options=OPTIONS)
        self.assertIn("Анна Алиева", html)
        self.assertIn("Сравнение с прошлым периодом", html)
        self.assertNotIn("Бек Бекова", html)


class FailureTests(OctoberFixture):
    def test_image_failure_keeps_the_report_with_its_text(self):
        admin = make_user("admin", User.Role.ADMIN)
        request = generation.ReportRequest(period=self.period(), output_format="both")
        with mock.patch.object(
            image_generator, "render_html_pages", side_effect=image_generator.ImageGenerationError("нет браузера"),
        ):
            report = generation.generate(self.group, request, user=admin, today=TODAY)
        self.assertEqual(report.status, ParentReport.Status.PARTIAL)
        self.assertEqual(report.error, "нет браузера")
        self.assertIn("Уважаемые родители", report.text)
        self.assertFalse(report.images.exists())


@skipUnless(chromium_available(), "headless Chromium is not available")
class RenderTests(OctoberFixture):
    def test_group_png(self):
        pages = image_generator.render_group_report(self.data(), language="ru", options=OPTIONS)
        self.assertEqual(len(pages), 1)
        self.assertEqual(png_size(pages[0].png), (layout.PAGE_WIDTH, layout.PAGE_HEIGHT))
        self.assertFalse(pages[0].overflow)

    def test_large_group_is_split_into_readable_pages(self):
        for index in range(28):
            name = "Абдырахманова-Токтогулова Нурайым Бекболотовна" if index % 7 == 0 else f"Студент{index}"
            student = self.student(name, f"Фамилия{index}")
            self.mark(self.l1, student, "present")
        for language in ("ru", "ky"):
            pages = image_generator.render_group_report(self.data(), language=language, options=OPTIONS)
            self.assertGreaterEqual(len(pages), 2)
            for page in pages:
                self.assertEqual(png_size(page.png), (layout.PAGE_WIDTH, layout.PAGE_HEIGHT))
                self.assertFalse(page.overflow, f"{language}: a page overflows its frame")

    def test_worst_case_text_at_the_page_boundary_never_overflows(self):
        """Longest recommendation texts + exactly as many rows as the estimate allows."""
        data = self.data()
        bad = {"attendance_rate": 40.0, "homework_rate": 20.0, "average_score": 3.0, "test_average": 30.0}
        data["group_stats"].update(bad, attention_count=30)
        for metric, value in bad.items():
            data["group_comparison"][metric].update(current=value, change=-30.0, trend="down")
        template = data["students"][0]
        for language in ("ru", "ky"):
            context = presentation.group_context(data, language=language, options=OPTIONS)
            capacity = layout._capacity(first=True, kpis=True, sections=True, sections_px=context["sections_px"])
            for count in (capacity, capacity + 1):
                data["students"] = [
                    {**template, "id": index, "name": "Абдырахманова-Токтогулова Нурайым Бекболотовна"}
                    for index in range(count)
                ]
                pages = image_generator.render_group_report(data, language=language, options=OPTIONS)
                self.assertEqual(len(pages), 1 if count == capacity else 2)
                for page in pages:
                    self.assertFalse(page.overflow, f"{language}, {count} rows: overflow")

    def test_generate_stores_and_downloads_png(self):
        admin = make_user("admin", User.Role.ADMIN)
        client = APIClient()
        client.force_authenticate(admin)
        with mock.patch("django.utils.timezone.localdate", _today):
            response = client.post(
                reverse("parent-report-generate", args=[self.group.pk]), {"period": "last_month"}, format="json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["status"], "ready")
        self.assertEqual(len(response.data["images"]), 1)
        report = ParentReport.objects.get(pk=response.data["id"])
        image = report.images.get()
        # Stored privately: never a public URL.
        with self.assertRaises(ValueError):
            image.image.url

        download = client.get(reverse("parent-report-download", args=[report.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "image/png")
        self.assertEqual(png_size(download.content), (layout.PAGE_WIDTH, layout.PAGE_HEIGHT))

        other_trainer = make_user("stranger", User.Role.TEACHER)
        stranger = APIClient()
        stranger.force_authenticate(other_trainer)
        self.assertEqual(stranger.get(reverse("parent-report-download", args=[report.pk])).status_code, 403)

    def test_individual_reports_one_png_per_student_and_zip(self):
        admin = make_user("admin", User.Role.ADMIN)
        request = generation.ReportRequest(period=self.period(), report_type="students", language="ky")
        report = generation.generate(self.group, request, user=admin, today=TODAY)
        self.assertEqual(report.status, ParentReport.Status.READY)
        images = list(report.images.order_by("page"))
        self.assertEqual({image.student_id for image in images}, {self.anna.pk, self.bek.pk})
        for image in images:
            with image.image.open("rb") as handle:
                self.assertEqual(png_size(handle.read()), (layout.PAGE_WIDTH, layout.PAGE_HEIGHT))

        client = APIClient()
        client.force_authenticate(admin)
        archive = client.get(reverse("parent-report-download", args=[report.pk]))
        self.assertEqual(archive["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
            self.assertEqual(len(zipped.namelist()), 2)
        single = client.get(reverse("parent-report-download", args=[report.pk]), {"image": images[0].pk})
        self.assertEqual(single["Content-Type"], "image/png")
        self.assertEqual(client.get(reverse("parent-report-download", args=[report.pk]), {"image": "x"}).status_code, 400)
