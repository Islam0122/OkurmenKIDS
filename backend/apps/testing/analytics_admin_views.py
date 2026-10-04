"""Analytics of the «Сессии» section (ADMIN role only, scoped by
services.analytics.visible_sessions):

    Аналитика (tree)  Группа → Предмет → Тест → Сессии
      → Группа        tests of the group with their averages
      → Предмет       a subject (optionally within one group)
      → Тест          totals + comparison of its sessions + its questions
      → Сессия        tabs «Вопросы» and «Аналитика» (+ exports)
        → Попытка     question by question

Nothing is stored: every number is counted from StudentAttempt / Answer
with a fixed number of queries per page.
"""
from __future__ import annotations

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.academy.models import Group
from apps.users.models import Subject

from .admin_views import _require_admin
from .models import Answer, AttemptStatus, StudentAttempt, Test
from .services import analytics
from .services.sessions import display_title, sync_due_sessions
from .session_admin_views import _get_session, _workspace_context


def _row_filters(request) -> dict:
    return {
        "status": request.GET.get("status", ""),
        "result": request.GET.get("result", ""),
        "query": request.GET.get("q", "").strip(),
    }


# ---------------------------------------------------------------------------
# One session: «Вопросы», «Аналитика», exports
# ---------------------------------------------------------------------------

def session_questions_view(request, session_id):
    _require_admin(request)
    session = _get_session(request, session_id)
    context = _workspace_context(session, "questions")
    stats = analytics.question_stats([session.pk], session.test.questions.order_by("order", "created_at"))
    low, high = analytics.success_extremes(stats)
    context.update({"questions": stats, "low_success": low, "high_success": high})
    return render(request, "admin/testing/sessions/questions.html", context)


def session_analytics_view(request, session_id):
    _require_admin(request)
    session = _get_session(request, session_id)
    context = _workspace_context(session, "analytics")
    data = analytics.session_analytics(session)
    filters = _row_filters(request)
    rows = analytics.filter_rows(data.rows, **filters)

    subject_summary = None
    if session.test.subject_id:
        scope = analytics.visible_sessions(request.user).filter(test__subject=session.test.subject_id)
        if session.group_id:
            scope = scope.filter(group=session.group_id)
        subject_summary = analytics.summarize_attempts(StudentAttempt.objects.filter(user__isnull=True, session__in=scope))

    query = request.GET.urlencode()
    context.update({
        "a": data,
        "rows": rows,
        "filters": filters,
        "has_filters": any(filters.values()),
        "status_filters": analytics.STATUS_FILTERS,
        "result_filters": analytics.RESULT_FILTERS,
        "export_qs": f"?{query}" if query else "",
        "subject_summary": subject_summary,
        "pass_bar": [
            ("ok", "Успешно", data.passed, data.share(data.passed)),
            ("bad", "Неуспешно", data.failed, data.share(data.failed)),
            ("review", "На проверке", data.under_review, data.share(data.under_review)),
            ("none", "Не завершили", data.not_finished, data.share(data.not_finished)),
        ],
    })
    return render(request, "admin/testing/sessions/analytics.html", context)


EXPORT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
    "pdf": "application/pdf",
}


def session_export_view(request, session_id, fmt):
    """Results export (Excel / CSV / PDF) — respects the table's filters."""
    _require_admin(request)
    if fmt not in EXPORT_TYPES:
        raise Http404("Неизвестный формат.")
    session = _get_session(request, session_id)
    data = analytics.session_analytics(session)
    rows = analytics.filter_rows(data.rows, **_row_filters(request))
    if fmt == "xlsx":
        content = analytics.export_excel(session, rows, data)
    elif fmt == "csv":
        content = analytics.export_csv(session, rows)
    else:
        content = analytics.export_pdf(session, rows, data)
    response = HttpResponse(content, content_type=EXPORT_TYPES[fmt])
    response["Content-Disposition"] = f'attachment; filename="session-{session.key}.{fmt}"'
    return response


def session_results_view(request, session_id):
    """Old «Результаты» address — the results now live in «Аналитика»."""
    _require_admin(request)
    return redirect(reverse("admin:testing_session_analytics", args=[session_id]))


# ---------------------------------------------------------------------------
# Attempt
# ---------------------------------------------------------------------------

def attempt_detail_view(request, attempt_id):
    _require_admin(request)
    attempt = get_object_or_404(
        StudentAttempt.objects.select_related(
            "student", "session__test__subject", "session__group", "session__teacher__user",
        ),
        pk=attempt_id,
    )
    session = attempt.session
    if not analytics.visible_sessions(request.user).filter(pk=session.pk).exists():
        raise Http404("Попытка не найдена.")
    detail = analytics.attempt_detail(attempt)
    others = session.attempts.filter(
        **({"student_id": attempt.student_id} if attempt.student_id else {"student_name": attempt.student_name})
    ).order_by("started_at")
    return render(request, "admin/testing/sessions/attempt.html", {
        "title": f"Попытка: {attempt.student_name}",
        "attempt": attempt,
        "session": session,
        "session_title": display_title(session),
        "student_name": str(attempt.student) if attempt.student_id else attempt.student_name,
        "finished": attempt.status == AttemptStatus.FINISHED,
        "detail": detail,
        "others": others,
        "graded": detail["total"] - detail["pending"],
        # Exam Mode (student portal): violation counters and the event log.
        "events": attempt.events.all() if attempt.exam_mode or attempt.events.exists() else None,
    })


