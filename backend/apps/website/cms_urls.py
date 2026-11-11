"""Marketing CMS — mounted at /api/v1/marketing/site/ (see cms.py)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import cms
from .content_import import views as import_views

router = DefaultRouter()
router.register("courses", cms.CoursePageViewSet, basename="site-course")
router.register("events", cms.EventViewSet, basename="site-event")
router.register("achievements", cms.AchievementViewSet, basename="site-achievement")
router.register("news", cms.NewsViewSet, basename="site-news")
router.register("team", cms.TeamMemberViewSet, basename="site-team")
router.register("testimonials", cms.TestimonialViewSet, basename="site-testimonial")
router.register("stats", cms.StatisticViewSet, basename="site-stat")
router.register("branches", cms.BranchViewSet, basename="site-branch")
router.register("banners", cms.BannerViewSet, basename="site-banner")
router.register("sections", cms.HomeSectionViewSet, basename="site-section")
router.register("media-categories", cms.MediaCategoryViewSet, basename="site-media-category")
router.register("media", cms.MediaAssetViewSet, basename="site-media")
router.register("leads", cms.LeadViewSet, basename="site-lead")
router.register("registrations", cms.RegistrationViewSet, basename="site-registration")
router.register("import", import_views.ImportBatchViewSet, basename="site-import")

urlpatterns = [
    path("meta/", cms.MetaView.as_view(), name="site-cms-meta"),
    path("overview/", cms.OverviewView.as_view(), name="site-cms-overview"),
    path("import/template/", import_views.ImportTemplateView.as_view(), name="site-import-template"),
    path("import/preview/", import_views.ImportPreviewView.as_view(), name="site-import-preview"),
    path("import/meta/", import_views.ImportMetaView.as_view(), name="site-import-meta"),
    path("settings/", cms.SettingsView.as_view(), name="site-cms-settings"),
    path("", include(router.urls)),
]
