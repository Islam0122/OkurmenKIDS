"""Who sees what.

Students (through the account's own child — portal scope.get_student):
* the feed: APPROVED posts for the whole academy, plus APPROVED posts meant
  only for the student's current group;
* their own posts in any state (drafts, pending, rejected with feedback).
Nothing else — no pending or hidden post of anyone else, no other group's
group-only posts.

Staff moderators:
* admin, director, operations director, team lead, assistant — everything;
* a trainer — posts of students of the groups they teach (an active
  GroupTeacher), and announcements for those groups;
* the website hand-off (reviews → testimonials CMS): admin, director,
  operations director.
Moderators never get access to student accounts through this module.
"""
from __future__ import annotations

from django.db.models import Q
from django.http import Http404

from apps.academy.models import GroupTeacher, Student
from apps.users.models import User

from .models import Audience, Post, PostStatus

FULL_MODERATORS = (User.Role.ADMIN, User.Role.DIRECTOR, User.Role.OPERATIONS_DIRECTOR, User.Role.TEAM_LEAD,
                   User.Role.ASSISTANT)
WEBSITE_EDITORS = (User.Role.ADMIN, User.Role.DIRECTOR, User.Role.OPERATIONS_DIRECTOR)
CAN_POST = (Student.Status.ACTIVE, Student.Status.PAUSED)


# ------------------------------------------------------------ students

def can_post(student: Student) -> bool:
    return student.status in CAN_POST


def feed_q(student: Student) -> Q:
    visible = Q(audience=Audience.ACADEMY)
    if student.group_id:
        visible |= Q(audience=Audience.GROUP, group_id=student.group_id)
    return Q(status=PostStatus.APPROVED) & visible


def feed(student: Student):
    return Post.objects.filter(feed_q(student))


def visible_post(student: Student, post_id) -> Post:
    """A post the student may open: in the feed, or their own."""
    post = Post.objects.filter(Q(pk=post_id) & (feed_q(student) | Q(author_student=student))).first()
    if post is None:
        raise Http404
    return post


def own_post(student: Student, post_id) -> Post:
    post = Post.objects.filter(pk=post_id, author_student=student).first()
    if post is None:
        raise Http404
    return post


# ------------------------------------------------------------ staff

def _active(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False) and user.is_active)


def is_moderator(user) -> bool:
    return _active(user) and (user.is_superuser or user.role in FULL_MODERATORS or user.role == User.Role.TEACHER)


def moderated_groups(user) -> set[int] | None:
    """None = every group; otherwise the groups this trainer teaches."""
    if user.is_superuser or user.role in FULL_MODERATORS:
        return None
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        return set()
    return set(GroupTeacher.objects.filter(teacher=teacher, is_active=True).values_list("group_id", flat=True))


def staff_posts(user):
    groups = moderated_groups(user)
    qs = Post.objects.all()
    if groups is None:
        return qs
    return qs.filter(Q(group_id__in=groups) | Q(author_student__group_id__in=groups) | Q(author=user)).distinct()


def can_publish_academy_wide(user) -> bool:
    return moderated_groups(user) is None


def can_send_to_website(user) -> bool:
    return _active(user) and (user.is_superuser or user.role in WEBSITE_EDITORS)
