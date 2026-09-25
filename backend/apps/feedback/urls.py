from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("feedback/surveys", views.SurveyAdminViewSet, basename="feedback-survey")
router.register("feedback/questions", views.SurveyQuestionAdminViewSet, basename="feedback-question")

urlpatterns = [
    path("feedback/analytics/overview/", views.FeedbackOverviewView.as_view(), name="feedback-overview"),
    path("feedback/public/<str:token>/", views.PublicSurveyView.as_view(), name="feedback-public-api"),
    path(
        "feedback/public/<str:token>/submit/",
        views.PublicSurveySubmitView.as_view(),
        name="feedback-public-submit-api",
    ),
    path("", include(router.urls)),
]
