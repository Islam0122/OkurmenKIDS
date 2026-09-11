"""Role-based permissions for the academy app.

Academy has no roles of its own — it reuses ``apps.users.models.User.Role``
(ADMIN / TEACHER). Admin has full access everywhere; a Teacher may only
read or write data that belongs to their own groups. Object-level scoping
here is a second line of defence — ``get_queryset()`` in each viewset
already excludes other teachers' data, so a Teacher normally gets a plain
404, not a 403.
"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import User


def _is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.role == User.Role.ADMIN))


def _teacher_profile(user):
    return getattr(user, "teacher_profile", None)


def _lesson_of(obj):
    """Best-effort walk from a Lesson/Attendance/Homework/HomeworkResult
    object to the Lesson it belongs to."""
    from apps.academy.models import Lesson

    if isinstance(obj, Lesson):
        return obj
    if hasattr(obj, "lesson_id"):
        return obj.lesson
    if hasattr(obj, "homework_id"):
        return obj.homework.lesson
    return None


def _teacher_owns_lesson(teacher, lesson) -> bool:
    """True only if `teacher` is the one actually giving `lesson` — not just
    any teacher with a stake in the same Group.

    A Group can have several teachers, each running their own independent
    TeachingAssignment (see apps.academy.models.GroupTeacher): every teacher
    is isolated to their own Lessons/Attendance/Homework, even within a
    Group they share with other teachers and the very same students.
    """
    if lesson is None:
        return False
    owner = lesson.effective_teacher
    return owner is not None and owner.id == teacher.id


class IsAdminOrReadOnly(BasePermission):
    """Any authenticated user may read; only Admin may write.

    Used for reference/catalogue data an Admin manages centrally (Course,
    CourseLessonPlan, Room, Group, Student) — a Teacher still only *sees*
    their own slice of it, via the viewset's queryset.
    """

    message = "Изменять эти данные может только администратор."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return _is_admin(user)


class IsAdminOrOwningTeacher(BasePermission):
    """Admin has full access; a Teacher may write only within their own groups.

    Used for the day-to-day teaching records a Teacher is expected to
    maintain themselves: Lesson (update only), Attendance, Homework,
    HomeworkResult.
    """

    message = "Вы можете работать только со своими группами."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if _is_admin(user):
            return True
        if request.method in SAFE_METHODS:
            return True

        teacher = _teacher_profile(user)
        lesson = _lesson_of(obj)
        return bool(teacher and _teacher_owns_lesson(teacher, lesson))
