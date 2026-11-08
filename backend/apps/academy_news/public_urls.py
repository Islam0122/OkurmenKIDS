"""Public academy news — mounted at /api/v1/public/news/."""
from django.urls import path

from .public_views import PublicArticleView, PublicNewsListView

urlpatterns = [
    path("", PublicNewsListView.as_view(), name="public-news"),
    path("<str:slug>/", PublicArticleView.as_view(), name="public-news-article"),
]
