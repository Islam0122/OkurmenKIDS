"""Template helpers for «Контроль тренеров» — display only: every status,
level and label comes ready-made from services.control."""
from __future__ import annotations

from django import template
from django.utils.html import format_html

from .report_tags import icon

register = template.Library()

_STATUS_CSS = {"ok": "good", "attention": "warn", "problem": "bad", "no_data": "none", "upcoming": "info",
               "cancelled": "none"}
_LEVEL = {"ok": ("good", "circle-check"), "warning": ("warn", "triangle-alert"), "danger": ("bad", "circle-x"),
          "none": ("none", "minus")}
_LEVEL_TITLE = {"ok": "заполнено", "warning": "есть пропуски", "danger": "не заполнено", "none": "не требуется"}


@register.simple_tag
def control_badge(status: str, label: str):
    """Text status badge — color only reinforces the label."""
    return format_html(
        '<span class="okr-status-badge is-{}"><span class="okr-dot" aria-hidden="true"></span>{}</span>',
        _STATUS_CSS.get(status, "none"), label,
    )


@register.filter
def control_cell(component: dict):
    """`8/8` with a check / warning / cross icon for its backend level; `—`
    when nothing was required in the period."""
    if not component["total"]:
        return format_html('<span class="okc-cell is-none" title="{}">{}—</span>', _LEVEL_TITLE["none"],
                           icon("minus", 14))
    css, icon_name = _LEVEL[component["level"]]
    return format_html(
        '<span class="okc-cell is-{}" title="{} из {} — {}">{}{}/{}</span>',
        css, component["completed"], component["total"], _LEVEL_TITLE[component["level"]],
        icon(icon_name, 14), component["completed"], component["total"],
    )


@register.filter
def state_css(state: str) -> str:
    """A lesson component's state (services.control.rules COMPONENT_*) -> css tone."""
    return {"ok": "good", "partial": "warn", "missing": "bad", "unchecked": "bad"}.get(state, "none")
