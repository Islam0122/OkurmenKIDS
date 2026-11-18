"""API — /api/v1/bulk-copy/operations/ (see services/engine.py for the rules).

    GET  options/                 groups the user may read
    GET  options/?group=<id>      + that group's subjects
    POST preview/                 dry run: lessons, suggested/validated mapping,
                                  students (matched / unmatched), records, summary, fingerprint
    POST /                        apply (fingerprint, operation_id, confirm_overwrite)
    GET  /                        audit log
    GET  <id>/                    one operation with its records
    POST <id>/undo/               safe undo
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.academy.models import Group, Lesson
from apps.attendance_matrix import access as matrix_access
from apps.users.models import Subject

from . import access
from .models import BulkCopyItem, BulkCopyOperation, Category
from .services import engine, operations

ERROR_STATUS = {
    "invalid": status.HTTP_400_BAD_REQUEST,
    "forbidden": status.HTTP_403_FORBIDDEN,
    "conflict": status.HTTP_409_CONFLICT,
    "confirmation_required": status.HTTP_428_PRECONDITION_REQUIRED,
}


class CanBulkCopy(BasePermission):
    message = "Массовое копирование доступно администратору или сотруднику с отдельным разрешением."

    def has_permission(self, request, view) -> bool:
        return access.can_use(request.user)


class PairSerializer(serializers.Serializer):
    source = serializers.IntegerField(min_value=1)
    target = serializers.IntegerField(min_value=1)


class RequestSerializer(serializers.Serializer):
    source_group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all())
    source_subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    source_start = serializers.DateField()
    source_end = serializers.DateField()
    target_group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all())
    target_subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    target_start = serializers.DateField()
    target_end = serializers.DateField()
    categories = serializers.ListField(child=serializers.ChoiceField(choices=Category.values), min_length=1, max_length=3)
    lesson_map = PairSerializer(many=True, required=False, allow_null=True, default=None)
    mode = serializers.ChoiceField(choices=["all", "selected"], default="all")
    student_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list,
                                        max_length=500)
    conflict = serializers.ChoiceField(choices=["preserve", "overwrite"], default="preserve")
    skip_empty = serializers.BooleanField(default=True)
    copy_comments = serializers.BooleanField(default=False)

    def to_request(self) -> engine.CopyRequest:
        d = self.validated_data
        lesson_map = None if d["lesson_map"] is None else tuple((p["source"], p["target"]) for p in d["lesson_map"])
        return engine.CopyRequest(
            source_group=d["source_group"], source_subject=d["source_subject"],
            source_start=d["source_start"], source_end=d["source_end"],
            target_group=d["target_group"], target_subject=d["target_subject"],
            target_start=d["target_start"], target_end=d["target_end"],
            categories=frozenset(d["categories"]), lesson_map=lesson_map,
            student_ids=tuple(sorted(set(d["student_ids"]))) if d["mode"] == "selected" else None,
            overwrite=d["conflict"] == "overwrite", skip_empty=d["skip_empty"], copy_comments=d["copy_comments"],
        )


class ApplySerializer(RequestSerializer):
    fingerprint = serializers.CharField(max_length=64)
    operation_id = serializers.UUIDField()
    confirm_overwrite = serializers.BooleanField(default=False)


# ---------------------------------------------------------------- payloads

def _lesson(lesson: Lesson | None) -> dict | None:
    if lesson is None:
        return None
    teacher = lesson.effective_teacher
    return {
        "id": lesson.pk, "date": lesson.date, "start": lesson.start_time.strftime("%H:%M") if lesson.start_time else None,
        "topic": lesson.topic, "lesson_number": lesson.lesson_number, "status": lesson.status,
        "teacher": str(teacher) if teacher else None,
    }


def _record(rec: engine.Record) -> dict:
    return {
        "kind": rec.kind, "student": rec.student.pk, "pair": rec.pair.index,
        "homework": rec.target_homework.title if rec.target_homework else None,
        "action": rec.action, "problem": rec.problem,
        "source": rec.source_values, "target": rec.target_values, "after": rec.values,
    }


def _preview(plan: engine.Plan) -> dict:
    return {
        "summary": plan.summary(),
        "fingerprint": plan.fingerprint(),
        "source_lessons": [_lesson(l) for l in plan.source_lessons],
        "target_lessons": [_lesson(l) for l in plan.target_lessons],
        "pairs": [{
            "index": p.index, "source": p.source_id, "target": p.target_id, "valid": p.valid, "problem": p.problem,
            "homework_pairs": len(p.homework_pairs), "homework_problem": p.homework_problem,
        } for p in plan.pairs],
        "students": plan.students,
        "records": [_record(r) for r in plan.records],
    }


def _name(user) -> str | None:
    return (user.get_full_name() or user.username) if user else None


def _operation(op: BulkCopyOperation, *, items: bool = False) -> dict:
    data = {
        "id": op.pk, "operation_id": str(op.operation_id), "status": op.status, "status_label": op.get_status_display(),
        "source": {"group": op.source_group_name, "subject": op.source_subject_name, "start": op.source_start, "end": op.source_end},
        "target": {"group": op.target_group_name, "subject": op.target_subject_name, "start": op.target_start, "end": op.target_end},
        "categories": op.categories, "copied": op.copied_count, "overwritten": op.overwritten_count,
        "skipped": op.skipped_count, "skipped_details": op.skipped_details, "error": op.error,
        "created_by": _name(op.created_by), "created_at": op.created_at, "finished_at": op.finished_at,
        "reverted_by": _name(op.reverted_by), "reverted_at": op.reverted_at, "revert_details": op.revert_details,
        "can_undo": op.status == BulkCopyOperation.Status.APPLIED,
    }
    if items:
        data["items"] = [{
            "id": i.pk, "kind": i.kind, "student": i.student_id,
            "student_name": f"{i.student.last_name} {i.student.first_name}".strip(),
            "target_lesson": _lesson(i.target_lesson), "action": i.action, "before": i.before, "after": i.after,
            "undo_result": i.undo_result,
        } for i in op.items.select_related("student", "target_lesson__teacher__user")]
    return data


def _error(exc: engine.CopyError) -> Response:
    return Response({"detail": exc.message, "code": exc.code}, status=ERROR_STATUS.get(exc.code, 400))


@extend_schema(tags=["Bulk copy"])
class BulkCopyViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, CanBulkCopy]

    def get_queryset(self):
        qs = BulkCopyOperation.objects.select_related("created_by", "reverted_by")
        if not access.is_unrestricted(self.request.user):
            qs = qs.filter(created_by=self.request.user)  # staff see their own operations only
        return qs

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([_operation(op) for op in page])

    def retrieve(self, request, pk=None):
        return Response(_operation(get_object_or_404(self.get_queryset(), pk=pk), items=True))

    @action(detail=False, methods=["get"])
    def options(self, request):
        groups = Group.objects.all() if access.is_unrestricted(request.user) else matrix_access.visible_groups(request.user)
        data = {"groups": [{"id": g.pk, "name": g.name, "status": g.status} for g in groups.order_by("name")],
                "subjects": []}
        group_id = request.query_params.get("group")
        if group_id:
            if not group_id.isdigit():
                raise ValidationError({"group": "Ожидается число."})
            group = get_object_or_404(groups, pk=group_id)
            ids = set(Lesson.objects.filter(group=group, subject__isnull=False).values_list("subject_id", flat=True))
            if group.course_id:
                ids |= set(group.course.subjects.values_list("pk", flat=True))
            data["subjects"] = [{"id": s.pk, "name": s.name} for s in Subject.objects.filter(pk__in=ids).order_by("name")]
        return Response(data)

    @action(detail=False, methods=["post"])
    def preview(self, request):
        serializer = RequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(_preview(engine.plan(serializer.to_request(), request.user)))
        except engine.CopyError as exc:
            return _error(exc)

    def create(self, request):
        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        try:
            op, replayed = operations.start(serializer.to_request(), user=request.user, fingerprint=d["fingerprint"],
                                            operation_id=d["operation_id"], confirm_overwrite=d["confirm_overwrite"])
        except engine.CopyError as exc:
            return _error(exc)
        code = status.HTTP_200_OK if replayed else (
            status.HTTP_202_ACCEPTED if op.status == BulkCopyOperation.Status.QUEUED else status.HTTP_201_CREATED)
        return Response({**_operation(op, items=op.status == BulkCopyOperation.Status.APPLIED), "replayed": replayed},
                        status=code)

    @action(detail=True, methods=["post"])
    def undo(self, request, pk=None):
        op = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            op = engine.undo(op, user=request.user)
        except engine.CopyError as exc:
            return _error(exc)
        return Response(_operation(op, items=True))


__all__ = ["BulkCopyViewSet", "BulkCopyItem"]
