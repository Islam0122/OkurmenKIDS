"""API задач, отчётов и уведомлений каждого сотрудника:

    /api/v1/tasks/                 список (scope — permissions.task_scope), создание
    /api/v1/tasks/my/              «Мои задачи»: сегодня, скоро, в работе, на проверке, выполнено, просрочено
    /api/v1/tasks/{id}/            карточка, изменение (автор / руководитель)
    /api/v1/tasks/{id}/{action}/   start, submit, approve, reject, cancel, reopen
    /api/v1/tasks/{id}/checklist/, comments/, attachments/
    /api/v1/tasks/recurrences/     шаблоны повторяющихся задач
    /api/v1/tasks/meta/            справочники и кому можно ставить задачи
    /api/v1/work-reports/          свои отчёты (+ отдела для руководителя), сдача и проверка
    /api/v1/notifications/         свои уведомления

Чужие записи — 404: queryset всегда ограничен правами пользователя.
"""
from __future__ import annotations

import datetime as dt

from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.models import User

from .departments import Department, choices as department_choices, department_of
from .models import (
    CLOSED_STATUSES,
    EmployeeReport,
    Notification,
    OPEN_STATUSES,
    Priority,
    Recurrence,
    ReportKind,
    Task,
    TaskCategory,
    TaskRecurrence,
    TaskStatus,
)
from .permissions import IsActiveEmployee, can_assign_to, can_oversee, manageable_roles, report_scope, task_scope
from .serializers import (
    AttachmentSerializer,
    ChecklistItemSerializer,
    CommentSerializer,
    EmployeeReportSerializer,
    NotificationSerializer,
    RecurrenceSerializer,
    TaskDetailSerializer,
    TaskListSerializer,
    TaskWriteSerializer,
    person,
)
from .services import reports as report_service
from .services import tasks as workflow

PERMISSIONS = [IsAuthenticated, IsActiveEmployee]


class OpsPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


def _choices(enum, values=None) -> list[dict]:
    return [{"value": v, "label": label} for v, label in enum.choices if values is None or v in values]


def parse_date(value):
    try:
        return dt.date.fromisoformat(value) if value else None
    except ValueError:
        raise ValidationError({"detail": "Дата указывается в формате ГГГГ-ММ-ДД."})


def visible_tasks(user):
    scope = task_scope(user)
    return Task.objects.none() if scope is None else Task.objects.filter(scope)


def filter_tasks(qs, params, user, now=None):
    now = now or timezone.now()
    value = params.get("status")
    overdue_q = Q(status__in=OPEN_STATUSES, deadline__lt=now)
    if value == TaskStatus.OVERDUE:
        qs = qs.filter(overdue_q)
    elif value == "open":
        qs = qs.exclude(status__in=CLOSED_STATUSES)
    elif value in OPEN_STATUSES:
        qs = qs.filter(status=value).exclude(overdue_q)
    elif value in TaskStatus.values:
        qs = qs.filter(status=value)
    if params.get("department") in Department.values:
        qs = qs.filter(department=params["department"])
    if params.get("priority") in Priority.values:
        qs = qs.filter(priority=params["priority"])
    if params.get("category") in TaskCategory.values:
        qs = qs.filter(category=params["category"])
    if (params.get("assignee") or "").isdigit():
        qs = qs.filter(assignee_id=int(params["assignee"]))
    if params.get("assignee") == "none":
        qs = qs.filter(assignee__isnull=True)
    if (params.get("created_by") or "").isdigit():
        qs = qs.filter(created_by_id=int(params["created_by"]))
    if params.get("role") in User.Role.values:
        qs = qs.filter(assignee__role=params["role"])
    if params.get("mine") == "1":
        qs = qs.filter(assignee=user)
    if params.get("created") == "1":
        qs = qs.filter(created_by=user)
    if params.get("to_review") == "1":
        qs = qs.filter(status=TaskStatus.REVIEW).filter(Q(reviewer=user) | Q(reviewer__isnull=True, created_by=user))
    if params.get("recurring") == "1":
        qs = qs.filter(recurrence__isnull=False)
    if (params.get("recurrence") or "").isdigit():
        qs = qs.filter(recurrence_id=int(params["recurrence"]))
    if (d := parse_date(params.get("deadline_from"))):
        qs = qs.filter(deadline__date__gte=d)
    if (d := parse_date(params.get("deadline_to"))):
        qs = qs.filter(deadline__date__lte=d)
    return qs


