"""Public (no-login) survey pages, mounted at /feedback/ in config/urls.py."""
from django.urls import path

from . import public_views

urlpatterns = [
    path("s/<str:token>/", public_views.public_survey_view, name="feedback_public"),
    path("s/<str:token>/done/", public_views.public_survey_done_view, name="feedback_public_done"),
]
