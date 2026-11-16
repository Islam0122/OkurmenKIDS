"""Where does each student review stand between the LMS and okurmenkids.com?

    python manage.py community_website_audit                 # read-only report
    python manage.py community_website_audit --name Кенешов   # only matching students
    python manage.py community_website_audit --publish 12 15 --as admin_login

The report changes nothing. For every review post it shows the three
separate states: the LMS (community) status, the family's website consent,
and the website testimonial (status / consent / published_at), and whether
the public API (/api/v1/public/site/testimonials/) returns it right now.

--publish runs the same action as «Опубликовать на сайте» in moderation, as
the given administrator / director, with the same rules (approved review,
family consent, one testimonial per post). Nothing else is ever published.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.community import services
from apps.community.models import Category, Post
from apps.users.models import User


class Command(BaseCommand):
    help = "Read-only report: student reviews in the LMS vs. testimonials on okurmenkids.com (optionally publish)."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="", help="Only students whose first or last name contains this.")
        parser.add_argument("--publish", nargs="+", type=int, default=[], metavar="POST_ID",
                            help="Publish these review posts on the website (as --as).")
        parser.add_argument("--as", dest="as_user", default="", help="Login of the administrator / director publishing.")

    def handle(self, *args, **options):
        from apps.website import public

        if options["publish"]:
            self._publish(options["publish"], options["as_user"])

        qs = (Post.objects.filter(category=Category.REVIEW, author_student__isnull=False)
              .select_related("author_student", "website_testimonial").order_by("-created_at"))
        if options["name"]:
            name = options["name"]
            qs = qs.filter(Q(author_student__first_name__icontains=name) | Q(author_student__last_name__icontains=name))
        on_site = {row["id"] for row in public.testimonials(page_size=36)["results"]} | {
            r["id"] for r in public._visible(public._testimonials())}

        waiting = 0
        self.stdout.write(f"{'post':>6}  {'student':<26} {'LMS':<9} {'consent':<7} {'website testimonial':<34} public API")
        for post in qs:
            t = post.website_testimonial
            site = f"#{t.pk} {t.status} consent={t.consent} at={t.published_at:%Y-%m-%d %H:%M}" if t else "—"
            live = bool(t and t.pk in on_site)
            eligible = services.website_eligible_q()
            is_eligible = Post.objects.filter(pk=post.pk).filter(eligible).exists()
            note = "ON SITE" if live else ("WAITING: «Опубликовать на сайте»" if is_eligible else "not eligible")
            if is_eligible and not live:
                waiting += 1
            student = f"{post.author_student.first_name} {post.author_student.last_name}"[:26]
            self.stdout.write(f"{post.pk:>6}  {student:<26} {post.status:<9} {str(post.website_consent):<7} {site:<34} {note}")
        self.stdout.write(f"\nEligible but not on the website: {waiting}")
        self.stdout.write("Public API filter: status=published AND consent=True AND published_at<=now; cache cleared on every save.")

    def _publish(self, post_ids, login):
        user = User.objects.filter(username=login).first() if login else None
        if user is None:
            raise CommandError("--as: the login of an administrator or director is required.")
        for post in Post.objects.filter(pk__in=post_ids):
            try:
                testimonial = services.publish_to_website(user, post)
            except (ValidationError, PermissionDenied) as exc:
                self.stderr.write(f"post {post.pk}: NOT published — {'; '.join(getattr(exc, 'messages', [str(exc)]))}")
                continue
            self.stdout.write(f"post {post.pk}: published as testimonial #{testimonial.pk}")
