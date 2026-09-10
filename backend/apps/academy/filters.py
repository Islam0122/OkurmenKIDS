"""FilterSets for the academy API.

Kept deliberately small: most endpoints only need exact-match filtering on
a handful of fields (already declared as ``filterset_fields`` on the
viewsets). Custom FilterSet classes here exist only where a plain field
list can't express what's needed — date ranges on Schedule and KPI.
"""
from __future__ import annotations

import django_filters as filters

from .models import KPI, Schedule


class ScheduleFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = Schedule
        fields = ["group", "room", "date", "is_cancelled"]


class KPIFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name="date_from", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="date_to", lookup_expr="lte")

    class Meta:
        model = KPI
        fields = ["student", "group"]
