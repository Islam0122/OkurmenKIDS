"""Student pages (no login), mounted at /exam/ in config/urls.py.

    /exam/                      enter the session key, then your name
                                (or pick yourself from the session's group)
    /exam/a/<attempt>/          take the test
    /exam/a/<attempt>/result/   the result

Server-rendered so they work on slow phones and in-app browsers; JS only
adds one-question-at-a-time navigation, the timer and the code editor.
An attempt page only opens in the browser that started the attempt (its id
is remembered in the Django session), so a shared link can't be used to
answer for someone else. All rules live in services/attempts.py.
"""
from __future__ import annotations

from django.core.cache import cache
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from apps.academy.models import Student

from .models import AttemptStatus, QuestionType, StudentAttempt
from .services.attempts import (
    AttemptError,
    SubmittedAnswer,
    attempt_deadline,
    attempt_questions,
    find_session,
    is_passed,
    join,
    result_rows,
    submit,
)
from .services.grading import attempt_score

_ATTEMPTS_SESSION_KEY = "testing_attempts"

# Wrong session keys allowed per client IP per hour (keys are short; this
# stops guessing). Correct keys are never counted, so a whole class joining
# from one school IP is not affected.
_FAILED_KEYS_PER_HOUR = 30


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else "") or request.META.get("REMOTE_ADDR", "")


def _failed_key_cache_key(request) -> str:
    return f"testing:join-fail:{_client_ip(request)}"


def _too_many_failed_keys(request) -> bool:
    return (cache.get(_failed_key_cache_key(request)) or 0) >= _FAILED_KEYS_PER_HOUR


def _record_failed_key(request) -> None:
    key = _failed_key_cache_key(request)
    if cache.add(key, 1, timeout=3600):
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=3600)


def _remember(request, attempt: StudentAttempt) -> None:
    ids = [i for i in request.session.get(_ATTEMPTS_SESSION_KEY, []) if i != str(attempt.pk)]
    request.session[_ATTEMPTS_SESSION_KEY] = [*ids[-19:], str(attempt.pk)]


def _own_attempt(request, attempt_id) -> StudentAttempt:
    if str(attempt_id) not in request.session.get(_ATTEMPTS_SESSION_KEY, []):
        raise Http404("Попытка не найдена.")
    try:
        return StudentAttempt.objects.select_related("session__test", "session__group").get(pk=attempt_id)
    except StudentAttempt.DoesNotExist:
        raise Http404("Попытка не найдена.")


@never_cache
@csrf_protect
def join_view(request):
    key = (request.POST.get("key") or request.GET.get("key") or "").strip()
    context = {"key": key, "error": None, "session": None}
    if key:
        if _too_many_failed_keys(request):
            context["error"] = "Слишком много неверных ключей. Попробуйте позже."
            return render(request, "testing/public/join.html", context, status=429)
        try:
            session = find_session(key)
        except AttemptError as error:
            _record_failed_key(request)
            context["error"] = error.messages[0]
            return render(request, "testing/public/join.html", context)
        context["session"] = session
        context["students"] = (
            Student.objects.filter(group=session.group, status=Student.Status.ACTIVE).order_by("first_name", "last_name")
            if session.group_id else None
        )

        if request.method == "POST" and "start" in request.POST:
            student = None
            name = request.POST.get("student_name", "")
            if session.group_id:
                student = Student.objects.filter(
                    pk=request.POST.get("student") or 0, group=session.group
                ).first() if (request.POST.get("student") or "").isdigit() else None
                if student is None:
                    context["error"] = "Выберите себя из списка группы."
                    return render(request, "testing/public/join.html", context)
            try:
                attempt = join(session, student_name=name, student=student)
            except AttemptError as error:
                context["error"] = error.messages[0]
                context["student_name"] = name
                return render(request, "testing/public/join.html", context)
            _remember(request, attempt)
            return redirect("testing_public_take", attempt_id=attempt.pk)
    return render(request, "testing/public/join.html", context)


def _answers_from_post(post, questions) -> dict[str, SubmittedAnswer]:
    answers = {}
    for question in questions:
        name = f"answer_{question.pk}"
        if question.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
            answers[str(question.pk)] = SubmittedAnswer(options=[v for v in post.getlist(name) if v])
        else:
            answers[str(question.pk)] = SubmittedAnswer(text=post.get(name, ""))
    return answers


@never_cache
@csrf_protect
def take_view(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if attempt.status != AttemptStatus.ACTIVE:
        return redirect("testing_public_result", attempt_id=attempt.pk)
    questions = attempt_questions(attempt)
    error = None
    given: dict[str, SubmittedAnswer] = {}
    if request.method == "POST":
        given = _answers_from_post(request.POST, questions)
        try:
            submit(attempt, given, timed_out=request.POST.get("timed_out") == "1")
        except AttemptError as exc:
            attempt.refresh_from_db()
            if attempt.status != AttemptStatus.ACTIVE:
                return redirect("testing_public_result", attempt_id=attempt.pk)
            error = exc.messages[0]
        else:
            return redirect("testing_public_result", attempt_id=attempt.pk)

    for question in questions:
        answer = given.get(str(question.pk))
        question.given_text = answer.text if answer else (question.starter_code if question.question_type == QuestionType.CODE else "")
        question.given_options = set(answer.options) if answer else set()
    deadline = attempt_deadline(attempt)
    return render(request, "testing/public/take.html", {
        "attempt": attempt,
        "test": attempt.session.test,
        "questions": questions,
        "deadline": deadline,
        "seconds_left": max(int((deadline - timezone.now()).total_seconds()), 0) if deadline else None,
        "error": error,
        "preview": False,
    })


@never_cache
def result_view(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if attempt.status == AttemptStatus.ACTIVE:
        return redirect("testing_public_take", attempt_id=attempt.pk)
    test = attempt.session.test
    score = attempt_score(attempt) if attempt.question_ids else None
    return render(request, "testing/public/result.html", {
        "attempt": attempt,
        "test": test,
        "score": score,
        "passed": is_passed(attempt, score) if score else None,
        "rows": result_rows(attempt) if test.show_result else [],
        "show_correct": test.show_correct_answers,
        "can_retry": test.allow_retry and attempt.session.effective_status == "running",
    })
