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

An exam session opens in the exam portal (the React test screen, Exam Mode
rules: server timer, autosave, current question, violations) when the
portal address is configured — see _start_in_shared_ui. This is the only
way students reach an exam; the server-rendered form here remains the
fallback without a portal address and for staff (LMS handoff).
"""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

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
from .services import handoff
from .services.grading import attempt_score
from .services.participants import attempt_progress, roster_students

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


def _accept_handoff(request, attempt_id) -> bool:
    """`?t=` from the LMS (services.handoff): remember the LMS user's own
    attempt for this browser. True when the URL carried a token — the caller
    then redirects to the clean URL, so the token never stays in history."""
    token = request.GET.get("t")
    if not token:
        return False
    if handoff.verified_attempt_id(token, attempt_id) is None:
        raise Http404("Ссылка недействительна или устарела. Откройте тест заново из LMS.")
    _remember(request, StudentAttempt(pk=attempt_id))
    return True


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
        roster = roster_students(session)
        has_roster = session.group_id is not None or session.participants.exists()
        context["students"] = roster if has_roster else None

        if request.method == "POST" and "start" in request.POST:
            student = None
            name = request.POST.get("student_name", "")
            if has_roster:
                raw = request.POST.get("student") or ""
                student = roster.filter(pk=int(raw)).first() if raw.isdigit() else None
                if student is None:
                    context["error"] = "Выберите себя из списка."
                    return render(request, "testing/public/join.html", context)
            try:
                exam_url = _start_in_shared_ui(request, session, student, name)
                if exam_url:
                    return redirect(exam_url)
                attempt = join(session, student_name=name, student=student)
            except AttemptError as error:
                context["error"] = error.messages[0]
                context["student_name"] = name
                return render(request, "testing/public/join.html", context)
            _remember(request, attempt)
            return redirect("testing_public_take", attempt_id=attempt.pk)
    return render(request, "testing/public/join.html", context)


def _start_in_shared_ui(request, session, student, student_name: str = "") -> str | None:
    """An exam session with the portal configured → the attempt runs in the
    exam portal. Returns where to go; None keeps this page's own form (a
    trainer session, or no portal address).

    The key and the student (roster choice, or the name in a session without
    a roster) are validated here, on the server; the page only receives a
    signed token bound to the attempt. An exam already running in another
    browser is not handed to this one — only the browser that started it
    gets it back after a refresh, so picking someone else's name can't take
    over their exam."""
    from apps.training.exam_api import portal_exam_url
    from apps.training.models import PortalSettings

    from .models import SessionType
    from .services import exam_portal

    if session.session_type != SessionType.EXAM or not PortalSettings.load().portal_url:
        return None
    mine = request.session.get(_ATTEMPTS_SESSION_KEY, [])
    for active in exam_portal.active_attempts(session, student, student_name):
        active.session = session
        if exam_portal.ensure_current(active, request).status == AttemptStatus.ACTIVE and str(active.pk) not in mine:
            raise AttemptError("Этот экзамен уже начат в другом браузере. Продолжите его там, где начали.")
    attempt = exam_portal.start_exam(session, student, request, student_name=student_name)
    _remember(request, attempt)
    return portal_exam_url(attempt)


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
    if _accept_handoff(request, attempt_id):
        return redirect("testing_public_take", attempt_id=attempt_id)
    attempt = _own_attempt(request, attempt_id)
    if attempt.status != AttemptStatus.ACTIVE:
        return redirect("testing_public_result", attempt_id=attempt.pk)
    if attempt.exam_mode:
        # An exam runs only in the exam portal (timer, autosave, rules):
        # this browser started it, so it gets its link back.
        from apps.training.exam_api import portal_exam_url

        if url := portal_exam_url(attempt):
            return redirect(url)
        return render(request, "testing/public/exam_mode_only.html", status=403)
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
    if _accept_handoff(request, attempt_id):
        return redirect("testing_public_result", attempt_id=attempt_id)
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
        "can_retry": test.allow_retry and attempt.session.effective_status == "running" and attempt.user_id is None,
        # An LMS account's own attempt (the Team Lead): back to the session in
        # the LMS instead of the student join page (they aren't on the roster).
        "lms_url": f"{settings.LMS_FRONTEND_URL}/app/exams/{attempt.session_id}" if attempt.user_id else None,
    })


@csrf_protect
def progress_view(request, attempt_id):
    """Heartbeat from the take page: which question is open and how many are
    answered (never the answers themselves); ``left=1`` when the page is
    closed (sent with navigator.sendBeacon, CSRF token in the form data)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    attempt = _own_attempt(request, attempt_id)

    def number(name):
        raw = request.POST.get(name, "")
        return int(raw) if raw.isdigit() else None

    attempt_progress(
        attempt,
        current=number("current"),
        answered=number("answered"),
        left=request.POST.get("left") == "1",
    )
    return JsonResponse({"ok": True, "status": attempt.status})
