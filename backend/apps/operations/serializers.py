"""Сериализаторы операционного модуля. О людях — только имя, роль и отдел:
контакты, зарплаты и прочие персональные данные здесь не отдаются."""
from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from apps.users.models import User

from . import kpi_registry
from .departments import Department, department_of
from .models import (
    EmployeeReport,
    IssueEvent,
    KPITarget,
    Notification,
    OperationalIssue,
    OperationsSettings,
    Recurrence,
    ReportKind,
    Task,
    TaskAttachment,
    TaskChecklistItem,
    TaskComment,
    TaskHistory,
    TaskRecurrence,
    TaskReview,
    TaskStatus,
)


def person(user) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.pk,
        "full_name": user.get_full_name() or user.username,
        "role": user.role,
        "role_label": user.get_role_display(),
        "department": department_of(user),
    }


class ActiveUserField(serializers.PrimaryKeyRelatedField):
    default_error_messages = {"does_not_exist": "Сотрудник не найден или неактивен."}

    def get_queryset(self):
        return User.objects.filter(is_active=True)


# --- Задачи ------------------------------------------------------------------

class ChecklistItemSerializer(serializers.ModelSerializer):
    done_by = serializers.SerializerMethodField()

    class Meta:
        model = TaskChecklistItem
        fields = ["id", "text", "position", "is_done", "done_by", "done_at"]

    def get_done_by(self, obj):
        return person(obj.done_by)


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = ["id", "author", "text", "created_at"]

    def get_author(self, obj):
        return person(obj.author)


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = TaskAttachment
        fields = ["id", "original_name", "content_type", "size", "uploaded_by", "created_at", "download_url"]

    def get_uploaded_by(self, obj):
        return person(obj.uploaded_by)

    def get_download_url(self, obj):
        # Только через API (проверка прав) — у закрытого файла нет публичной ссылки.
        return f"/api/v1/tasks/{obj.task_id}/attachments/{obj.pk}/download/"


class HistorySerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = TaskHistory
        fields = ["id", "actor", "action", "action_label", "from_status", "to_status", "changes", "comment",
                  "created_at"]

    def get_actor(self, obj):
        return person(obj.actor)


class ReviewSerializer(serializers.ModelSerializer):
    reviewer = serializers.SerializerMethodField()

    class Meta:
        model = TaskReview
        fields = ["id", "reviewer", "decision", "comment", "created_at"]

    def get_reviewer(self, obj):
        return person(obj.reviewer)


