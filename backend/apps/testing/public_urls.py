"""Student test pages (no login) — mounted at /exam/ in config/urls.py."""
from django.urls import path

from . import public_views

urlpatterns = [
    path("", public_views.join_view, name="testing_public_join"),
    path("a/<uuid:attempt_id>/", public_views.take_view, name="testing_public_take"),
    path("a/<uuid:attempt_id>/result/", public_views.result_view, name="testing_public_result"),
    path("a/<uuid:attempt_id>/progress/", public_views.progress_view, name="testing_public_progress"),
]
