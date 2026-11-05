"""PNG rendering: Django template → headless Chromium (Playwright) screenshot.

Local only: the HTML is fully self-contained (logo and fonts are embedded as
data URIs), the browser never makes a network request — every request is
aborted. One browser per call renders every page of a report.

Chromium is found the way Playwright finds it, or at
``settings.REPORTS_CHROMIUM_EXECUTABLE`` / ``$REPORTS_CHROMIUM_EXECUTABLE``
when set (a system Chromium, e.g. in Docker).
"""
from __future__ import annotations

import dataclasses
import logging
import os

from django.conf import settings
from django.template.loader import render_to_string

from . import layout, presentation

logger = logging.getLogger(__name__)

DEVICE_SCALE = 1  # 1600×1100 px — the size the design is made for.
RENDER_TIMEOUT_MS = 30_000


class ImageGenerationError(RuntimeError):
    """The PNG could not be rendered (no browser installed, render error…)."""


@dataclasses.dataclass
class RenderedPage:
    png: bytes
    width: int
    height: int
    overflow: bool = False


def _executable() -> str | None:
    return getattr(settings, "REPORTS_CHROMIUM_EXECUTABLE", None) or os.environ.get("REPORTS_CHROMIUM_EXECUTABLE") or None


_OVERFLOW_JS = """
() => Array.from(document.querySelectorAll('.page')).map((page) => {
  const clipped = Array.from(page.querySelectorAll('.section, .card, .kpi')).some(
    (el) => el.scrollHeight > el.clientHeight + 1
  );
  const last = page.lastElementChild;
  const bottom = last ? last.getBoundingClientRect().bottom - page.getBoundingClientRect().top : 0;
  return clipped || page.scrollHeight > page.clientHeight + 1 || bottom > page.clientHeight + 1;
})
"""


def render_html_pages(html: str) -> list[RenderedPage]:
    """Screenshot every ``.page`` element of ``html`` as its own PNG."""
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImageGenerationError("Playwright не установлен: pip install playwright && playwright install chromium") from exc

    try:
        with sync_playwright() as pw:
            launch = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none"]}
            executable = _executable()
            if executable:
                launch["executable_path"] = executable
            browser = pw.chromium.launch(**launch)
            try:
                context = browser.new_context(
                    viewport={"width": layout.PAGE_WIDTH, "height": layout.PAGE_HEIGHT},
                    device_scale_factor=DEVICE_SCALE,
                    java_script_enabled=True,
                    offline=True,
                )
                page = context.new_page()
                page.route("**/*", lambda route: route.abort() if not route.request.url.startswith("data:") else route.continue_())
                page.set_default_timeout(RENDER_TIMEOUT_MS)
                page.set_content(html, wait_until="load")
                page.evaluate("document.fonts.ready")
                overflow = page.evaluate(_OVERFLOW_JS)
                pages = []
                for index, element in enumerate(page.query_selector_all(".page")):
                    png = element.screenshot(type="png", animations="disabled")
                    pages.append(RenderedPage(
                        png=png,
                        width=layout.PAGE_WIDTH * DEVICE_SCALE,
                        height=layout.PAGE_HEIGHT * DEVICE_SCALE,
                        overflow=bool(overflow[index]) if index < len(overflow) else False,
                    ))
                context.close()
            finally:
                browser.close()
    except (PlaywrightError, OSError, RuntimeError) as exc:
        # No browser installed, a crashed renderer, the sync API called inside
        # an event loop… — the report is kept without its image.
        logger.exception("Report image rendering failed")
        first_line = (str(exc).splitlines() or [exc.__class__.__name__])[0]
        raise ImageGenerationError(f"Не удалось сформировать изображение: {first_line}") from exc
    for number, rendered in enumerate(pages, start=1):
        if rendered.overflow:
            logger.warning("Report image page %s overflows its 1600×1100 frame", number)
    return pages


def group_html(snapshot: dict, *, language: str, options: dict) -> str:
    return render_to_string("reports/group_report.html", presentation.group_context(snapshot, language=language, options=options))


def student_html(snapshot: dict, entry: dict, *, language: str, options: dict) -> str:
    return render_to_string(
        "reports/student_report.html", presentation.student_context(snapshot, entry, language=language, options=options),
    )


def render_group_report(snapshot: dict, *, language: str, options: dict) -> list[RenderedPage]:
    return render_html_pages(group_html(snapshot, language=language, options=options))


def render_student_reports(snapshot: dict, *, language: str, options: dict) -> list[tuple[dict, RenderedPage]]:
    """One PNG per student. All students go through one browser: their pages
    are joined into one document and screenshot page by page."""
    entries = snapshot["students"]
    if not entries:
        return []
    bodies = [student_html(snapshot, entry, language=language, options=options) for entry in entries]
    # Each rendered document has exactly one <section class="page">; join the
    # sections under the first document's <head>.
    head, _, rest = bodies[0].partition("<body>")
    sections = [body.partition("<body>")[2].rpartition("</body>")[0] for body in bodies]
    html = f"{head}<body>{''.join(sections)}</body></html>"
    pages = render_html_pages(html)
    return list(zip(entries, pages))
