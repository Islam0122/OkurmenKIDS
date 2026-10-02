"""«Сессии» — test sessions as their own admin section (ADMIN role only).

A test defines *what* is asked; a session defines *who* takes it, *when*,
for which group, with how much time and attempts, and collects results:

    Сессии (list) → + Создать сессию
                  → Сессия: Обзор · Участники · Результаты · Активность · Настройки

Live parts (participants, activity) refresh themselves by polling a
server-rendered fragment every few seconds — the project has no WebSocket
infrastructure, and this needs none.
"""
from __future__ import annotations

import uuid

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode

from apps.academy.models import Group

from .admin_views import _require_admin
from .forms import SessionForm
from .models import (
    ParticipantStatus,
    SessionPhase,
    SessionTransitionError,
    Test,
    TestSession,
)
from .services.participants import session_counts
from .services.sessions import (
    display_title,
    export_results_excel,
    export_results_pdf,
    filter_by_phase,
    result_rows,
    session_date,
    sync_due_sessions,
)

PHASE_TABS = (
    ("all", "Все"),
    (SessionPhase.ACTIVE, "Активные"),
    (SessionPhase.SCHEDULED, "Запланированные"),
    (SessionPhase.DRAFT, "Черновики"),
    (SessionPhase.FINISHED, "Завершённые"),
    (SessionPhase.CANCELLED, "Отменённые"),
)

LIVE_REFRESH_SECONDS = 5


def _session_url(session, tab: str = "overview") -> str:
    names = {
        "overview": "admin:testing_testsession_change",
        "participants": "admin:testing_session_participants",
        "results": "admin:testing_session_results",
        "activity": "admin:testing_session_activity",
        "settings": "admin:testing_session_settings",
    }
    return reverse(names[tab], args=[session.pk])


def _get_session(session_id) -> TestSession:
    session = get_object_or_404(
        TestSession.objects.select_related("test", "test__subject", "group", "teacher__user"), pk=session_id,
    )
    session.sync_schedule()
    return session


# ---------------------------------------------------------------------------
# List / create
# ---------------------------------------------------------------------------

def sessions_list_view(request):
    _require_admin(request)
    sync_due_sessions()
    params = request.GET
    query = (params.get("q") or "").strip()
    phase = params.get("status") or "all"
    group_id = params.get("group") or ""
    test_id = params.get("test") or ""
    date = params.get("date") or ""

    sessions = (
        TestSession.objects.select_related("test", "group")
        .annotate(participants_total=Count("participants", distinct=True))
        .order_by("-scheduled_start", "-created_at")
    )
    base = sessions
    if query:
        sessions = sessions.filter(
            Q(title__icontains=query) | Q(test__title__icontains=query)
            | Q(group__name__icontains=query) | Q(key__icontains=query)
        )
    if group_id.isdigit():
        sessions = sessions.filter(group_id=group_id)
    if test_id:
        try:
            sessions = sessions.filter(test_id=uuid.UUID(test_id))
        except ValueError:
            test_id = ""
    if date:
        try:
            day = timezone.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            date = ""
        else:
            sessions = sessions.filter(
                Q(scheduled_start__date=day) | Q(scheduled_start__isnull=True, created_at__date=day)
            )
    counts = {key: (base if key == "all" else filter_by_phase(base, key)).count() for key, _ in PHASE_TABS}
    sessions = filter_by_phase(sessions, phase) if phase != "all" else sessions

    page = Paginator(sessions, 20).get_page(params.get("page"))
    now = timezone.now()
    cards = []
    for session in page.object_list:
        participants = list(session.participants.all())
        cards.append({
            "session": session,
            "title": display_title(session),
            "when": session_date(session),
            "phase": session.phase_at(now),
            "counts": session_counts(session, participants, now) if participants else None,
            "students_total": len(participants) or (
                session.group.students.filter(status="active").count() if session.group_id else 0
            ),
        })
    filter_query = {k: v for k, v in (("q", query), ("group", group_id), ("test", test_id), ("date", date)) if v}
    return render(request, "admin/testing/sessions/list.html", {
        "title": "Сессии",
        "page": page,
        "cards": cards,
        "query": query,
        "phase": phase,
        "group_id": group_id,
        "test_id": str(test_id),
        "date": date,
        "tabs": [{"key": k, "label": label, "count": counts[k], "active": k == phase} for k, label in PHASE_TABS],
        "groups": Group.objects.order_by("name"),
        "tests": Test.objects.order_by("title"),
        "filter_qs": urlencode(filter_query),
        "has_filters": bool(filter_query),
    })


def _test_choices():
    """Test info for the create/settings page (shown when a test is picked)."""
    return {
        str(t.pk): {
            "level": t.get_level_display(),
            "questions": t.questions_total,
            "time": t.time_limit_minutes,
            "passing": t.passing_score,
            "subject": t.subject.name if t.subject_id else "",
        }
        for t in Test.objects.select_related("subject").annotate(questions_total=Count("questions"))
    }


def session_create_view(request):
    _require_admin(request)
    initial = {"all_students": True, "max_attempts": 1}
    if request.GET.get("test"):
        initial["test"] = request.GET["test"]
    form = SessionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            session = form.save(teacher=getattr(request.user, "teacher_profile", None))
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            messages.success(request, f"Сессия создана. Ключ для студентов: {session.key}")
            return redirect(_session_url(session))
    return render(request, "admin/testing/sessions/form.html", {
        "title": "Создание сессии",
        "form": form,
        "test_info": _test_choices(),
        "creating": True,
    })


