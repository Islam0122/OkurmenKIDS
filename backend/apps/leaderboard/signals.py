"""Leaderboard cache invalidation: any change to a source of XP (attendance,
homework results, test attempts) or to who is listed (students, groups,
lessons) makes the next public request rebuild instead of waiting for the
cache TTL. Bulk `.update()` calls bypass signals — the short TTL covers those.
"""
from django.db.models.signals import post_delete, post_save

from apps.academy.models import Attendance, Course, Group, Homework, HomeworkResult, Lesson, Student
from apps.testing.models import AttemptStatus, StudentAttempt

from .services import bump_cache_version

for _model in (Attendance, Course, Group, Homework, HomeworkResult, Lesson, Student):
    post_save.connect(bump_cache_version, sender=_model, dispatch_uid=f"leaderboard_save_{_model.__name__}")
    post_delete.connect(bump_cache_version, sender=_model, dispatch_uid=f"leaderboard_delete_{_model.__name__}")


def _attempt_saved(sender, instance, **kwargs):
    # An attempt in progress autosaves every few seconds and earns nothing
    # yet — only a finished (or re-graded) one can move the leaderboard.
    if instance.status != AttemptStatus.ACTIVE:
        bump_cache_version()


post_save.connect(_attempt_saved, sender=StudentAttempt, dispatch_uid="leaderboard_save_StudentAttempt")
post_delete.connect(bump_cache_version, sender=StudentAttempt, dispatch_uid="leaderboard_delete_StudentAttempt")
