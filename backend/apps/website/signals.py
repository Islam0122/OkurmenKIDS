"""Any change of public site content clears the public cache at once.

Also listens to the LMS models the site reads (course, teacher, subject,
user): renaming a course or deactivating a trainer shows up immediately."""
from django.db.models.signals import m2m_changed, post_delete, post_save

from . import models
from .public import bump_cache_version

_SENDERS = (
    models.SiteSettings, models.HomeSection, models.Statistic, models.Branch, models.PromoBanner,
    models.CoursePage, models.TeamMember, models.Event, models.EventPhoto, models.EventRegistration,
    models.Achievement, models.AchievementPhoto, models.Testimonial,
    "academy.Course", "users.Teacher", "users.Subject", "users.User",
)

for _model in _SENDERS:
    _name = _model if isinstance(_model, str) else _model.__name__
    post_save.connect(bump_cache_version, sender=_model, dispatch_uid=f"public_site_save_{_name}")
    post_delete.connect(bump_cache_version, sender=_model, dispatch_uid=f"public_site_delete_{_name}")

for _through in (models.SiteSettings.featured_projects.through, models.SiteSettings.featured_news.through):
    m2m_changed.connect(bump_cache_version, sender=_through, dispatch_uid=f"public_site_m2m_{_through.__name__}")
