"""Public website API — mounted at /api/v1/public/site/ (see public_views)."""
from django.urls import path

from . import public_views as views

urlpatterns = [
    path("settings/", views.SettingsView.as_view(), name="public-site-settings"),
    path("home/", views.HomeView.as_view(), name="public-site-home"),
    path("courses/", views.CoursesView.as_view(), name="public-site-courses"),
    path("courses/<slug:slug>/", views.CourseView.as_view(), name="public-site-course"),
    path("events/", views.EventsView.as_view(), name="public-site-events"),
    path("events/<slug:slug>/", views.EventView.as_view(), name="public-site-event"),
    path("events/<slug:slug>/register/", views.EventRegisterView.as_view(), name="public-site-event-register"),
    path("achievements/", views.AchievementsView.as_view(), name="public-site-achievements"),
    path("achievements/<slug:slug>/", views.AchievementView.as_view(), name="public-site-achievement"),
    path("team/", views.TeamView.as_view(), name="public-site-team"),
    path("team/<slug:slug>/", views.TeamMemberView.as_view(), name="public-site-team-member"),
    path("testimonials/", views.TestimonialsView.as_view(), name="public-site-testimonials"),
    path("leads/", views.LeadView.as_view(), name="public-site-leads"),
    path("sitemap/", views.SitemapView.as_view(), name="public-site-sitemap"),
    path("preview/<str:token>/", views.PreviewView.as_view(), name="public-site-preview"),
]
