"""Make the WebP copies (thumb/large) of every student-project image that has none.

Safe to re-run: images that already have both copies are skipped. New uploads
get their copies automatically (signals.py); this backfills older ones in one
go instead of on their first public view.

    python manage.py build_project_image_variants [--force]
"""
from django.core.management.base import BaseCommand

from apps.projects.images import build_variants, has_variants
from apps.projects.models import ProjectImage


class Command(BaseCommand):
    help = "Build WebP thumb/large copies of student-project images (apps.projects.images)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Rebuild copies that already exist.")

    def handle(self, *args, force=False, **options):
        built = skipped = failed = 0
        for image in ProjectImage.objects.exclude(image="").iterator():
            if not force and has_variants(image.image):
                skipped += 1
            elif build_variants(image.image):
                built += 1
            else:
                failed += 1
        self.stdout.write(f"built={built} skipped={skipped} failed={failed}")
