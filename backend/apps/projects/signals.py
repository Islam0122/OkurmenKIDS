"""The public gallery cache (public.py) is rebuilt after any change it shows."""
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete

from apps.academy.models import Group, Student

from .images import build_variants, drop_variants, has_variants
from .models import ProjectImage, StudentProject, Technology
from .public import bump_cache_version

for _model in (StudentProject, ProjectImage, Technology, Student, Group):
    post_save.connect(bump_cache_version, sender=_model, dispatch_uid=f"public_projects_save_{_model.__name__}")
    post_delete.connect(bump_cache_version, sender=_model, dispatch_uid=f"public_projects_delete_{_model.__name__}")
m2m_changed.connect(bump_cache_version, sender=StudentProject.technologies.through,
                    dispatch_uid="public_projects_technologies")


def _image_variants_on_save(sender, instance, **kwargs):
    """WebP copies for cards and the gallery (images.py); a new upload has a new
    file name, so this runs once per file."""
    if instance.image and not has_variants(instance.image):
        build_variants(instance.image)


def _image_variants_on_delete(sender, instance, **kwargs):
    # pre_delete: the post_delete handler in models.py deletes the original and
    # clears `image.name`, after which the copies could no longer be found.
    # (A rolled-back delete loses nothing: copies are rebuilt on the next view.)
    drop_variants(instance.image)


post_save.connect(_image_variants_on_save, sender=ProjectImage, dispatch_uid="projects_image_variants_save")
pre_delete.connect(_image_variants_on_delete, sender=ProjectImage, dispatch_uid="projects_image_variants_delete")
