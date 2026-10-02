"""Template helpers of the «Тесты» section and the student test pages:
badges (colours from theme.css .ok-badge-*), Russian plurals and the inline
Lucide icons (shared set in apps/academy/templatetags/lucide_icons.py).
"""
from __future__ import annotations

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.academy.templatetags.lucide_icons import ICONS

from ..models import DifficultyLevel, ParticipantStatus, SessionPhase, TestLevel, TestStatus

register = template.Library()

LEVEL_BADGE_CLASSES = {
    DifficultyLevel.EASY: "ok-badge-success",
    DifficultyLevel.MEDIUM: "ok-badge-warning",
    DifficultyLevel.HARD: "ok-badge-danger",
}

STATUS_BADGE_CLASSES = {
    TestStatus.ACTIVE: "ok-badge-success",
    TestStatus.DRAFT: "ok-badge-muted",
    TestStatus.ARCHIVED: "ok-badge-info",
}


def badge(css: str, label: str) -> str:
    return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@register.filter
def level_badge(value: str) -> str:
    """Test.level → «Начальный / Средний / Продвинутый» badge."""
    if value not in TestLevel.values:
        return "—"
    return badge(LEVEL_BADGE_CLASSES[value], TestLevel(value).label)


@register.filter
def difficulty_badge(value: str) -> str:
    """Question.difficulty → «Лёгкий / Средний / Сложный» badge."""
    if value not in DifficultyLevel.values:
        return "—"
    return badge(LEVEL_BADGE_CLASSES[value], DifficultyLevel(value).label)


@register.filter
def status_badge(value: str) -> str:
    if value not in TestStatus.values:
        return "—"
    return badge(STATUS_BADGE_CLASSES[value], TestStatus(value).label)


PHASE_BADGE_CLASSES = {
    SessionPhase.DRAFT: "ok-badge-muted",
    SessionPhase.SCHEDULED: "ok-badge-info",
    SessionPhase.ACTIVE: "ok-badge-success",
    SessionPhase.FINISHED: "ok-badge-muted",
    SessionPhase.CANCELLED: "ok-badge-danger",
}

PARTICIPANT_BADGE_CLASSES = {
    ParticipantStatus.NOT_STARTED: "ok-badge-muted",
    ParticipantStatus.IN_PROGRESS: "ok-badge-success",
    ParticipantStatus.PAUSED: "ok-badge-warning",
    ParticipantStatus.DISCONNECTED: "ok-badge-warning",
    ParticipantStatus.COMPLETED: "ok-badge-info",
    ParticipantStatus.EXPIRED: "ok-badge-danger",
}


@register.filter
def phase_badge(value: str) -> str:
    """Session phase → «Черновик / Запланирована / Активна / …» badge."""
    if value not in SessionPhase.values:
        return "—"
    css = PHASE_BADGE_CLASSES[value]
    if value == SessionPhase.ACTIVE:
        css += " okt-badge-live"
    return badge(css, SessionPhase(value).label)


@register.filter
def participant_badge(value: str) -> str:
    if value not in ParticipantStatus.values:
        return "—"
    return badge(PARTICIPANT_BADGE_CLASSES[value], ParticipantStatus(value).label)


@register.filter
def duration_label(seconds) -> str:
    """`2531` → «42:11», `None` → «—»."""
    from ..services.sessions import format_duration

    return format_duration(seconds)


@register.filter
def pass_badge(passed) -> str:
    """True / False / None (not finished or under review) → badge."""
    if passed is True:
        return badge("ok-badge-success", "Прошёл")
    if passed is False:
        return badge("ok-badge-danger", "Не прошёл")
    return ""


@register.filter
def percent(value, digits=0) -> str:
    """`83.333` → «83%», `None` → «—»."""
    number = _to_number(value)
    if number is None:
        return "—"
    return f"{number:.{int(digits)}f}%".replace(".", ",")


@register.filter
def score_class(value, passing) -> str:
    """CSS modifier for a score vs the test's passing score.

    `0` is a real result (→ fail); a missing score or passing score
    (None, '', '—', garbage) → «oks-empty», never an exception.
    """
    score, passing_score = _to_number(value), _to_number(passing)
    if score is None or passing_score is None:
        return "oks-empty"
    return "okt-pass" if score >= passing_score else "oks-fail"


def _to_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@register.filter
def student_count_label(n) -> str:
    n = int(n or 0)
    return f"{n} {plural_ru(n, 'студент', 'студента', 'студентов')}"


@register.filter
def test_count_label(n) -> str:
    n = int(n or 0)
    return f"{n} {plural_ru(n, 'тест', 'теста', 'тестов')}"


@register.filter
def question_count_label(n) -> str:
    """`155` → «155 вопросов», `1` → «1 вопрос», `0` → «0 вопросов»."""
    n = int(n or 0)
    return f"{n} {plural_ru(n, 'вопрос', 'вопроса', 'вопросов')}"


@register.filter
def attempt_count_label(n) -> str:
    n = int(n or 0)
    return f"{n} {plural_ru(n, 'попытка', 'попытки', 'попыток')}"


@register.filter
def points_label(n) -> str:
    n = int(n or 0)
    return f"{n} {plural_ru(n, 'балл', 'балла', 'баллов')}"


@register.filter
def safe_image_url(value) -> str:
    """The URL only if it is http(s) — anything else (javascript:, data:,
    file:, a typo) renders as no image. Stored URLs are already validated;
    this also guards a value re-displayed after a failed form submit."""
    value = (value or "").strip()
    return value if value.lower().startswith(("http://", "https://")) else ""


@register.simple_tag
def ticon(name: str, size: int = 16, css_class: str = ""):
    """Inline Lucide SVG, decorative (the control next to it has a label)."""
    return format_html(
        '<svg class="okt-icon {}" xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true" focusable="false">{}</svg>',
        css_class, size, size, mark_safe(ICONS[name]),
    )
