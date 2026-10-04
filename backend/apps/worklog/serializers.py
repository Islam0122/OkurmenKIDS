from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from apps.academy.models import Group, Lesson, Student
from apps.users.models import Teacher

from . import metrics as metrics_service
from .models import ReportKind, TaskStatus, TeamLeadReport, WorkLogEntry
from .schemas import REPORT_KINDS, clean_report_data, status_label


def _ref(obj, label=None):
    if obj is None:
        return None
    return {"id": obj.pk, "name": label if label is not None else str(obj)}


class WorkLogEntrySerializer(serializers.ModelSerializer):
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False, allow_null=True)
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), required=False, allow_null=True)
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all(), required=False, allow_null=True)
    report = serializers.PrimaryKeyRelatedField(queryset=TeamLeadReport.objects.all(), required=False, allow_null=True)

    class Meta:
        model = WorkLogEntry
        fields = [
            "id", "entry_kind", "date", "time_from", "time_to", "work_type",
            "group", "teacher", "student", "with_whom",
            "title", "goal", "description", "result", "problem", "decision", "next_action",
            "responsible", "deadline", "priority", "status", "comment", "report",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        effective = instance.effective_status()
        data.update({
            "author": _ref(instance.author, instance.author.get_full_name() or instance.author.username),
            "group_detail": _ref(instance.group, instance.group.name if instance.group_id else None),
            "teacher_detail": _ref(instance.teacher),
            "student_detail": _ref(instance.student),
            "work_type_label": instance.get_work_type_display(),
            "priority_label": instance.get_priority_display(),
            "effective_status": effective,
            "effective_status_label": TaskStatus(effective).label,
            "is_overdue": effective == TaskStatus.OVERDUE,
            "summary": summary_sentence(instance),
            "can_edit": self._can_edit(instance),
        })
        return data

    def _can_edit(self, instance) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.pk == instance.author_id)

    def validate(self, attrs):
        """Section 6.13: a journal record answers «что сделал, когда, с кем,
        какой результат, что дальше»; a task has an owner and a deadline."""
        merged = {f: attrs.get(f, getattr(self.instance, f, None)) for f in self.Meta.fields if f not in ("id",)}
        kind = merged.get("entry_kind") or WorkLogEntry.Kind.LOG
        errors = {}
        if merged.get("time_from") and merged.get("time_to") and merged["time_to"] <= merged["time_from"]:
            errors["time_to"] = "Время окончания должно быть позже начала."
        if kind == WorkLogEntry.Kind.TASK:
            for field, message in (
                ("title", "Опишите задачу."),
                ("responsible", "Укажите ответственного."),
                ("deadline", "Укажите срок."),
            ):
                if not merged.get(field):
                    errors[field] = message
        else:
            if not (merged.get("description") or "").strip():
                errors["description"] = "Что сделано? Опишите работу."
            if not any(merged.get(f) for f in ("group", "teacher", "student")) and not (merged.get("with_whom") or "").strip():
                errors["with_whom"] = "С кем работали? Укажите группу, тренера, студента или участников."
            if not (merged.get("result") or "").strip():
                errors["result"] = "Какой результат получен?"
            if not (merged.get("next_action") or "").strip():
                errors["next_action"] = "Что нужно сделать дальше? (если ничего — так и напишите)"
            if (merged.get("next_action") or "").strip() and merged.get("deadline") and not (merged.get("responsible") or "").strip():
                errors["responsible"] = "У следующего действия со сроком должен быть ответственный."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def summary_sentence(entry: WorkLogEntry) -> str:
    """The section 6.13 sentence: when, what, with whom, result, next."""
    who = ", ".join(
        part for part in (
            f"группа {entry.group.name}" if entry.group_id else "",
            f"тренер {entry.teacher}" if entry.teacher_id else "",
            f"студент {entry.student}" if entry.student_id else "",
            entry.with_whom,
        ) if part
    )
    parts = [f"{entry.date:%d.%m.%Y}"]
    if entry.time_from:
        parts[0] += f" {entry.time_from:%H:%M}"
        if entry.time_to:
            parts[0] += f"–{entry.time_to:%H:%M}"
    parts.append(entry.get_work_type_display().lower())
    if who:
        parts.append(who)
    text = ", ".join(parts) + "."
    if entry.description:
        text += f" {entry.description.strip().rstrip('.')}."
    if entry.result:
        text += f" Результат: {entry.result.strip().rstrip('.')}."
    if entry.next_action:
        text += f" Дальше: {entry.next_action.strip().rstrip('.')}"
        if entry.responsible:
            text += f" ({entry.responsible}"
            text += f", до {entry.deadline:%d.%m.%Y})" if entry.deadline else ")"
        text += "."
    return text


