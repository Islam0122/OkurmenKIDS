"""«Тесты» — the whole test management section of the admin (ADMIN role only).

    Тесты (list)  →  Создать тест
                  →  Тест: Вопросы (info + questions) · Настройки ·
                       Публикация (status + sessions) · Статистика · Предпросмотр
                       └── Вопрос: create / edit (type-aware editor), ↑ ↓,
                           copy, delete, drag & drop order

Questions only exist inside a test: there is no separate questions section.
Every write goes through services (questions / attempts), which the REST
API (api_views.py) uses too.
"""
from __future__ import annotations

import json
import random
import uuid

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Min, Q
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.users.models import Subject, User

from .forms import (
    QuestionForm,
    TestCreateForm,
    TestInfoForm,
    TestSettingsForm,
    question_data_from_post,
)
from .models import (
    Answer,
    AttemptStatus,
    GradingStatus,
    Question,
    QuestionType,
    StudentAttempt,
    Test,
    TestLevel,
    TestStatus,
)
from .services import questions as question_service
from .services import import_export
from .services.attempts import ordered_questions
from .services.question_rules import CHOICE_TYPES

STATUS_FILTERS = (
    ("all", "Все"),
    (TestStatus.ACTIVE, "Активные"),
    (TestStatus.DRAFT, "Черновики"),
    (TestStatus.ARCHIVED, "Архив"),
)

QUESTION_TYPE_TABS = (
    (QuestionType.TEXT, "Текст", "type"),
    (QuestionType.SINGLE_CHOICE, "Один вариант", "circle-dot"),
    (QuestionType.MULTIPLE_CHOICE, "Несколько", "list-checks"),
    (QuestionType.CODE, "Код", "code"),
)

QUESTION_TYPE_SHORT = {
    QuestionType.TEXT: "Текст",
    QuestionType.SINGLE_CHOICE: "Один вариант",
    QuestionType.MULTIPLE_CHOICE: "Несколько вариантов",
    QuestionType.CODE: "Код",
}


def is_admin_user(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", None) == User.Role.ADMIN)
    )


def _require_admin(request) -> None:
    if not is_admin_user(request.user):
        raise PermissionDenied("Тесты доступны только администратору.")


def _require_post(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    return None


def _test_url(test, tab: str = "overview") -> str:
    names = {
        "overview": "admin:testing_test_change",
        "settings": "admin:testing_test_settings",
        "publish": "admin:testing_test_publish",
        "stats": "admin:testing_test_stats",
    }
    return reverse(names[tab], args=[test.pk])


def _attempts_of(test):
    return StudentAttempt.objects.filter(session__test=test)


# ---------------------------------------------------------------------------
# List / create
# ---------------------------------------------------------------------------

def filter_tests(params, tests=None) -> tuple:
    """The list's filters (q, status, subject, level) applied to ``tests``.
    Shared by the list and «Экспорт → текущий фильтр»."""
    tests = Test.objects.all() if tests is None else tests
    filters = {
        "q": (params.get("q") or "").strip(),
        "status": params.get("status") or "",
        "subject": params.get("subject") or "",
        "level": params.get("level") or "",
    }
    if filters["status"] in TestStatus.values:
        tests = tests.filter(status=filters["status"])
    else:
        filters["status"] = ""
    if filters["level"] in TestLevel.values:
        tests = tests.filter(level=filters["level"])
    else:
        filters["level"] = ""
    if filters["subject"] == "none":
        tests = tests.filter(subject__isnull=True)
    elif filters["subject"].isdigit():
        tests = tests.filter(subject_id=int(filters["subject"]))
    else:
        filters["subject"] = ""
    if filters["q"]:
        q = filters["q"]
        tests = tests.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(subject__name__icontains=q))
    return tests, filters


def tests_list_view(request):
    _require_admin(request)
    tests, filters = filter_tests(
        request.GET,
        Test.objects.select_related("subject")
        .annotate(
            questions_total=Count("questions", distinct=True),
            attempts_total=Count("sessions__attempts", distinct=True),
        )
        .order_by("-updated_at"),
    )
    counts = dict(Test.objects.values_list("status").annotate(n=Count("pk")))
    page = Paginator(tests, 24).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "admin/testing/tests/list.html", {
        "title": "Тесты",
        "page": page,
        "tests": page.object_list,
        "filters": filters,
        "has_filters": any(filters.values()),
        "filter_qs": query.urlencode(),
        "status_options": [
            (key, label, counts.get(key, 0)) for key, label in STATUS_FILTERS if key != "all"
        ],
        "level_options": TestLevel.choices,
        "subjects": Subject.objects.filter(pk__in=Test.objects.values("subject")).order_by("name"),
        "has_unassigned": Test.objects.filter(subject__isnull=True).exists(),
        "total": sum(counts.values()),
        "found": page.paginator.count,
        "export_formats": import_export.FORMATS,
        "export_scopes": import_export.EXPORT_SCOPES,
    })


