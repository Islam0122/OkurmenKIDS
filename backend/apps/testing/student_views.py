"""Student portal pages, mounted at /student/ in config/urls.py.

    /student/login/                                    sign in with the personal code
    /student/                                          Student Dashboard
    /student/exams/                                    exams + summary cards
    /student/exams/<exam>/prepare/                     rules, «Начать экзамен» (POST)
    /student/exams/<exam>/attempt/<attempt>/           Exam Mode
    /student/exams/<exam>/attempt/<attempt>/submit/    finish (POST)
    /student/exams/<exam>/result/<attempt>/            result
    /student/exams/<exam>/review/<attempt>/            answers review (if the test allows it)

``exam`` is a TestSession of type «exam». Server-rendered like /exam/;
exam_mode.js adds the Exam Mode behaviour. All rules live in
services/exam_portal.py — the views only resolve the student, check that
the exam and attempt are theirs, and render.
"""
from __future__ import annotations

from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from . import student_auth
from .models import AttemptStatus, FinishReason, QuestionType, StudentAttempt
from .public_views import _answers_from_post
from .services import exam_portal as portal
from .services.attempts import AttemptError, attempt_questions, result_rows
from .services.sessions import format_duration
from .student_auth import student_required

EXAM_RULES = [
    "На выполнение экзамена отводится ограниченное время.",
    "После начала экзамена таймер запускается автоматически.",
    "Нельзя покидать страницу экзамена.",
    "Нельзя открывать дополнительные вкладки.",
    "Нельзя использовать копирование и вставку (Copy / Paste).",
    "Нельзя использовать контекстное меню.",
    "Нельзя выделять текст вопросов.",
    "При попытке покинуть страницу показывается предупреждение.",
    "Все действия студента фиксируются системой.",
    "После завершения времени экзамен автоматически отправляется.",
]


def _student_context(request) -> dict:
    student = request.student
    group = student.group
    return {
        "student": student,
        "group": group,
        "course": group.course if group else None,
    }


def _exam(request, exam_id):
    try:
        return portal.exam_sessions_for(request.student).get(pk=exam_id)
    except portal.TestSession.DoesNotExist:
        raise Http404("Экзамен не найден.")


def _own_attempt(request, exam_id, attempt_id) -> StudentAttempt:
    """The signed-in student's own Exam Mode attempt of this exam — or 404
    (never 403: whether someone else's attempt exists is not disclosed)."""
    try:
        return StudentAttempt.objects.select_related("session__test__subject", "session__group").get(
            pk=attempt_id, session_id=exam_id, student=request.student, exam_mode=True,
        )
    except StudentAttempt.DoesNotExist:
        raise Http404("Попытка не найдена.")


def _attempt_url(attempt) -> str:
    return reverse("student_exam_attempt", args=[attempt.session_id, attempt.pk])


def _result_url(attempt) -> str:
    return reverse("student_exam_result", args=[attempt.session_id, attempt.pk])


# ---------------------------------------------------------------------------
# Sign in / out, dashboard
# ---------------------------------------------------------------------------

@never_cache
@csrf_protect
def login_view(request):
    fallback = reverse("student_portal_dashboard")
    if student_auth.current_student(request) is not None:
        return redirect(student_auth.safe_next(request, fallback))
    error = None
    status = 200
    if request.method == "POST":
        if student_auth.too_many_failed_codes(request):
            error, status = "Слишком много неверных попыток. Попробуйте позже.", 429
        else:
            access = student_auth.find_access(request.POST.get("code", ""))
            if access is None:
                student_auth.record_failed_code(request)
                error = "Код не найден. Проверьте код у администратора."
            else:
                student_auth.login(request, access)
                return redirect(student_auth.safe_next(request, fallback))
    return render(request, "testing/student/login.html", {
        "error": error,
        "next": request.POST.get("next") or request.GET.get("next") or "",
    }, status=status)


@csrf_protect
def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    student_auth.logout(request)
    return redirect("student_portal_login")


@never_cache
@student_required
def dashboard_view(request):
    cards = portal.student_exam_cards(request.student)
    return render(request, "testing/student/dashboard.html", {
        **_student_context(request),
        "summary": portal.summarize(cards),
        "next_exam": next((c for c in cards if c.status in (portal.ExamStatus.IN_PROGRESS, portal.ExamStatus.AVAILABLE, portal.ExamStatus.UPCOMING)), None),
    })


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------

