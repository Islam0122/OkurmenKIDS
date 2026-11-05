from django.urls import path

from . import views

# Подключено в config/urls.py под /api/v1/monthly-performance/.
urlpatterns = [
    path("", views.MonthlyPerformanceView.as_view(), name="monthly-performance"),
    path("snapshots/", views.SnapshotListView.as_view(), name="monthly-performance-snapshots"),
    path("snapshots/<str:day>/", views.SnapshotCorrectionView.as_view(), name="monthly-performance-snapshot"),
    path("summary/", views.SummaryView.as_view(), name="monthly-performance-summary"),
    path("trends/", views.TrendsView.as_view(), name="monthly-performance-trends"),
]
