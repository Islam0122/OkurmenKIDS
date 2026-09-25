from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("scholarship-periods", views.ScholarshipPeriodViewSet, basename="scholarship-period")
router.register("scholarship-evaluations", views.ScholarshipEvaluationViewSet, basename="scholarship-evaluation")
router.register("scholarship-awards", views.ScholarshipAwardViewSet, basename="scholarship-award")
router.register("scholarship-feedback", views.TrainerFeedbackViewSet, basename="scholarship-feedback")

urlpatterns = [
    path("", include(router.urls)),
]