@never_cache
@student_required
def exams_view(request):
    cards = portal.student_exam_cards(request.student)
    return render(request, "testing/student/exams.html", {
        **_student_context(request),
        "cards": cards,
        "summary": portal.summarize(cards),
    })


@never_cache
@csrf_protect
@student_required
def prepare_view(request, exam_id):
    session = _exam(request, exam_id)
    card = portal.exam_card(session, request.student)
    error = None
    if request.method == "POST":
        if card.active_attempt is not None:
            return redirect(_attempt_url(card.active_attempt))
        if request.POST.get("rules_accepted") != "1":
            error = "Подтвердите, что ознакомились с правилами экзамена."
        else:
            try:
                attempt = portal.start_exam(session, request.student, request)
            except AttemptError as exc:
                error = exc.messages[0]
            else:
                return redirect(_attempt_url(attempt))
        card = portal.exam_card(session, request.student)
    return render(request, "testing/student/prepare.html", {
        **_student_context(request),
        "card": card,
        "test": session.test,
        "rules": EXAM_RULES,
        "error": error,
    })


@never_cache
@student_required
def attempt_view(request, exam_id, attempt_id):
    attempt = portal.ensure_current(_own_attempt(request, exam_id, attempt_id), request)
    if attempt.status != AttemptStatus.ACTIVE:
        return redirect(_result_url(attempt))
    questions = attempt_questions(attempt)
    drafts = attempt.draft_answers or {}
    for question in questions:
        draft = drafts.get(str(question.pk)) or {}
        if question.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
            question.given_options = set(draft.get("options") or [])
            question.given_text = ""
        else:
            question.given_options = set()
            default = question.starter_code if question.question_type == QuestionType.CODE else ""
            question.given_text = draft["text"] if "text" in draft else default
    test = attempt.session.test
    return render(request, "testing/student/attempt.html", {
        "attempt": attempt,
        "session": attempt.session,
        "test": test,
        "title": attempt.session.title or test.title,
        "questions": questions,
        "seconds_left": portal.remaining_seconds(attempt),
        "error": request.session.pop("student_exam_error", None),
    })


@csrf_protect
@student_required
def submit_view(request, exam_id, attempt_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    attempt = _own_attempt(request, exam_id, attempt_id)
    questions = attempt_questions(attempt)
    try:
        attempt = portal.submit_exam(
            attempt, _answers_from_post(request.POST, questions),
            timed_out=request.POST.get("timed_out") == "1", request=request,
        )
    except AttemptError as exc:
        request.session["student_exam_error"] = exc.messages[0]
        return redirect(_attempt_url(attempt))
    return redirect(_result_url(attempt))


@never_cache
@student_required
def result_view(request, exam_id, attempt_id):
    attempt = portal.ensure_current(_own_attempt(request, exam_id, attempt_id), request)
    if attempt.status == AttemptStatus.ACTIVE:
        return redirect(_attempt_url(attempt))
    test = attempt.session.test
    graded = attempt.status == AttemptStatus.FINISHED
    summary = portal.result_summary(attempt) if graded else None
    return render(request, "testing/student/result.html", {
        **_student_context(request),
        "attempt": attempt,
        "test": test,
        "title": attempt.session.title or test.title,
        "graded": graded,
        "show_result": test.show_result and graded,
        "summary": summary,
        "duration": format_duration(summary.duration_seconds if summary else None),
        "can_review": graded and test.show_result and test.show_correct_answers,
        "terminated": attempt.finish_reason == FinishReason.VIOLATIONS,
        "time_expired": attempt.finish_reason == FinishReason.TIME_EXPIRED,
        "session_closed": attempt.finish_reason == FinishReason.SESSION_CLOSED,
    })


@never_cache
@student_required
def review_view(request, exam_id, attempt_id):
    attempt = _own_attempt(request, exam_id, attempt_id)
    test = attempt.session.test
    if attempt.status != AttemptStatus.FINISHED or not (test.show_result and test.show_correct_answers):
        raise Http404("Разбор этого экзамена недоступен.")
    return render(request, "testing/student/review.html", {
        **_student_context(request),
        "attempt": attempt,
        "test": test,
        "title": attempt.session.title or test.title,
        "rows": result_rows(attempt),
    })

