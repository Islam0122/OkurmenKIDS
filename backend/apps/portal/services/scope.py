"""Which students a portal account may read — the one gate every portal
query passes through. An id that is not linked to the signed-in account is
indistinguishable from one that does not exist (404), so ids of other
students reveal nothing."""
from __future__ import annotations

from django.http import Http404

from apps.academy.models import Student


def linked_students(user):
    """Students linked to `user`'s portal account (empty for anyone else)."""
    if not getattr(user, "is_authenticated", False):
        return Student.objects.none()
    return (
        Student.objects.filter(portal_links__account__user=user)
        .select_related("group__course", "branch")
        .order_by("portal_links__created_at", "pk")
        .distinct()
    )


def get_student(user, student_id) -> Student:
    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        raise Http404
    student = linked_students(user).filter(pk=student_id).first()
    if student is None:
        raise Http404
    return student
