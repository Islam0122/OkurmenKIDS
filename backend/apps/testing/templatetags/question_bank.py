"""Template helpers of the «Тесты» section and the student test pages:
badges (colours from theme.css .ok-badge-*), Russian plurals and the inline
Lucide icons (shared set in apps/academy/templatetags/lucide_icons.py).
"""
from __future__ import annotations

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.academy.templatetags.lucide_icons import ICONS

from ..models import DifficultyLevel, TestLevel, TestStatus

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


@register.simple_tag
def ticon(name: str, size: int = 16, css_class: str = ""):
    """Inline Lucide SVG, decorative (the control next to it has a label)."""
    return format_html(
        '<svg class="okt-icon {}" xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true" focusable="false">{}</svg>',
        css_class, size, size, mark_safe(ICONS[name]),
    )
