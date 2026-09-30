"""Template helpers for the Reports admin pages."""
from __future__ import annotations

from django import template
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe

from ..services.reports.kpi import LEVEL_LABELS, kpi_level
from .lucide_icons import ICONS

register = template.Library()

_LEVEL_CLASSES = {"good": "good", "warning": "warn", "bad": "bad", "none": "none"}


def _fmt(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):g}".replace(".", ",") + "%"


@register.simple_tag
def icon(name: str, size: int = 16, css_class: str = ""):
    """Inline Lucide SVG. Decorative (aria-hidden): every icon sits next to
    a visible text label, or its button carries its own aria-label."""
    return format_html(
        '<svg class="okr-icon {}" xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true" focusable="false">{}</svg>',
        css_class, size, size, mark_safe(ICONS[name]),
    )


@register.filter
def pct(value) -> str:
    """`94.4` -> `94,4%`; `None` (no data) -> `—` — never a fabricated 0%."""
    return _fmt(value)


@register.filter
def kpi_badge(value):
    """`94,4%` plus a text level ("Хороший" / "Требует внимания" / "Низкий")
    — color is only a secondary cue."""
    level = kpi_level(value)
    if level == "none":
        return format_html('<span class="okr-kpi"><span class="okr-status-badge is-none">{}</span></span>',
                           LEVEL_LABELS["none"])
    return format_html(
        '<span class="okr-kpi"><span class="okr-kpi-value">{}</span>'
        '<span class="okr-status-badge is-{}"><span class="okr-dot" aria-hidden="true"></span>{}</span></span>',
        _fmt(value), _LEVEL_CLASSES[level], LEVEL_LABELS[level],
    )


@register.filter
def level_class(value) -> str:
    return _LEVEL_CLASSES[kpi_level(value)]


@register.filter
def level_label(value) -> str:
    return LEVEL_LABELS[kpi_level(value)]


@register.simple_tag(takes_context=True)
def query_with(context, **overrides) -> str:
    """The current query string with some params replaced (None drops one)."""
    params = context["request"].GET.copy()
    for key, value in overrides.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    return "?" + urlencode(sorted((k, v) for k in params for v in params.getlist(k)))


@register.simple_tag(takes_context=True)
def sort_link(context, key: str, label: str, default_desc: bool = False):
    """Column header link that toggles sort by `key` (asc/desc)."""
    current = context["request"].GET.get("sort") or context.get("default_sort", "name")
    if current == key:
        next_sort, title, icon_name = f"-{key}", "Сортировка по возрастанию", "chevron-up"
    elif current == f"-{key}":
        next_sort, title, icon_name = key, "Сортировка по убыванию", "chevron-down"
    else:
        next_sort, title, icon_name = (f"-{key}" if default_desc else key), "Сортировать", "chevrons-up-down"
    url = query_with(context, sort=next_sort, page=None)
    active = current.lstrip("-") == key
    return format_html(
        '<a class="okr-sort{}" href="{}" title="{}">{}{}</a>',
        " is-active" if active else "", url, title, label, icon(icon_name, 12, "okr-sort-icon"),
    )


_STUDENT_STATUS = {
    "active": ("Активный", "good"),
    "withdrawn": ("Ушёл", "bad"),
    "paused": ("Приостановлен", "warn"),
    "completed": ("Завершил обучение", "none"),
}


@register.filter
def student_status_badge(status: str):
    label, css = _STUDENT_STATUS.get(status, (status, "none"))
    return format_html('<span class="okr-status-badge is-{}">{}</span>', css, label)
