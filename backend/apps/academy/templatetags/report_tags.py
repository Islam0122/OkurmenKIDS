"""Template helpers for the 📊 Reports admin pages."""
from __future__ import annotations

from django import template
from django.utils.html import format_html
from django.utils.http import urlencode

from ..services.reports.kpi import kpi_level

register = template.Library()

_LEVEL_CLASSES = {"good": "okr-badge-good", "warning": "okr-badge-warn", "bad": "okr-badge-bad", "none": "okr-badge-none"}
_LEVEL_DOTS = {"good": "🟢", "warning": "🟡", "bad": "🔴", "none": ""}


def _fmt(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):g}".replace(".", ",") + "%"


@register.filter
def pct(value) -> str:
    """`94.4` -> `94,4%`; `None` (no data) -> `—` — never a fabricated 0%."""
    return _fmt(value)


@register.filter
def kpi_badge(value):
    level = kpi_level(value)
    title = "Нет данных за период" if level == "none" else "KPI"
    return format_html(
        '<span class="okr-badge {}" title="{}">{} {}</span>', _LEVEL_CLASSES[level], title, _LEVEL_DOTS[level],
        _fmt(value),
    )


@register.filter
def level_class(value) -> str:
    return {"good": "good", "warning": "warn", "bad": "bad", "none": "none"}[kpi_level(value)]


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
        next_sort, arrow = f"-{key}", " ↑"
    elif current == f"-{key}":
        next_sort, arrow = key, " ↓"
    else:
        next_sort, arrow = (f"-{key}" if default_desc else key), ""
    url = query_with(context, sort=next_sort, page=None)
    return format_html('<a class="okr-sort{}" href="{}">{}{}</a>', " is-active" if arrow else "", url, label, arrow)