class TaskListSerializer(serializers.ModelSerializer):
    assignee = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    stored_status = serializers.CharField(source="status", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    department_label = serializers.CharField(source="get_department_display", read_only=True)
    checklist_total = serializers.IntegerField(read_only=True, default=0)
    checklist_done = serializers.IntegerField(read_only=True, default=0)
    is_recurring = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ["id", "title", "department", "department_label", "assignee", "created_by", "priority",
                  "priority_label", "category", "category_label", "status", "stored_status", "status_label",
                  "start_date", "deadline", "requires_approval", "occurrence_date", "is_recurring",
                  "checklist_total", "checklist_done", "completed_at", "created_at", "updated_at"]

    def get_assignee(self, obj):
        return person(obj.assignee)

    def get_created_by(self, obj):
        return person(obj.created_by)

    def get_status(self, obj):
        return obj.effective_status(self.context.get("now"))

    def get_status_label(self, obj):
        return TaskStatus(obj.effective_status(self.context.get("now"))).label

    def get_is_recurring(self, obj):
        return obj.recurrence_id is not None


class TaskDetailSerializer(TaskListSerializer):
    reviewer = serializers.SerializerMethodField()
    checklist = ChecklistItemSerializer(many=True, read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    history = HistorySerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    actions = serializers.SerializerMethodField()

    class Meta(TaskListSerializer.Meta):
        fields = TaskListSerializer.Meta.fields + ["description", "reviewer", "checklist", "comments",
                                                   "attachments", "history", "reviews", "actions",
                                                   "started_at", "submitted_at", "cancelled_at"]

    def get_reviewer(self, obj):
        return person(obj.reviewer or obj.created_by)

    def get_actions(self, obj):
        from .services.tasks import available_actions

        request = self.context.get("request")
        return available_actions(request.user, obj) if request else []


class TaskWriteSerializer(serializers.ModelSerializer):
    assignee = ActiveUserField(allow_null=True, required=False)
    reviewer = ActiveUserField(allow_null=True, required=False)
    department = serializers.ChoiceField(choices=Department.choices, required=False)
    checklist = serializers.ListField(child=serializers.CharField(max_length=255), required=False, write_only=True)

    class Meta:
        model = Task
        fields = ["title", "description", "department", "assignee", "reviewer", "priority", "category",
                  "start_date", "deadline", "requires_approval", "checklist"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Укажите название задачи.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        deadline = attrs.get("deadline", getattr(self.instance, "deadline", None))
        if start and deadline and timezone.localtime(deadline).date() < start:
            raise serializers.ValidationError({"deadline": "Дедлайн раньше даты начала."})
        return attrs


class RecurrenceSerializer(serializers.ModelSerializer):
    assignee = ActiveUserField()
    assignee_info = serializers.SerializerMethodField()
    frequency_label = serializers.CharField(source="get_frequency_display", read_only=True)
    occurrences_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TaskRecurrence
        fields = ["id", "title", "description", "department", "assignee", "assignee_info", "priority", "category",
                  "requires_approval", "checklist", "frequency", "frequency_label", "weekdays", "month_day",
                  "due_time", "starts_on", "ends_on", "is_active", "last_generated_on", "occurrences_count",
                  "created_at"]
        read_only_fields = ["department", "last_generated_on", "created_at"]

    def get_assignee_info(self, obj):
        return person(obj.assignee)

    def validate(self, attrs):
        frequency = attrs.get("frequency", getattr(self.instance, "frequency", None))
        weekdays = attrs.get("weekdays", getattr(self.instance, "weekdays", []))
        month_day = attrs.get("month_day", getattr(self.instance, "month_day", None))
        if frequency == Recurrence.WEEKLY and (not weekdays or any(d not in range(7) for d in weekdays)):
            raise serializers.ValidationError({"weekdays": "Укажите дни недели (0 — понедельник … 6 — воскресенье)."})
        if frequency == Recurrence.MONTHLY and not month_day:
            raise serializers.ValidationError({"month_day": "Укажите число месяца."})
        starts, ends = attrs.get("starts_on", getattr(self.instance, "starts_on", None)), attrs.get("ends_on")
        if starts and ends and ends < starts:
            raise serializers.ValidationError({"ends_on": "Окончание раньше начала."})
        checklist = attrs.get("checklist")
        if checklist is not None and (not isinstance(checklist, list) or not all(isinstance(i, str) for i in checklist)):
            raise serializers.ValidationError({"checklist": "Чек-лист — список строк."})
        return attrs


# --- Отчёты ------------------------------------------------------------------

class EmployeeReportSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    department_label = serializers.CharField(source="get_department_display", read_only=True)

    class Meta:
        model = EmployeeReport
        fields = ["id", "author", "department", "department_label", "kind", "kind_label", "period_start",
                  "period_end", "done", "plans", "problems", "metrics", "status", "status_label", "submitted_at",
                  "reviewed_by", "reviewed_at", "review_comment", "created_at", "updated_at"]
        read_only_fields = ["department", "period_end", "status", "submitted_at", "reviewed_at", "review_comment",
                            "created_at", "updated_at"]

    def get_author(self, obj):
        return person(obj.author)

    def get_reviewed_by(self, obj):
        return person(obj.reviewed_by)

    def validate_kind(self, value):
        if self.instance is not None and value != self.instance.kind:
            raise serializers.ValidationError("Вид отчёта не меняется.")
        return value

    def validate(self, attrs):
        from .services.reports import metric_schema, normalize_period

        kind = attrs.get("kind", getattr(self.instance, "kind", ReportKind.DAILY))
        start = attrs.get("period_start", getattr(self.instance, "period_start", None)) or timezone.localdate()
        attrs["period_start"], attrs["period_end"] = normalize_period(kind, start)
        if attrs["period_start"] > timezone.localdate():
            raise serializers.ValidationError({"period_start": "Отчёт за будущий период сдать нельзя."})
        if "metrics" in attrs:
            role = (self.instance.author if self.instance else self.context["request"].user).role
            schema = {field["key"]: field for field in metric_schema(role)}
            cleaned = {}
            for key, value in (attrs["metrics"] or {}).items():
                if key not in schema:
                    raise serializers.ValidationError({"metrics": f"Неизвестный показатель «{key}»."})
                if value in (None, ""):
                    continue
                if schema[key]["type"] == "bool":
                    cleaned[key] = bool(value)
                    continue
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    raise serializers.ValidationError({"metrics": f"«{schema[key]['label']}» — число."})
                if number < 0:
                    raise serializers.ValidationError({"metrics": f"«{schema[key]['label']}» не может быть меньше 0."})
                cleaned[key] = int(number) if schema[key]["type"] == "int" else round(number, 2)
            attrs["metrics"] = cleaned
        return attrs


# --- KPI ---------------------------------------------------------------------

class KPITargetSerializer(serializers.ModelSerializer):
    employee = ActiveUserField(allow_null=True, required=False)
    employee_info = serializers.SerializerMethodField()
    metric_label = serializers.SerializerMethodField()
    department_label = serializers.CharField(source="get_department_display", read_only=True)
    period_label = serializers.CharField(source="get_period_display", read_only=True)

    class Meta:
        model = KPITarget
        fields = ["id", "metric", "metric_label", "department", "department_label", "employee", "employee_info",
                  "period", "period_label", "target_value", "valid_from", "valid_to", "note", "created_at"]
        read_only_fields = ["created_at"]

    def get_employee_info(self, obj):
        return person(obj.employee)

    def get_metric_label(self, obj):
        metric = kpi_registry.METRICS.get(obj.metric)
        return metric.label if metric else obj.metric

    def validate(self, attrs):
        metric_key = attrs.get("metric", getattr(self.instance, "metric", None))
        metric = kpi_registry.METRICS.get(metric_key)
        if metric is None:
            raise serializers.ValidationError({"metric": "Неизвестный показатель."})
        department = attrs.get("department", getattr(self.instance, "department", None))
        employee = attrs["employee"] if "employee" in attrs else getattr(self.instance, "employee", None)
        if employee is not None:
            attrs["department"] = department = department_of(employee)
        if metric.departments and department not in metric.departments:
            raise serializers.ValidationError({"metric": "Этот показатель не относится к выбранному отделу."})
        if employee is None and not metric.department_level:
            raise serializers.ValidationError({"employee": "Этот показатель задаётся только сотруднику."})
        if employee is not None and not metric.employee_level:
            raise serializers.ValidationError({"employee": "Этот показатель задаётся только отделу."})
        start = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        end = attrs.get("valid_to", getattr(self.instance, "valid_to", None))
        if start and end and end < start:
            raise serializers.ValidationError({"valid_to": "Окончание раньше начала."})
        return attrs


# --- Проблемы ----------------------------------------------------------------

class IssueEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = IssueEvent
        fields = ["id", "actor", "action", "action_label", "from_status", "to_status", "comment", "created_at"]

    def get_actor(self, obj):
        return person(obj.actor)


class IssueSerializer(serializers.ModelSerializer):
    responsible = serializers.SerializerMethodField()
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    department_label = serializers.CharField(source="get_department_display", read_only=True)

    class Meta:
        model = OperationalIssue
        fields = ["id", "kind", "kind_label", "title", "description", "priority", "priority_label", "status",
                  "status_label", "department", "department_label", "responsible", "object_type", "object_id", "link",
                  "detected_at", "last_seen_at", "times_detected", "reopen_count", "auto_detected", "resolved_at"]

    def get_responsible(self, obj):
        return person(obj.responsible)


class IssueDetailSerializer(IssueSerializer):
    events = IssueEventSerializer(many=True, read_only=True)
    resolved_by = serializers.SerializerMethodField()

    class Meta(IssueSerializer.Meta):
        fields = IssueSerializer.Meta.fields + ["events", "resolved_by", "payload"]

    def get_resolved_by(self, obj):
        return person(obj.resolved_by)


class IssueCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    department = serializers.ChoiceField(choices=Department.choices)
    priority = serializers.ChoiceField(choices=[p for p in ("low", "medium", "high", "critical")], default="medium")
    responsible = ActiveUserField(allow_null=True, required=False)


# --- Уведомления и настройки -------------------------------------------------

class NotificationSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "kind", "kind_label", "title", "message", "link", "is_read", "read_at", "created_at"]


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationsSettings
        fields = ["required_reports", "daily_report_due", "deadline_reminder_hours",
                  "problem_group_attendance", "detect_staff_absence", "notify_telegram",
                  "operations_director_sees_marketing_budget", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate_required_reports(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Ожидается объект «роль → список отчётов».")
        roles = set(User.Role.values)
        for role, kinds in value.items():
            if role not in roles:
                raise serializers.ValidationError(f"Неизвестная роль «{role}».")
            if not isinstance(kinds, list) or not set(kinds) <= set(ReportKind.values):
                raise serializers.ValidationError(f"Неверный список отчётов для роли «{role}».")
        return {role: sorted(set(kinds)) for role, kinds in value.items() if kinds}