def test_create_view(request):
    _require_admin(request)
    form = TestCreateForm(request.POST or None, initial={"status": TestStatus.DRAFT})
    if request.method == "POST" and form.is_valid():
        test = form.save()
        messages.success(request, f"Тест «{test.title}» создан. Добавьте в него вопросы.")
        if "_continue" in request.POST:
            return redirect(reverse("admin:testing_question_add", args=[test.pk]))
        return redirect(_test_url(test))
    return render(request, "admin/testing/tests/create.html", {"title": "Новый тест", "form": form})


# ---------------------------------------------------------------------------
# Test workspace
# ---------------------------------------------------------------------------

def _workspace_context(request, test: Test, tab: str) -> dict:
    tabs = [
        ("overview", "Вопросы", "list-checks"),
        ("settings", "Настройки", "settings"),
        ("publish", "Публикация", "send"),
        ("stats", "Статистика", "chart-column"),
    ]
    return {
        "title": test.title,
        "test": test,
        "active_tab": tab,
        "tabs": [{"key": k, "label": label, "icon": icon, "url": _test_url(test, k)} for k, label, icon in tabs],
        "question_total": test.questions.count(),
        "attempt_total": _attempts_of(test).count(),
        "preview_url": reverse("admin:testing_test_preview", args=[test.pk]),
        "export_formats": import_export.FORMATS,
    }


def test_overview_view(request, test_id):
    _require_admin(request)
    try:
        uuid.UUID(str(test_id))
    except ValueError:
        raise Http404("Тест не найден.")
    test = get_object_or_404(Test.objects.select_related("subject"), pk=test_id)
    form = TestInfoForm(request.POST or None, instance=test)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Основная информация сохранена.")
        return redirect(_test_url(test))
    questions = list(
        test.questions.annotate(options_total=Count("options")).order_by("order", "created_at")
    )
    for question in questions:
        question.type_label = QUESTION_TYPE_SHORT.get(question.question_type, question.get_question_type_display())
    context = _workspace_context(request, test, "overview")
    context.update({
        "form": form,
        "questions": questions,
        "points_total": sum(q.points for q in questions),
        "type_tabs": QUESTION_TYPE_TABS,
    })
    return render(request, "admin/testing/tests/overview.html", context)


def test_settings_view(request, test_id):
    _require_admin(request)
    test = get_object_or_404(Test, pk=test_id)
    form = TestSettingsForm(request.POST or None, instance=test)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Настройки теста сохранены.")
        return redirect(_test_url(test, "settings"))
    context = _workspace_context(request, test, "settings")
    context["form"] = form
    return render(request, "admin/testing/tests/settings.html", context)


def test_status_action_view(request, test_id, action):
    """Header/menu quick actions: publish, back to draft, archive."""
    _require_admin(request)
    if (response := _require_post(request)) is not None:
        return response
    test = get_object_or_404(Test, pk=test_id)
    target = {"publish": TestStatus.ACTIVE, "draft": TestStatus.DRAFT, "archive": TestStatus.ARCHIVED}.get(action)
    if target is None:
        raise PermissionDenied
    if target == TestStatus.ACTIVE and not test.questions.exists():
        messages.error(request, "Нельзя опубликовать тест без вопросов.")
    else:
        test.status = target
        test.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Статус теста: «{test.get_status_display()}».")
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = _test_url(test, "publish")
    return redirect(next_url)


def test_publish_view(request, test_id):
    """Publication status of the test, and the sessions it is used in.
    Sessions themselves are created and run in the «Сессии» section."""
    _require_admin(request)
    test = get_object_or_404(Test, pk=test_id)
    sessions = list(
        test.sessions.select_related("group")
        .annotate(attempts_total=Count("attempts", distinct=True), participants_total=Count("participants", distinct=True))
        .order_by("-scheduled_start", "-created_at")[:30]
    )
    context = _workspace_context(request, test, "publish")
    context.update({
        "sessions": sessions,
        "availability_error": test.availability_error(),
        "sessions_url": f"{reverse('admin:testing_testsession_changelist')}?test={test.pk}",
    })
    return render(request, "admin/testing/tests/publish.html", context)


