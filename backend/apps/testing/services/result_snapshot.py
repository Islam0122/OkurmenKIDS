"""The historical snapshot a test result keeps (StudentAttempt.group /
teacher / subject / test_title), taken when the attempt starts.

    group    the session's group, else the student's group at that moment
    teacher  the session's teacher, else the group's active teacher of the
             test's subject, else the group's only active teacher
    subject  the test's subject
    title    the test title

Public trainer attempts (no student, no group) keep only subject and title.
"""
from __future__ import annotations


def resolve_teacher_id(session, group_id, subject_id):
    if session.teacher_id:
        return session.teacher_id
    if group_id is None:
        return None
    from apps.academy.models import GroupTeacher

    active = GroupTeacher.objects.filter(group_id=group_id, is_active=True)
    if subject_id is not None:
        match = active.filter(subject_id=subject_id).values_list("teacher_id", flat=True).first()
        if match:
            return match
    ids = list(active.values_list("teacher_id", flat=True).distinct()[:2])
    return ids[0] if len(ids) == 1 else None


def fill_snapshot(attempt) -> None:
    """Fill the empty snapshot fields of a new attempt (never overwrites)."""
    session = attempt.session
    test = session.test
    if attempt.group_id is None:
        attempt.group_id = session.group_id or (attempt.student.group_id if attempt.student_id else None)
    if attempt.subject_id is None:
        attempt.subject_id = test.subject_id
    if attempt.teacher_id is None:
        attempt.teacher_id = resolve_teacher_id(session, attempt.group_id, attempt.subject_id)
    if not attempt.test_title:
        attempt.test_title = test.title[:255]
