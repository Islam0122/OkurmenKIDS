"""Публичный карьерный сайт — /api/v1/public/careers/ (без входа)."""
from django.urls import path

from . import public

urlpatterns = [
    path("filters/", public.FiltersView.as_view(), name="careers-filters"),
    path("vacancies/", public.VacancyListView.as_view(), name="careers-vacancies"),
    path("vacancies/<slug:slug>/", public.VacancyDetailView.as_view(), name="careers-vacancy"),
    path("vacancies/<slug:slug>/apply/", public.ApplyView.as_view(), name="careers-apply"),
]