class TeamLeadReportSerializer(serializers.ModelSerializer):
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False, allow_null=True)
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), required=False, allow_null=True)
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all(), required=False, allow_null=True)
    lesson = serializers.PrimaryKeyRelatedField(queryset=Lesson.objects.all(), required=False, allow_null=True)

    class Meta:
        model = TeamLeadReport
        fields = [
            "id", "kind", "date", "period_start", "period_end", "group", "teacher", "student", "lesson",
            "data", "metrics", "metrics_calculated_at", "status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "metrics", "metrics_calculated_at", "created_at", "updated_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        data.update({
            "kind_label": instance.get_kind_display(),
            "status_label": status_label(instance.kind, instance.status),
            "author": _ref(instance.author, instance.author.get_full_name() or instance.author.username),
            "group_detail": _ref(instance.group, instance.group.name if instance.group_id else None),
            "teacher_detail": _ref(instance.teacher),
            "student_detail": _ref(instance.student),
            "title": report_title(instance),
            "can_edit": bool(request and request.user.pk == instance.author_id),
        })
        if self.context.get("detail"):
            data["tasks"] = WorkLogEntrySerializer(
                instance.tasks.select_related("author", "group", "teacher__user", "student"),
                many=True, context=self.context,
            ).data
            if instance.kind == ReportKind.DAILY:
                entries = WorkLogEntry.objects.filter(
                    author=instance.author, date=instance.date, entry_kind=WorkLogEntry.Kind.LOG,
                ).select_related("author", "group", "teacher__user", "student").order_by("time_from", "id")
                data["day_entries"] = WorkLogEntrySerializer(entries, many=True, context=self.context).data
        return data

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        if self.instance is not None and "kind" in attrs and attrs["kind"] != self.instance.kind:
            raise serializers.ValidationError({"kind": "Вид отчёта нельзя изменить."})
        schema = REPORT_KINDS[kind]
        status = attrs.get("status", getattr(self.instance, "status", None) or schema["statuses"][0][0])
        if status not in dict(schema["statuses"]):
            raise serializers.ValidationError({"status": "Недопустимый статус для этого отчёта."})
        attrs["status"] = status

        # Lesson / student links fill in the rest from the LMS.
        lesson = attrs.get("lesson", getattr(self.instance, "lesson", None))
        if lesson is not None:
            attrs.setdefault("group", lesson.group)
            attrs["teacher"] = attrs.get("teacher") or lesson.effective_teacher
            attrs.setdefault("date", lesson.date)
        student = attrs.get("student", getattr(self.instance, "student", None))
        if student is not None and kind == ReportKind.PROBLEM_STUDENT:
            attrs.setdefault("group", student.group)

        merged = lambda f: attrs.get(f, getattr(self.instance, f, None))  # noqa: E731
        errors = {}
        for link in schema.get("required_links", []):
            if merged(link) is None:
                errors[link] = "Обязательное поле."
        if schema["period"] == "range":
            start, end = merged("period_start"), merged("period_end")
            if not start or not end:
                errors["period_start"] = "Укажите период."
            elif end < start:
                errors["period_end"] = "Конец периода раньше начала."
        if errors:
            raise serializers.ValidationError(errors)

        # A draft may be incomplete; anything past «Черновик» must be complete.
        require_complete = status != "draft" and not (kind == ReportKind.PROBLEM_STUDENT and status == "new")
        try:
            attrs["data"] = clean_report_data(kind, attrs.get("data", getattr(self.instance, "data", {})),
                                              require_complete=require_complete)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"data": exc.message_dict})
        return attrs


def report_title(report: TeamLeadReport) -> str:
    about = report.teacher or report.student or report.group
    when = (
        f"{report.period_start:%d.%m.%Y} — {report.period_end:%d.%m.%Y}"
        if report.period_start and report.period_end else f"{report.date:%d.%m.%Y}"
    )
    return " · ".join(str(p) for p in (report.get_kind_display(), about, when) if p)


def refresh_metrics(report: TeamLeadReport) -> None:
    report.metrics = metrics_service.compute(report)
    report.metrics_calculated_at = timezone.now()
    report.save(update_fields=["metrics", "metrics_calculated_at", "updated_at"])
