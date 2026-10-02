"""Badges and labels shared by the Testing admin (admin.py list columns and
the admin/testing/* templates), so a level/status looks the same everywhere.

Colours come from theme.css's .ok-badge-* classes (light/dark aware).
"""
from __future__ import annotations

from django import template
from django.utils.html import format_html

from ..models import DifficultyLevel

register = template.Library()

DIFFICULTY_BADGE_CLASSES = {
    DifficultyLevel.EASY: "ok-badge-success",
    DifficultyLevel.MEDIUM: "ok-badge-warning",
    DifficultyLevel.HARD: "ok-badge-danger",
}


def badge(css: str, label: str) -> str:
    return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@register.filter
def difficulty_badge(value: str) -> str:
    """`"easy"` → green «Лёгкий» badge (also used for Test.level)."""
    if value not in DifficultyLevel.values:
        return "—"
    return badge(DIFFICULTY_BADGE_CLASSES[value], DifficultyLevel(value).label)


@register.filter
def active_badge(is_active: bool) -> str:
    return badge("ok-badge-success", "Активен") if is_active else badge("ok-badge-muted", "Неактивен")


@register.filter
def question_count_label(n: int) -> str:
    """`155` → «155 вопросов», `1` → «1 вопрос», `0` → «0 вопросов»."""
    n = n or 0
    return f"{n} {plural_ru(n, 'вопрос', 'вопроса', 'вопросов')}"