def with_counts(qs):
    return qs.select_related("assignee", "created_by", "reviewer").annotate(
        checklist_total=Count("checklist", distinct=True),
        checklist_done=Count("checklist", filter=Q(checklist__is_done=True), distinct=True),
    )


def ordered(qs):
    return qs.annotate(
        closed_rank=Case(When(status__in=CLOSED_STATUSES, then=Value(1)), default=Value(0),
                         output_field=IntegerField()),
        priority_rank=Case(*(When(priority=p, then=Value(i)) for i, p in enumerate(
            (Priority.CRITICAL, Priority.HIGH, Priority.MEDIUM, Priority.LOW))), output_field=IntegerField()),
    ).order_by("closed_rank", F("deadline").asc(nulls_last=True), "priority_rank", "-created_at")


@extend_schema(tags=["Tasks"])
class TaskViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = PERMISSIONS
    pagination_class = OpsPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "description"]
    ordering_fields = ["deadline", "created_at", "updated_at", "priority", "title"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = visible_tasks(self.request.user)
        if self.action == "list":
            return with_counts(ordered(filter_tasks(qs, self.request.query_params, self.request.user)))
        return with_counts(qs).prefetch_related("checklist__done_by", "comments__author", "attachments__uploaded_by",
                                                "history__actor", "reviews__reviewer")

    def get_serializer_class(self):
        if self.action in ("create", "partial_update", "update"):
            return TaskWriteSerializer
        return TaskListSerializer if self.action == "list" else TaskDetailSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "now": timezone.now()}

    def _detail(self, task, code=status.HTTP_200_OK):
        task = self.get_queryset().get(pk=task.pk)
        return Response(TaskDetailSerializer(task, context=self.get_serializer_context()).data, status=code)

    def create(self, request, *args, **kwargs):
        serializer = TaskWriteSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        checklist = data.pop("checklist", [])
        task = workflow.create_task(request.user, data, checklist)
        return self._detail(task, status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        task = self.get_object()
        serializer = TaskWriteSerializer(task, data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("checklist", None)
        task = workflow.update_task(request.user, task, data)
        return self._detail(task)

    def _run(self, request, name):
        task = self.get_object()
        if name == "start":
            task = workflow.start(request.user, task)
        else:
            task = workflow.ACTIONS[name](request.user, task, str(request.data.get("comment") or ""))
        return self._detail(task)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._run(request, "start")

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._run(request, "submit")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._run(request, "approve")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._run(request, "reject")

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._run(request, "cancel")

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._run(request, "reopen")

    @action(detail=True, methods=["post"], url_path="checklist")
    def checklist_add(self, request, pk=None):
        task = self.get_object()
        item = workflow.add_checklist_item(request.user, task, str(request.data.get("text") or ""))
        return Response(ChecklistItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path=r"checklist/(?P<item_id>\d+)")
    def checklist_toggle(self, request, pk=None, item_id=None):
        task = self.get_object()
        item = get_object_or_404(task.checklist, pk=item_id)
        item = workflow.toggle_checklist_item(request.user, task, item, bool(request.data.get("is_done")))
        return Response(ChecklistItemSerializer(item).data)

    @action(detail=True, methods=["post"])
    def comments(self, request, pk=None):
        task = self.get_object()
        comment = workflow.add_comment(request.user, task, str(request.data.get("text") or ""))
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def attachments(self, request, pk=None):
        task = self.get_object()
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Выберите файл."})
        attachment = workflow.add_attachment(request.user, task, upload)
        return Response(AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"attachments/(?P<attachment_id>\d+)")
    def attachment_delete(self, request, pk=None, attachment_id=None):
        task = self.get_object()
        attachment = get_object_or_404(task.attachments, pk=attachment_id)
        workflow.delete_attachment(request.user, task, attachment)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path=r"attachments/(?P<attachment_id>\d+)/download")
    def attachment_download(self, request, pk=None, attachment_id=None):
        # Права на вложение = права на задачу: get_object() уже ограничен scope.
        task = self.get_object()
        attachment = get_object_or_404(task.attachments, pk=attachment_id)
        response = FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.original_name,
                                content_type=attachment.content_type or "application/octet-stream")
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=False, methods=["get"])
    def my(self, request):
        """«Мои задачи» — разделы страницы одним запросом."""
        user, now = request.user, timezone.now()
        today = timezone.localdate()
        qs = with_counts(Task.objects.filter(Q(assignee=user) | Q(
            assignee__isnull=True, department=department_of(user)), status__in=STORED_OPEN_OR_REVIEW))
        context = self.get_serializer_context()

        def data(items):
            return TaskListSerializer(items, many=True, context=context).data

        open_items = list(ordered(qs))
        tomorrow = today + dt.timedelta(days=1)
        sections = {
            "overdue": [t for t in open_items if t.is_overdue(now)],
            "today": [t for t in open_items if not t.is_overdue(now) and t.status != TaskStatus.REVIEW
                      and t.deadline and timezone.localtime(t.deadline).date() == today],
            "upcoming": [t for t in open_items if t.status != TaskStatus.REVIEW and not t.is_overdue(now)
                         and (t.deadline is None or timezone.localtime(t.deadline).date() >= tomorrow)
                         and t.status != TaskStatus.IN_PROGRESS],
            "in_progress": [t for t in open_items if t.status == TaskStatus.IN_PROGRESS and not t.is_overdue(now)],
            "review": [t for t in open_items if t.status == TaskStatus.REVIEW],
        }
        completed = with_counts(Task.objects.filter(assignee=user, status=TaskStatus.COMPLETED)).order_by(
            "-completed_at")[:30]
        to_review = with_counts(Task.objects.filter(status=TaskStatus.REVIEW).filter(
            Q(reviewer=user) | Q(reviewer__isnull=True, created_by=user)).exclude(assignee=user))
        return Response({
            **{key: data(items) for key, items in sections.items()},
            "completed": data(completed),
            "to_review": data(ordered(to_review)),
            "counts": {**{key: len(items) for key, items in sections.items()}, "to_review": to_review.count()},
        })

    @action(detail=False, methods=["get"])
    def meta(self, request):
        user = request.user
        roles = manageable_roles(user)
        people = User.objects.filter(is_active=True).order_by("first_name", "last_name")
        if roles is not None:
            people = people.filter(Q(role__in=roles) | Q(pk=user.pk))
        return Response({
            "statuses": _choices(TaskStatus),
            "priorities": _choices(Priority),
            "categories": _choices(TaskCategory),
            "departments": department_choices(),
            "recurrence": _choices(Recurrence),
            "assignees": [person(u) for u in people],
            "can_assign_others": roles is None or bool(roles),
            "can_oversee": can_oversee(user),
            "me": person(user),
        })


