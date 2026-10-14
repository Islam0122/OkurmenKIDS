from django.urls import path

from . import views

urlpatterns = [
    # The public leaderboard site (no login, GET only, whitelisted fields).
    path("public/leaderboard/meta/", views.LeaderboardMetaView.as_view(), name="public-leaderboard-meta"),
    path("public/leaderboard/students/", views.StudentLeaderboardView.as_view(), name="public-leaderboard-students"),
    path("public/leaderboard/groups/", views.GroupLeaderboardView.as_view(), name="public-leaderboard-groups"),
]
