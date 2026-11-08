"""The public gallery cache (public.py) is rebuilt after any change it shows."""
from django.db.models.signals import m2m_changed, post_delete, post_save

from apps.academy.models import Group, Student

from .models import ProjectImage, StudentProject, Technology
from .public import bump_cache_version

for _model in (StudentProject, ProjectImage, Technology, Student, Group):
    post_save.connect(bump_cache_version, sender=_model, dispatch_uid=f"public_projects_save_{_model.__name__}")
    post_delete.connect(bump_cache_version, sender=_model, dispatch_uid=f"public_projects_delete_{_model.__name__}")
m2m_changed.connect(bump_cache_version, sender=StudentProject.technologies.through,
                    dispatch_uid="public_projects_technologies")