def group_students_view(request, group_id):
    """Active students of a group, for the roster checklist."""
    _require_admin(request)
    students = SessionForm.group_students(group_id)
    return JsonResponse({"students": [{"id": s.pk, "name": str(s)} for s in students]})


# ---------------------------------------------------------------------------
# Session workspace
# ---------------------------------------------------------------------------

def _workspace_context(session: TestSession, tab: str) -> dict:
    tabs = [
        ("overview", "Обзор", "chart-column"),
        ("participants", "Участники", "users"),
        ("results", "Результаты", "target"),
        ("activity", "Активность", "activity"),
        ("settings", "Настройки", "settings"),
    ]
    participants = list(session.participants.select_related("student", "attempt"))
    now = timezone.now()
    return {
        "title": display_title(session),
        "session": session,
        "session_title": display_title(session),
        "phase": session.phase_at(now),
        "when": session_date(session),
        "participants": participants,
        "counts": session_counts(session, participants, now),
        "active_tab": tab,
        "tabs": [{"key": k, "label": label, "icon": icon, "url": _session_url(session, k)} for k, label, icon in tabs],
        "join_url": None,
        "live": session.phase_at(now) == SessionPhase.ACTIVE,
        "refresh_seconds": LIVE_REFRESH_SECONDS,
    }


def _participant_rows(session: TestSession, participants) -> list[dict]:
    now = timezone.now()
    rows = []
    for participant in participants:
        participant.session = session
        status = participant.live_status_at(now)
        rows.append({
            "participant": participant,
            "status": status,
            "status_label": ParticipantStatus(status).label,
            "progress_percent": (
                round(participant.answered_count / participant.question_total * 100)
                if participant.question_total else 0
            ),
            # The score only once the student has finished.
            "score": participant.score if status == ParticipantStatus.COMPLETED else None,
            "duration": participant.duration_seconds,
        })
    return rows


def session_overview_view(request, session_id):
    _require_admin(request)
    session = _get_session(session_id)
    context = _workspace_context(session, "overview")
    context["join_url"] = request.build_absolute_uri(reverse("testing_public_join")) + f"?key={session.key}"
    context["test_questions"] = session.test.questions.count()
    return render(request, "admin/testing/sessions/overview.html", context)


def session_participants_view(request, session_id):
    _require_admin(request)
    session = _get_session(session_id)
    context = _workspace_context(session, "participants")
    context["rows"] = _participant_rows(session, context["participants"])
    if request.GET.get("fragment"):
        return render(request, "admin/testing/sessions/_participants_table.html", context)
    return render(request, "admin/testing/sessions/participants.html", context)


def session_results_view(request, session_id):
    _require_admin(request)
    session = _get_session(session_id)
    context = _workspace_context(session, "results")
    context["results"] = result_rows(session)
    return render(request, "admin/testing/sessions/results.html", context)


def session_export_view(request, session_id, fmt):
    _require_admin(request)
    session = _get_session(session_id)
    filename = f"session-{session.key}"
    if fmt == "xlsx":
        response = HttpResponse(
            export_results_excel(session),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    elif fmt == "pdf":
        response = HttpResponse(export_results_pdf(session), content_type="application/pdf")
    else:
        return HttpResponse(status=404)
    response["Content-Disposition"] = f'attachment; filename="{filename}.{fmt}"'
    return response


def session_activity_view(request, session_id):
    _require_admin(request)
    session = _get_session(session_id)
    context = _workspace_context(session, "activity")
    context["rows"] = _participant_rows(session, context["participants"])
    context["events"] = _activity_events(context["participants"])
    if request.GET.get("fragment"):
        return render(request, "admin/testing/sessions/_activity_live.html", context)
    return render(request, "admin/testing/sessions/activity.html", context)


def _activity_events(participants) -> list[dict]:
    """Recent events derived from participants' timestamps (newest first)."""
    events = []
    for p in participants:
        name = str(p.student)
        if p.started_at:
            events.append({"at": p.started_at, "kind": "started", "text": f"{name} начал(а) тест"})
        if p.left_at and p.status == ParticipantStatus.IN_PROGRESS:
            events.append({"at": p.left_at, "kind": "left", "text": f"{name}: соединение потеряно"})
        if p.finished_at and p.status == ParticipantStatus.COMPLETED:
            events.append({"at": p.finished_at, "kind": "finished", "text": f"{name} завершил(а) тест"})
    return sorted(events, key=lambda e: e["at"], reverse=True)[:30]


def session_settings_view(request, session_id):
    _require_admin(request)
    session = _get_session(session_id)
    form = SessionForm(request.POST or None, session=session)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            messages.success(request, "Настройки сессии сохранены.")
            return redirect(_session_url(session, "settings"))
    context = _workspace_context(session, "settings")
    context.update({"form": form, "test_info": _test_choices(), "creating": False})
    return render(request, "admin/testing/sessions/settings.html", context)


def session_action_view(request, session_id, action):
    """Start now / pause / resume / finish / cancel."""
    _require_admin(request)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    session = _get_session(session_id)
    if action not in ("start", "pause", "resume", "finish", "cancel"):
        return HttpResponse(status=404)
    try:
        getattr(session, action)()
    except SessionTransitionError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, f"Сессия: «{session.phase_label}».")
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect(_session_url(session))
