"""«Тесты»: import / export of tests and of one test's questions (CSV /
XLSX), and «Дублировать» (ADMIN role only).

Each import / export page is also the no-JS fallback of the modal on the
list / test page that posts to it. The work is done by services/import_export.py.
"""
from __future__ import annotations

import csv
import uuid
import zipfile

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl.utils.exceptions import InvalidFileException

from apps.users.import_export.formats import UnsupportedFileFormat

from .admin_views import _require_admin, _require_post, _test_url, filter_tests
from .models import Test
from .services import questions as question_service
from .services import import_export

FORMATS, EXPORT_SCOPES = import_export.FORMATS, import_export.EXPORT_SCOPES
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _format(request) -> str | None:
    fmt = request.GET.get("format", "")
    return fmt if fmt in dict(FORMATS) else None


def _uploaded(request):
    """The uploaded file, or None with an error message for the page."""
    file = request.FILES.get("file")
    if file is None:
        return None, "Выберите файл CSV или XLSX."
    if not file.name.lower().endswith((".csv", ".xlsx")):
        return None, "Неподдерживаемый формат файла. Используйте CSV или XLSX."
    if file.size > MAX_UPLOAD_BYTES:
        return None, "Файл больше 5 МБ."
    return file, None


def _run_import(request, run, context: dict, template: str):
    file, error = _uploaded(request)
    if error is None:
        try:
            report = run(file, update_existing=request.POST.get("update_existing") == "1")
        except UnsupportedFileFormat as exc:
            error = str(exc)
        except (zipfile.BadZipFile, InvalidFileException, UnicodeDecodeError, csv.Error, KeyError, OSError):
            error = "Не удалось прочитать файл. Проверьте, что это CSV (UTF-8) или XLSX по шаблону."
        else:
            context.update({"report": report, "file_name": file.name})
            return render(request, template, context)
    context["error"] = error
    return render(request, template, context, status=400)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def tests_export_view(request):
    """GET ?format=xlsx|csv&scope=all|selected|filtered[&ids=…][&q=…] → file;
    without ``format`` → the export form (no-JS fallback)."""
    _require_admin(request)
    fmt = _format(request)
    if fmt is None:
        tests, filters = filter_tests(request.GET)
        return render(request, "admin/testing/tests/io_page.html", {
            "title": "Экспорт тестов", "mode": "tests_export", "formats": FORMATS,
            # No cards to tick on this page — «Только выбранные» lives in the list's dialog.
            "scopes": [s for s in EXPORT_SCOPES if s[0] != "selected"],
            "filters": filters, "has_filters": any(filters.values()), "found": tests.count(),
            "total": Test.objects.count(),
        })
    scope = request.GET.get("scope", "all")
    tests = Test.objects.order_by("title")
    if scope == "selected":
        ids = []
        for value in request.GET.getlist("ids"):
            try:
                ids.append(uuid.UUID(value))
            except ValueError:
                continue
        if not ids:
            messages.error(request, "Не выбрано ни одного теста: отметьте карточки галочкой или экспортируйте все.")
            return redirect("admin:testing_test_changelist")
        tests = tests.filter(pk__in=ids)
    elif scope == "filtered":
        tests, _filters = filter_tests(request.GET, tests)
    return import_export.export_tests(tests, fmt)


def tests_import_view(request):
    _require_admin(request)
    context = {"title": "Импорт тестов", "mode": "tests_import"}
    if request.method != "POST":
        return render(request, "admin/testing/tests/io_page.html", context)
    return _run_import(request, import_export.import_tests, context, "admin/testing/tests/io_page.html")


def tests_import_template_view(request):
    _require_admin(request)
    return import_export.tests_template(_format(request) or "xlsx")


def test_duplicate_view(request, test_id):
    _require_admin(request)
    if (response := _require_post(request)) is not None:
        return response
    test = get_object_or_404(Test, pk=test_id)
    copy = question_service.duplicate_test(test)
    messages.success(request, f"Создана копия «{copy.title}» (черновик) — со всеми вопросами.")
    return redirect(_test_url(copy))


# ---------------------------------------------------------------------------
# Questions of one test
# ---------------------------------------------------------------------------

def questions_export_view(request, test_id):
    _require_admin(request)
    test = get_object_or_404(Test, pk=test_id)
    fmt = _format(request)
    if fmt is None:
        return render(request, "admin/testing/tests/io_page.html", {
            "title": "Экспорт вопросов", "mode": "questions_export", "test": test, "formats": FORMATS,
        })
    return import_export.export_questions(test, fmt)


def questions_import_view(request, test_id):
    _require_admin(request)
    test = get_object_or_404(Test, pk=test_id)
    context = {"title": "Импорт вопросов", "mode": "questions_import", "test": test}
    if request.method != "POST":
        return render(request, "admin/testing/tests/io_page.html", context)
    return _run_import(
        request, lambda file, **kw: import_export.import_questions(test, file, **kw),
        context, "admin/testing/tests/io_page.html",
    )


def questions_import_template_view(request, test_id):
    _require_admin(request)
    test = get_object_or_404(Test, pk=test_id)
    return import_export.questions_template(_format(request) or "xlsx", test)