def test_stats_view(request, test_id):
    _require_admin(request)
    test = get_object_or_404(Test, pk=test_id)
    attempts = _attempts_of(test)
    finished = attempts.filter(status=AttemptStatus.FINISHED)
    finished_total = finished.count()
    passed = finished.filter(score__gte=test.passing_score).count()
    answer_stats = {
        row["question_id"]: row
        for row in Answer.objects.filter(attempt__session__test=test)
        .values("question_id")
        .annotate(
            total=Count("pk"),
            correct=Count("pk", filter=Q(is_correct=True)),
            pending=Count("pk", filter=Q(grading_status__in=[GradingStatus.PENDING, GradingStatus.PROCESSING, GradingStatus.FAILED])),
        )
    }
    question_rows = []
    for number, question in enumerate(test.questions.order_by("order", "created_at"), start=1):
        stats = answer_stats.get(question.pk, {"total": 0, "correct": 0, "pending": 0})
        graded = stats["total"] - stats["pending"]
        question_rows.append({
            "number": number,
            "question": question,
            "type_label": QUESTION_TYPE_SHORT.get(question.question_type),
            "total": stats["total"],
            "pending": stats["pending"],
            "rate": round(stats["correct"] / graded * 100) if graded else None,
        })
    context = _workspace_context(request, test, "stats")
    context.update({
        "attempts_total": attempts.count(),
        "finished_total": finished_total,
        "active_total": attempts.filter(status=AttemptStatus.ACTIVE).count(),
        "average_score": finished.aggregate(avg=Avg("score"))["avg"],
        "pass_rate": round(passed / finished_total * 100) if finished_total else None,
        **finished.filter(student__isnull=False).aggregate(
            students_total=Count("student", distinct=True), best_score=Max("score"), lowest_score=Min("score"),
        ),
        "results_url": reverse("admin:testing_testresult_changelist") + f"?session__test__id__exact={test.pk}",
        "pending_total": Answer.objects.filter(
            attempt__session__test=test, grading_status__in=[GradingStatus.PENDING, GradingStatus.PROCESSING, GradingStatus.FAILED]
        ).count(),
        "question_rows": question_rows,
        "recent_attempts": attempts.select_related("session", "student").order_by("-started_at")[:20],
    })
    return render(request, "admin/testing/tests/stats.html", context)


def test_preview_view(request, test_id):
    """The test as a student sees it — same template as the real page,
    nothing is saved."""
    _require_admin(request)
    test = get_object_or_404(Test, pk=test_id)
    ids = [str(pk) for pk in test.questions.order_by("order", "created_at").values_list("pk", flat=True)]
    seed = random.randrange(1 << 30)
    if test.shuffle_questions:
        random.Random(seed).shuffle(ids)
    questions = ordered_questions(test, ids, shuffle_seed=seed)
    for question in questions:
        question.given_text = question.starter_code if question.question_type == QuestionType.CODE else ""
        question.given_options = set()
    return render(request, "testing/public/take.html", {
        "test": test,
        "questions": questions,
        "preview": True,
        "back_url": _test_url(test),
        "deadline": None,
        "time_limit_minutes": test.time_limit_minutes,
    })


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

def question_editor_view(request, test_id, question_id=None):
    _require_admin(request)
    test = get_object_or_404(Test, pk=test_id)
    question = get_object_or_404(Question, pk=question_id, test=test) if question_id else None

    if request.method == "POST":
        form = QuestionForm(request.POST)
        errors: dict = {}
        if form.is_valid():
            data = question_data_from_post(
                request.POST,
                form.cleaned_data["question_type"],
                form.cleaned_data["text"],
                form.cleaned_data["language"],
                form.cleaned_data["image_url"],
            )
            try:
                saved = question_service.save_question(test, data, question=question, **form.extra_values())
            except ValidationError as error:
                errors = error.message_dict if hasattr(error, "error_dict") else {"__all__": error.messages}
            else:
                messages.success(request, "Вопрос сохранён." if question else "Вопрос добавлен.")
                if "_addanother" in request.POST:
                    url = reverse("admin:testing_question_add", args=[test.pk])
                    return redirect(f"{url}?type={saved.question_type}")
                return redirect(f"{_test_url(test)}#question-{saved.pk}")
        rows = _rows_from_post(request.POST)
        question_type = request.POST.get("question_type") or QuestionType.SINGLE_CHOICE
    else:
        if question:
            form = QuestionForm(initial=QuestionForm.initial_for(question))
            question_type = question.question_type
            rows = _rows_from_question(question)
        else:
            question_type = request.GET.get("type")
            if question_type not in QuestionType.values:
                question_type = QuestionType.SINGLE_CHOICE
            form = QuestionForm(initial={"question_type": question_type})
            rows = _blank_rows()
        errors = {}

    field_keys = ("text", "image_url", "options", "correct_answers", "language", "code_tests")
    non_field_errors = [m for key, msgs in errors.items() if key not in field_keys for m in msgs]
    number = None
    if question:
        number = list(test.questions.order_by("order", "created_at").values_list("pk", flat=True)).index(question.pk) + 1
    context = _workspace_context(request, test, "overview")
    context.update({
        "title": "Новый вопрос" if question is None else f"Вопрос {number}",
        "question": question,
        "question_number": number,
        "form": form,
        "question_type": question_type,
        "type_tabs": QUESTION_TYPE_TABS,
        "choice_types": list(CHOICE_TYPES),
        "errors": errors,
        "non_field_errors": non_field_errors,
        **rows,
    })
    return render(request, "admin/testing/tests/question_form.html", context)