STORED_OPEN_OR_REVIEW = (*OPEN_STATUSES, TaskStatus.REVIEW)


@extend_schema(tags=["Tasks"])
class RecurrenceViewSet(viewsets.ModelViewSet):
    """Шаблоны повторяющихся задач. Видит и меняет автор, руководитель отдела
    исполнителя или надзор; исполнитель — только читает свои."""

    serializer_class = RecurrenceSerializer
    permission_classes = PERMISSIONS
    pagination_class = OpsPagination
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        user = self.request.user
        qs = TaskRecurrence.objects.select_related("assignee").annotate(occurrences_count=Count("occurrences"))
        if can_oversee(user):
            return qs
        roles = manageable_roles(user) or []
        return qs.filter(Q(created_by=user) | Q(assignee=user) | Q(assignee__role__in=roles))

    def _check_manage(self, rule=None, assignee=None):
        user = self.request.user
        if assignee is not None and not can_assign_to(user, assignee):
            raise ValidationError({"assignee": "Этому сотруднику вы не можете ставить задачи."})
        if rule is not None and not (can_oversee(user) or rule.created_by_id == user.pk
                                     or (rule.assignee.role in (manageable_roles(user) or []))):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Шаблон меняет его автор или руководитель.")

    def perform_create(self, serializer):
        assignee = serializer.validated_data["assignee"]
        self._check_manage(assignee=assignee)
        rule = serializer.save(created_by=self.request.user, department=department_of(assignee))
        from .services.recurrence import generate_for

        generate_for(rule, timezone.localdate())

    def perform_update(self, serializer):
        self._check_manage(rule=serializer.instance, assignee=serializer.validated_data.get("assignee"))
        assignee = serializer.validated_data.get("assignee", serializer.instance.assignee)
        serializer.save(department=department_of(assignee))

    def perform_destroy(self, instance):
        self._check_manage(rule=instance)
        # Шаблон не удаляется вместе с историей: повторения остаются задачами.
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


