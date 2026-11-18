"""API — bulk copy of trainer scores between subjects (services.score_copy).

    GET  /api/v1/scholarship-score-copies/options/            groups, periods
    GET  /api/v1/scholarship-score-copies/options/?group=<id>  + that group's subjects
    POST /api/v1/scholarship-score-copies/preview/            dry run: summary, rows, fingerprint
    POST /api/v1/scholarship-score-copies/                    apply (fingerprint + operation_id)
    GET  /api/v1/scholarship-score-copies/                    audit history
    GET  /api/v1/scholarship-score-copies/<id>/               one operation with its rows
    POST /api/v1/scholarship-score-copies/<id>/undo/          safe undo

Admin, or staff with `scholarships.copy_scores` (permissions.can_copy_scores).
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.academy.models import Group
from apps.users.models import Subject, Teacher

from .models import ScholarshipPeriod, ScoreCopyItem, ScoreCopyOperation
from .permissions import CanCopyScores
from .services import score_copy as svc

TAGS = ["Scholarships — score copy"]

ERROR_STATUS = {
    "invalid": status.HTTP_400_BAD_REQUEST,
    "conflict": status.HTTP_409_CONFLICT,
    "confirmation_required": status.HTTP_428_PRECONDITION_REQUIRED,
}


class CopyRequestSerializer(serializers.Serializer):
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all())
    source_subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    target_subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    source_period = serializers.PrimaryKeyRelatedField(queryset=ScholarshipPeriod.objects.all())
    target_period = serializers.PrimaryKeyRelatedField(queryset=ScholarshipPeriod.objects.all())
    mode = serializers.ChoiceField(choices=["all", "selected"], default="all")
    student_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list,
                                        max_length=1000)
    conflict = serializers.ChoiceField(choices=["preserve", "overwrite"], default="preserve")
    copy_comment = serializers.BooleanField(default=False)
    source_teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), required=False, allow_null=True)
    target_teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), required=False, allow_null=True)

    def to_request(self) -> svc.CopyRequest:
        data = self.validated_data
        ids = None
        if data["mode"] == "selected":
            ids = tuple(sorted(set(data["student_ids"])))
        return svc.CopyRequest(
            group=data["group"], source_subject=data["source_subject"], target_subject=data["target_subject"],
            source_period=data["source_period"], target_period=data["target_period"], student_ids=ids,
            overwrite=data["conflict"] == "overwrite", copy_comment=data["copy_comment"],
            source_teacher=data.get("source_teacher"), target_teacher=data.get("target_teacher"),
        )


class ApplySerializer(CopyRequestSerializer):
    fingerprint = serializers.CharField(max_length=64)
    operation_id = serializers.UUIDField()
    confirm_overwrite = serializers.BooleanField(default=False)


def _teacher(t) -> dict | None:
    return {"id": t.pk, "name": str(t)} if t else None


def _period(p) -> dict | None:
    if p is None:
        return None
    return {"id": p.pk, "title": p.title, "period_start": p.period_start, "period_end": p.period_end,
            "status": p.status, "is_draft": p.is_draft}


def _row(row: svc.Row) -> dict:
    student = row.student
    return {
        "student_id": student.pk,
        "student_name": f"{student.last_name} {student.first_name}".strip(),
        "action": row.action,
        "reason": svc.REASONS[row.action],
        "source": svc.feedback_values(row.source),
        "source_teacher": _teacher(row.source.teacher) if row.source else None,
        "target": svc.feedback_values(row.target),
        "target_teacher": _teacher(row.target_teacher),
        "target_teachers": [_teacher(t) for t in row.target_teachers],
        "after": {**row.values, "score": svc.values_score(row.values)} if row.values else None,
    }


def _plan_payload(plan: svc.Plan) -> dict:
    return {
        "summary": plan.summary(),
        "fingerprint": plan.fingerprint(),
        "rows": [_row(row) for row in plan.rows],
        "source_teachers": [_teacher(t) for t in plan.source_teachers],
        "target_teachers": [_teacher(t) for t in plan.target_teachers],
        "target_period_is_draft": plan.request.target_period.is_draft,
    }


def _operation(op: ScoreCopyOperation, *, items: bool = False) -> dict:
    data = {
        "id": op.pk,
        "operation_id": str(op.operation_id),
        "status": op.status,
        "status_label": op.get_status_display(),
        "group": {"id": op.group_id, "name": op.group_name},
        "source_subject": {"id": op.source_subject_id, "name": op.source_subject_name},
        "target_subject": {"id": op.target_subject_id, "name": op.target_subject_name},
        "source_period": _period(op.source_period),
        "target_period": _period(op.target_period),
        "options": op.options,
        "copied": op.copied_count,
        "overwritten": op.overwritten_count,
        "skipped": op.skipped_count,
        "skipped_details": op.skipped_details,
        "created_by": op.created_by.get_full_name() or op.created_by.username,
        "created_at": op.created_at,
        "reverted_by": (op.reverted_by.get_full_name() or op.reverted_by.username) if op.reverted_by else None,
        "reverted_at": op.reverted_at,
        "revert_details": op.revert_details,
        "can_undo": op.status == ScoreCopyOperation.Status.APPLIED and bool(op.target_period and op.target_period.is_draft),
    }
    if items:
        data["items"] = [{
            "id": item.pk,
            "student_id": item.student_id,
            "student_name": f"{item.student.last_name} {item.student.first_name}".strip(),
            "teacher": _teacher(item.teacher),
            "action": item.action,
            "before": item.before,
            "after": item.after,
            "undo_result": item.undo_result,
        } for item in op.items.select_related("student", "teacher__user")]
    return data


def _raise(exc: svc.ScoreCopyError):
    return Response({"detail": exc.message, "code": exc.code}, status=ERROR_STATUS.get(exc.code, 400))


@extend_schema(tags=TAGS)
class ScoreCopyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, CanCopyScores]
    queryset = ScoreCopyOperation.objects.select_related(
        "created_by", "reverted_by", "source_period", "target_period",
    )

    def list(self, request):
        qs = self.get_queryset()
        group = request.query_params.get("group")
        if group and group.isdigit():
            qs = qs.filter(group_id=group)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response([_operation(op) for op in page])

    def retrieve(self, request, pk=None):
        return Response(_operation(get_object_or_404(self.get_queryset(), pk=pk), items=True))

    @action(detail=False, methods=["get"])
    def options(self, request):
        groups = Group.objects.order_by("name")
        data = {
            "groups": [{"id": g.pk, "name": g.name, "status": g.status} for g in groups],
            "periods": [_period(p) for p in ScholarshipPeriod.objects.order_by("-period_start", "-id")],
            "subjects": [],
        }
        group_id = request.query_params.get("group")
        if group_id:
            if not group_id.isdigit():
                raise ValidationError({"group": "Ожидается число."})
            group = get_object_or_404(Group, pk=group_id)
            data["subjects"] = [{"id": s.pk, "name": s.name} for s in svc.subjects_of_group(group)]
        return Response(data)

    @action(detail=False, methods=["post"])
    def preview(self, request):
        serializer = CopyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(_plan_payload(svc.plan(serializer.to_request())))
        except svc.ScoreCopyError as exc:
            return _raise(exc)

    def create(self, request):
        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            operation, replayed = svc.apply(
                serializer.to_request(), user=request.user, fingerprint=data["fingerprint"],
                operation_id=data["operation_id"], confirm_overwrite=data["confirm_overwrite"],
            )
        except svc.ScoreCopyError as exc:
            return _raise(exc)
        payload = {**_operation(operation, items=True), "replayed": replayed}
        return Response(payload, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def undo(self, request, pk=None):
        operation = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            operation = svc.undo(operation, user=request.user)
        except svc.ScoreCopyError as exc:
            return _raise(exc)
        return Response(_operation(operation, items=True))


__all__ = ["ScoreCopyViewSet", "ScoreCopyItem"]
