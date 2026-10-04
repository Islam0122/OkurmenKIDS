"""Student portal — mounted at /student/ in config/urls.py (see student_views.py)."""
from django.urls import path

from . import student_api, student_views

exam = "exams/<uuid:exam_id>/"
attempt_api = "api/exam-attempts/<uuid:attempt_id>/"

urlpatterns = [
    path("", student_views.dashboard_view, name="student_portal_dashboard"),
    path("login/", student_views.login_view, name="student_portal_login"),
    path("logout/", student_views.logout_view, name="student_portal_logout"),
    path("exams/", student_views.exams_view, name="student_exams"),
    path(exam + "prepare/", student_views.prepare_view, name="student_exam_prepare"),
    path(exam + "attempt/<uuid:attempt_id>/", student_views.attempt_view, name="student_exam_attempt"),
    path(exam + "attempt/<uuid:attempt_id>/submit/", student_views.submit_view, name="student_exam_submit"),
    path(exam + "result/<uuid:attempt_id>/", student_views.result_view, name="student_exam_result"),
    path(exam + "review/<uuid:attempt_id>/", student_views.review_view, name="student_exam_review"),
    path(attempt_api + "state/", student_api.state_view, name="student_api_attempt_state"),
    path(attempt_api + "answers/", student_api.answers_view, name="student_api_attempt_answers"),
    path(attempt_api + "events/", student_api.events_view, name="student_api_attempt_events"),
]