def _blank_rows() -> dict:
    return {
        "option_rows": [{"id": "", "text": "", "image_url": "", "is_correct": False} for _ in range(4)],
        "correct_answer": "",
        "accepted_answers": "",
        "test_rows": [{"input": "", "expected_output": ""}],
    }


def _rows_from_question(question: Question) -> dict:
    answers = list(question.correct_answers or [])
    options = [
        {"id": str(o.pk), "text": o.text, "image_url": o.image_url, "is_correct": o.is_correct}
        for o in question.options.order_by("order", "pk")
    ]
    return {
        "option_rows": options or _blank_rows()["option_rows"],
        "correct_answer": answers[0] if answers else "",
        "accepted_answers": "\n".join(answers[1:]),
        "test_rows": list(question.code_tests or []) or [{"input": "", "expected_output": ""}],
    }


def _rows_from_post(post) -> dict:
    texts, ids, images = post.getlist("option_text"), post.getlist("option_id"), post.getlist("option_image")
    if post.get("question_type") == QuestionType.SINGLE_CHOICE:
        correct = {post.get("option_correct_single", "")}
    else:
        correct = set(post.getlist("option_correct"))
    return {
        "option_rows": [
            {
                "id": ids[i] if i < len(ids) else "",
                "text": t,
                "image_url": images[i] if i < len(images) else "",
                "is_correct": str(i) in correct,
            }
            for i, t in enumerate(texts)
        ] or _blank_rows()["option_rows"],
        "correct_answer": post.get("correct_answer", ""),
        "accepted_answers": post.get("accepted_answers", ""),
        "test_rows": [
            {"input": i, "expected_output": o}
            for i, o in zip(post.getlist("test_input"), post.getlist("test_output"))
        ] or [{"input": "", "expected_output": ""}],
    }


def question_action_view(request, test_id, question_id, action):
    """↑ / ↓ / copy / delete from the questions list."""
    _require_admin(request)
    if (response := _require_post(request)) is not None:
        return response
    question = get_object_or_404(Question, pk=question_id, test_id=test_id)
    anchor = f"#question-{question.pk}"
    if action in ("up", "down"):
        question_service.move_question(question, action)
    elif action == "duplicate":
        copy = question_service.duplicate_question(question)
        messages.success(request, "Копия вопроса добавлена.")
        anchor = f"#question-{copy.pk}"
    elif action == "delete":
        test = question.test
        question.delete()
        question_service.renumber(test)
        messages.success(request, "Вопрос удалён.")
        anchor = "#questions"
    else:
        raise PermissionDenied
    return redirect(_test_url(question.test) + anchor)


def questions_reorder_view(request, test_id):
    """Drag & drop: POST {"order": [question ids]} → Question.order = 1..n."""
    _require_admin(request)
    if (response := _require_post(request)) is not None:
        return response
    test = get_object_or_404(Test, pk=test_id)
    try:
        ids = json.loads(request.body or b"{}").get("order")
    except (ValueError, AttributeError):
        ids = None
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return JsonResponse({"error": "Некорректный запрос."}, status=400)
    if not question_service.reorder_questions(test, ids):
        return JsonResponse({"error": "Список вопросов изменился — обновите страницу."}, status=409)
    Test.objects.filter(pk=test.pk).update(updated_at=timezone.now())
    return JsonResponse({"ok": True})