# ---------------------------------------------------------------------------
# Above one session
# ---------------------------------------------------------------------------

def _int(value) -> int | None:
    return int(value) if value and str(value).isdigit() else None


def analytics_tree_view(request):
    """Main analytics screen: Группа → Предмет → Тест → Сессии."""
    _require_admin(request)
    sync_due_sessions()
    sessions = analytics.visible_sessions(request.user)
    group_id = _int(request.GET.get("group"))
    subject_id = _int(request.GET.get("subject"))
    if group_id:
        sessions = sessions.filter(group_id=group_id)
    if subject_id:
        sessions = sessions.filter(test__subject_id=subject_id)
    visible = analytics.visible_sessions(request.user)
    return render(request, "admin/testing/analytics/tree.html", {
        "title": "Аналитика тестов",
        "tree": analytics.analytics_tree(sessions),
        "total": analytics.summarize_attempts(StudentAttempt.objects.filter(user__isnull=True, session__in=sessions)),
        "groups": Group.objects.filter(pk__in=visible.values("group")).order_by("name"),
        "subjects": Subject.objects.filter(pk__in=visible.values("test__subject")).order_by("name"),
        "group_id": group_id,
        "subject_id": subject_id,
    })


def _test_rows(sessions) -> list[dict]:
    """Tests of the given sessions with their (finished-attempt) results."""
    summaries = analytics.test_summaries(StudentAttempt.objects.filter(user__isnull=True, session__in=sessions), by_group=False)
    tests ={t.pk: t for t in Test.objects.filter(pk__in=sessions.values("test")).select_related("subject")}
    by_test = {key[2]: summary for key, summary in summaries.items()}
    rows = [{"test": test, "summary": by_test.get(pk)} for pk, test in tests.items()]
    rows.sort(key=lambda r: (r["test"].subject.name if r["test"].subject_id else "~", r["test"].title.casefold()))
    return rows


def group_analytics_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)
    sessions = analytics.visible_sessions(request.user).filter(group=group)
    tree = analytics.analytics_tree(sessions)
    return render(request, "admin/testing/analytics/group.html", {
        "title": f"Аналитика группы: {group.name}",
        "group": group,
        "crumb_title": group.name,
        "total": analytics.summarize_attempts(StudentAttempt.objects.filter(user__isnull=True, session__in=sessions)),
        "test_rows": _test_rows(sessions),
        "node": tree[0] if tree else None,
    })


def subject_analytics_view(request, subject_id):
    _require_admin(request)
    subject = get_object_or_404(Subject, pk=subject_id)
    sessions = analytics.visible_sessions(request.user).filter(test__subject=subject)
    group = None
    if _int(request.GET.get("group")):
        group = get_object_or_404(Group, pk=request.GET["group"])
        sessions = sessions.filter(group=group)
    return render(request, "admin/testing/analytics/subject.html", {
        "title": f"Аналитика предмета: {subject.name}",
        "subject": subject,
        "group": group,
        "crumb_title": subject.name,
        "total": analytics.summarize_attempts(StudentAttempt.objects.filter(user__isnull=True, session__in=sessions)),
        "test_rows": _test_rows(sessions),
        "sessions": analytics.with_list_stats(sessions).order_by("-created_at"),
    })


def test_analytics_view(request, test_id):
    _require_admin(request)
    test = get_object_or_404(Test.objects.select_related("subject"), pk=test_id)
    sessions = analytics.visible_sessions(request.user).filter(test=test)
    group = None
    if _int(request.GET.get("group")):
        group = get_object_or_404(Group, pk=request.GET["group"])
        sessions = sessions.filter(group=group)
    stats = analytics.question_stats(sessions, test.questions.order_by("order", "created_at"))
    low, high = analytics.success_extremes(stats)
    return render(request, "admin/testing/analytics/test.html", {
        "title": f"Аналитика теста: {test.title}",
        "test": test,
        "group": group,
        "crumb_title": test.title,
        "total": analytics.summarize_attempts(StudentAttempt.objects.filter(user__isnull=True, session__in=sessions)),
        "sessions": analytics.with_list_stats(sessions).order_by("-created_at"),
        "questions": stats,
        "low_success": low,
        "high_success": high,
        "grading": analytics.grading_counts(Answer.objects.filter(attempt__session__in=sessions)),
    })
