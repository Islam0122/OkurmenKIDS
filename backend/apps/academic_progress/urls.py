from django.urls import path

from . import views

urlpatterns = [
    path("meta/", views.MetaView.as_view(), name="academic-progress-meta"),
    path("programs/", views.ProgramsView.as_view(), name="academic-progress-programs"),
    path("programs/<int:pk>/", views.ProgramView.as_view(), name="academic-progress-program"),
    path("groups/<int:pk>/", views.GroupProgressView.as_view(), name="academic-progress-group"),
    path("groups/<int:pk>/history/", views.GroupHistoryView.as_view(), name="academic-progress-group-history"),
]
