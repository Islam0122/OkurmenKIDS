from django.urls import path

from . import views

urlpatterns = [
    path("meta/", views.MetaView.as_view(), name="attendance-matrix-meta"),
    path("overview/", views.OverviewView.as_view(), name="attendance-matrix-overview"),
    path("overview/export/", views.OverviewExportView.as_view(), name="attendance-matrix-overview-export"),
    path("groups/<int:pk>/", views.GroupMatrixView.as_view(), name="attendance-matrix-group"),
    path("groups/<int:pk>/export/", views.GroupExportView.as_view(), name="attendance-matrix-group-export"),
    path("cell/", views.CellView.as_view(), name="attendance-matrix-cell"),
    path("settings/", views.SettingsView.as_view(), name="attendance-matrix-settings"),
]
