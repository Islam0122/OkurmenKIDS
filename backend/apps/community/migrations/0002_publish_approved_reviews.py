"""Approved student reviews whose family allowed the website are now published
on okurmenkids.com by the approval itself. This publishes the ones approved
before that change and never put on the site (no website testimonial yet).

Only: status approved, category review, website_consent, a student author,
no testimonial linked. A review that already has a testimonial (published,
or taken off by an administrator) is left exactly as it is; nothing is
duplicated; no other post is touched."""
from django.db import migrations
from django.utils import timezone

KY_LETTERS = set("ңөүҢӨҮ")


def language_of(text: str) -> str:
    letters = [ch for ch in text if ch.isalpha()]
    if any(ch in KY_LETTERS for ch in letters):
        return "ky"
    if letters and sum(1 for ch in letters if ch.isascii()) / len(letters) > 0.6:
        return "en"
    return "ru"


def publish_waiting(apps, schema_editor):
    Post = apps.get_model("community", "Post")
    Testimonial = apps.get_model("website", "Testimonial")
    now = timezone.now()
    created = 0
    posts = (Post.objects.filter(status="approved", category="review", website_consent=True,
                                 author_student__isnull=False, website_testimonial__isnull=True)
             .select_related("author_student", "group__course").order_by("published_at", "pk"))
    for post in posts:
        student = post.author_student
        initial = f" {student.last_name[:1]}." if student.last_name else ""
        testimonial = Testimonial.objects.create(
            author_name=f"{student.first_name}{initial}"[:120], author_role="student",
            course_label=(post.group.course.name if post.group_id else "")[:120], text=post.text,
            language=language_of(post.text), consent=True, status="published", published_at=now,
            created_by_id=post.moderated_by_id, reviewed_by_id=post.moderated_by_id,
        )
        Post.objects.filter(pk=post.pk).update(website_testimonial=testimonial)
        created += 1
    if created:
        from apps.website.public import bump_cache_version

        bump_cache_version()  # the public API shows them on the next request


class Migration(migrations.Migration):

    dependencies = [
        ("community", "0001_initial"),
        ("website", "0008_team_member_category"),
    ]

    operations = [migrations.RunPython(publish_waiting, migrations.RunPython.noop)]
