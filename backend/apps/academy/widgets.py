"""Custom form widgets for the Academy admin.

Kept separate from admin.py because a widget is reusable form/rendering
logic, not admin wiring — the same pattern as apps/academy/services/ vs.
apps/academy/admin.py.
"""
from __future__ import annotations

from django import forms


class SubjectCardsWidget(forms.SelectMultiple):
    """A drop-in replacement for ``filter_horizontal`` on Course.subjects.

    Renders as a completely ordinary ``<select multiple>`` — so Django's
    form validation and the M2M save on ``form.save()`` work exactly as
    they do for the stock widget — and only adds one thing: a
    ``data-description`` attribute on each ``<option>``, read from the
    ``Subject`` instance Django already attaches to the choice value
    (``ModelChoiceIteratorValue.instance``, a documented Django 3.1+ API
    made exactly for this). ``apps/users/static/okurmenkids/js/ui.js``
    picks up any ``select[multiple].ok-subject-cards-source`` and replaces
    it, visually, with a searchable checkbox-card grid — the underlying
    ``<select>`` stays in the DOM and is what actually submits.
    """

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instance = getattr(value, "instance", None)
        description = getattr(instance, "description", "") if instance is not None else ""
        if description:
            option["attrs"]["data-description"] = description
        return option