# --- Отчёты сотрудников ------------------------------------------------------

@extend_schema(tags=["Work reports"])
class WorkReportViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = EmployeeReportSerializer
    permission_classes = PERMISSIONS
    pagination_class = OpsPagination
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        scope = report_scope(self.request.user)
        qs = EmployeeReport.objects.none() if scope is None else EmployeeReport.objects.filter(scope)
        p = self.request.query_params
        if p.get("kind") in ReportKind.values:
            qs = qs.filter(kind=p["kind"])
        if p.get("status") in EmployeeReport.Status.values:
            qs = qs.filter(status=p["status"])
        if p.get("department") in Department.values:
            qs = qs.filter(department=p["department"])
        if (p.get("author") or "").isdigit():
            qs = qs.filter(author_id=int(p["author"]))
        if p.get("mine") == "1":
            qs = qs.filter(author=self.request.user)
        if (d := parse_date(p.get("date_from"))):
            qs = qs.filter(period_start__gte=d)
        if (d := parse_date(p.get("date_to"))):
            qs = qs.filter(period_start__lte=d)
        return qs.select_related("author", "reviewed_by")

    def perform_create(self, serializer):
        serializer.instance = report_service.save_report(self.request.user, dict(serializer.validated_data))

    def perform_update(self, serializer):
        serializer.instance = report_service.save_report(self.request.user, dict(serializer.validated_data),
                                                         serializer.instance)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        report = report_service.submit_report(request.user, self.get_object())
        return Response(self.get_serializer(report).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        accept = request.data.get("decision") == "accept"
        if request.data.get("decision") not in ("accept", "return"):
            raise ValidationError({"decision": "accept или return."})
        report = report_service.review_report(request.user, self.get_object(), accept,
                                              str(request.data.get("comment") or ""))
        return Response(self.get_serializer(report).data)

    @action(detail=False, methods=["get"])
    def meta(self, request):
        """Схема показателей своей роли и обязательные отчёты (что и до какого
        срока сдать за последние 14 дней)."""
        today = timezone.localdate()
        items = report_service.obligations(today - dt.timedelta(days=13), today, users=[request.user])
        return Response({
            "kinds": _choices(ReportKind),
            "statuses": _choices(EmployeeReport.Status),
            "metrics": report_service.metric_schema(request.user.role),
            "obligations": [{"kind": o.kind, "period_start": o.period_start, "period_end": o.period_end,
                             "due": o.due, "status": o.status, "report_id": o.report_id} for o in items],
            "today": today,
        })


# --- Уведомления -------------------------------------------------------------

@extend_schema(tags=["Notifications"])
class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = PERMISSIONS
    pagination_class = OpsPagination

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        if self.request.query_params.get("unread") == "1":
            qs = qs.filter(is_read=False)
        return qs

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(is_read=False).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = get_object_or_404(self.get_queryset(), pk=pk)
        if not notification.is_read:
            notification.is_read, notification.read_at = True, timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({"updated": updated})

