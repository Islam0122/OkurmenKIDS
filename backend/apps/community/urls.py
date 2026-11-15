from django.urls import path

from . import views

app_name = "community"

urlpatterns = [
    path("meta/", views.MetaView.as_view(), name="meta"),
    path("posts/", views.PostsView.as_view(), name="posts"),
    path("posts/<int:post_id>/", views.PostView.as_view(), name="post"),
    path("posts/<int:post_id>/<str:action>/", views.ModerateView.as_view(), name="moderate"),
    path("announcements/", views.AnnouncementsView.as_view(), name="announcements"),
    path("reports/", views.ReportsView.as_view(), name="reports"),
    path("reports/<int:report_id>/close/", views.ReportCloseView.as_view(), name="report-close"),
    path("comments/<int:comment_id>/hide/", views.CommentModerationView.as_view(), name="comment-hide"),
    path("media/<str:token>/", views.MediaView.as_view(), name="media"),
]
