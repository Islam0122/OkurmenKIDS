"""Workflow задач: создание, изменение, переходы статусов, проверка,
чек-лист, комментарии, вложения — каждое действие в одной транзакции и с
записью в TaskHistory.

Переходы (кто — см. permissions):

    pending / rejected ──start──▶ in_progress
    pending / in_progress / rejected ──submit──▶ review      (requires_approval)
                                      ──submit──▶ completed  (без подтверждения)
    review ──approve──▶ completed
    review ──reject (комментарий обязателен)──▶ rejected
    любой открытый / review ──cancel──▶ cancelled
    completed / cancelled ──reopen──▶ pending

«Просрочена» — не переход, а вычисляемое состояние (Task.effective_status).
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ..departments import department_of
from ..models import (
    CLOSED_STATUSES,
    NotificationKind,
    OPEN_STATUSES,
    Task,
    TaskAttachment,
    TaskChecklistItem,
    TaskComment,
    TaskHistory,
    TaskReview,
    TaskStatus,
)
from ..permissions import can_assign_department, can_assign_to, can_review, is_executor, is_task_manager
from .notifications import notify

A = TaskHistory.Action
EDITABLE_FIELDS = ("title", "description", "priority", "category", "start_date", "deadline", "requires_approval",
                   "reviewer", "department")


def task_link(task: Task) -> str:
    return f"/tasks/{task.pk}"


def log(task: Task, actor, action: str, *, from_status: str = "", to_status: str = "", changes=None, comment=""):
    return TaskHistory.objects.create(task=task, actor=actor, action=action, from_status=from_status,
                                      to_status=to_status, changes=changes or {}, comment=comment)


def _notify_assigned(task: Task, actor) -> None:
    if task.assignee_id and task.assignee_id != getattr(actor, "pk", None):
        notify(task.assignee, NotificationKind.TASK_ASSIGNED, f"task:{task.pk}:assigned:{task.assignee_id}",
               f"Новая задача: {task.title}", f"Поставил(а): {actor}" if actor else "", task_link(task))


def create_task(actor, data: dict, checklist: list[str] | None = None) -> Task:
    assignee = data.get("assignee")
    department = data.get("department") or (department_of(assignee) if assignee else department_of(actor))
    if assignee is not None and not can_assign_to(actor, assignee):
        raise PermissionDenied("Этому сотруднику вы не можете ставить задачи.")
    if assignee is None and not can_assign_department(actor, department):
        raise PermissionDenied("Ставить задачи этому отделу вы не можете.")
    reviewer = data.get("reviewer")
    if reviewer is not None and not reviewer.is_active:
        raise ValidationError({"reviewer": "Проверяющий должен быть активным сотрудником."})
    with transaction.atomic():
        task = Task.objects.create(created_by=actor, department=department, **{
            k: v for k, v in data.items() if k not in ("department", "checklist")
        })
        for position, text in enumerate(checklist or []):
            if text.strip():
                TaskChecklistItem.objects.create(task=task, text=text.strip()[:255], position=position)
        log(task, actor, A.CREATED, to_status=task.status)
        _notify_assigned(task, actor)
    return task


def update_task(actor, task: Task, data: dict) -> Task:
    if not is_task_manager(actor, task):
        raise PermissionDenied("Менять условия задачи может её автор или руководитель.")
    if task.status in CLOSED_STATUSES:
        raise ValidationError({"detail": "Закрытую задачу нельзя изменить — откройте её снова."})
    changes = {}
    for field in EDITABLE_FIELDS:
        if field not in data:
            continue
        old, new = getattr(task, field), data[field]
        if old != new:
            changes[field] = [_plain(old), _plain(new)]
            setattr(task, field, new)
    if "assignee" in data and data["assignee"] != task.assignee:
        return _reassign(actor, task, data["assignee"], changes)
    if changes:
        with transaction.atomic():
            task.save()
            log(task, actor, A.UPDATED, changes=changes)
    return task


def _plain(value):
    if hasattr(value, "pk"):
        return value.pk
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _reassign(actor, task: Task, assignee, changes: dict) -> Task:
    if assignee is not None and not can_assign_to(actor, assignee):
        raise PermissionDenied("Этому сотруднику вы не можете передать задачу.")
    changes["assignee"] = [task.assignee_id, getattr(assignee, "pk", None)]
    with transaction.atomic():
        task.assignee = assignee
        if assignee is not None and "department" not in changes:
            task.department = department_of(assignee)
        task.save()
        log(task, actor, A.ASSIGNED, changes=changes)
        _notify_assigned(task, actor)
    return task


def _transition(task: Task, actor, action: str, to_status: str, *, comment: str = "", **stamps) -> Task:
    from_status = task.status
    task.status = to_status
    for field, value in stamps.items():
        setattr(task, field, value)
    task.save()
    log(task, actor, action, from_status=from_status, to_status=to_status, comment=comment)
    return task


@transaction.atomic
def start(actor, task: Task) -> Task:
    task = Task.objects.select_for_update().get(pk=task.pk)
    if not is_executor(actor, task):
        raise PermissionDenied("Взять задачу в работу может только её исполнитель.")
    if task.status not in (TaskStatus.PENDING, TaskStatus.REJECTED):
        raise ValidationError({"detail": "Задача уже в работе или закрыта."})
    if task.assignee_id is None:
        task.assignee = actor  # задачу отдела берёт тот, кто начал её выполнять
    return _transition(task, actor, A.STARTED, TaskStatus.IN_PROGRESS, started_at=timezone.now())


@transaction.atomic
def submit(actor, task: Task, comment: str = "") -> Task:
    task = Task.objects.select_for_update().get(pk=task.pk)
    if not is_executor(actor, task):
        raise PermissionDenied("Сдать задачу может только её исполнитель.")
    if task.status not in OPEN_STATUSES:
        raise ValidationError({"detail": "Задачу в этом статусе нельзя сдать."})
    if task.checklist.filter(is_done=False).exists():
        raise ValidationError({"detail": "Сначала отметьте все пункты чек-листа."})
    if task.assignee_id is None:
        task.assignee = actor
    now = timezone.now()
    if task.requires_approval:
        _transition(task, actor, A.SUBMITTED, TaskStatus.REVIEW, comment=comment, submitted_at=now)
        reviewer = task.reviewer or task.created_by
        if reviewer.pk != actor.pk:
            notify(reviewer, NotificationKind.TASK_REVIEW, f"task:{task.pk}:review:{now.timestamp():.0f}",
                   f"Задача ждёт проверки: {task.title}", f"Исполнитель: {actor}", task_link(task))
        return task
    return _transition(task, actor, A.COMPLETED, TaskStatus.COMPLETED, comment=comment, submitted_at=now,
                       completed_at=now)


@transaction.atomic
def approve(actor, task: Task, comment: str = "") -> Task:
    task = Task.objects.select_for_update().get(pk=task.pk)
    if not can_review(actor, task):
        raise PermissionDenied("Подтвердить задачу может только проверяющий.")
    if task.status != TaskStatus.REVIEW:
        raise ValidationError({"detail": "Задача не на проверке."})
    TaskReview.objects.create(task=task, reviewer=actor, decision=TaskReview.Decision.APPROVED, comment=comment)
    _transition(task, actor, A.APPROVED, TaskStatus.COMPLETED, comment=comment, completed_at=timezone.now())
    notify(task.assignee, NotificationKind.TASK_APPROVED, f"task:{task.pk}:approved:{task.reviews.count()}",
           f"Задача подтверждена: {task.title}", comment, task_link(task))
    return task


@transaction.atomic
def reject(actor, task: Task, comment: str) -> Task:
    task = Task.objects.select_for_update().get(pk=task.pk)
    if not can_review(actor, task):
        raise PermissionDenied("Вернуть задачу может только проверяющий.")
    if task.status != TaskStatus.REVIEW:
        raise ValidationError({"detail": "Задача не на проверке."})
    comment = (comment or "").strip()
    if not comment:
        raise ValidationError({"comment": "Укажите, что нужно доработать."})
    TaskReview.objects.create(task=task, reviewer=actor, decision=TaskReview.Decision.REJECTED, comment=comment)
    _transition(task, actor, A.REJECTED, TaskStatus.REJECTED, comment=comment)
    notify(task.assignee, NotificationKind.TASK_REJECTED, f"task:{task.pk}:rejected:{task.reviews.count()}",
           f"Задача возвращена на доработку: {task.title}", comment, task_link(task))
    return task


@transaction.atomic
def cancel(actor, task: Task, comment: str = "") -> Task:
    task = Task.objects.select_for_update().get(pk=task.pk)
    if not is_task_manager(actor, task):
        raise PermissionDenied("Отменить задачу может её автор или руководитель.")
    if task.status in CLOSED_STATUSES:
        raise ValidationError({"detail": "Задача уже закрыта."})
    return _transition(task, actor, A.CANCELLED, TaskStatus.CANCELLED, comment=comment, cancelled_at=timezone.now())


@transaction.atomic
def reopen(actor, task: Task, comment: str = "") -> Task:
    task = Task.objects.select_for_update().get(pk=task.pk)
    if not is_task_manager(actor, task):
        raise PermissionDenied("Открыть задачу снова может её автор или руководитель.")
    if task.status not in CLOSED_STATUSES:
        raise ValidationError({"detail": "Задача не закрыта."})
    return _transition(task, actor, A.REOPENED, TaskStatus.PENDING, comment=comment, completed_at=None,
                       cancelled_at=None)


ACTIONS = {"start": start, "submit": submit, "approve": approve, "reject": reject, "cancel": cancel, "reopen": reopen}


def available_actions(user, task: Task) -> list[str]:
    """Что пользователь может сделать с задачей сейчас — для кнопок UI
    (сервер всё равно проверит каждое действие)."""
    actions = []
    executor, manager, reviewer = is_executor(user, task), is_task_manager(user, task), can_review(user, task)
    if executor and task.status in (TaskStatus.PENDING, TaskStatus.REJECTED):
        actions.append("start")
    if executor and task.status in OPEN_STATUSES:
        actions.append("submit")
    if reviewer and task.status == TaskStatus.REVIEW:
        actions += ["approve", "reject"]
    if manager and task.status not in CLOSED_STATUSES:
        actions += ["edit", "cancel"]
    if manager and task.status in CLOSED_STATUSES:
        actions.append("reopen")
    return actions


# --- Чек-лист, комментарии, вложения ----------------------------------------

def _can_work(user, task: Task) -> bool:
    return is_executor(user, task) or is_task_manager(user, task)


@transaction.atomic
def add_checklist_item(actor, task: Task, text: str) -> TaskChecklistItem:
    if not is_task_manager(actor, task):
        raise PermissionDenied("Пункты чек-листа добавляет автор задачи или руководитель.")
    text = (text or "").strip()
    if not text:
        raise ValidationError({"text": "Пункт не может быть пустым."})
    position = (task.checklist.order_by("-position").values_list("position", flat=True).first() or 0) + 1
    item = TaskChecklistItem.objects.create(task=task, text=text[:255], position=position)
    log(task, actor, A.CHECKLIST, changes={"added": item.text})
    return item


@transaction.atomic
def toggle_checklist_item(actor, task: Task, item: TaskChecklistItem, done: bool) -> TaskChecklistItem:
    if not _can_work(actor, task):
        raise PermissionDenied("Отмечать пункты может исполнитель задачи.")
    if task.status in CLOSED_STATUSES:
        raise ValidationError({"detail": "Задача закрыта."})
    item.is_done = done
    item.done_by = actor if done else None
    item.done_at = timezone.now() if done else None
    item.save(update_fields=["is_done", "done_by", "done_at"])
    log(task, actor, A.CHECKLIST, changes={"item": item.text, "done": done})
    return item


@transaction.atomic
def add_comment(actor, task: Task, text: str) -> TaskComment:
    text = (text or "").strip()
    if not text:
        raise ValidationError({"text": "Комментарий не может быть пустым."})
    comment = TaskComment.objects.create(task=task, author=actor, text=text)
    log(task, actor, A.COMMENTED, comment=text[:500])
    for participant in {task.assignee, task.created_by, task.reviewer} - {None, actor}:
        notify(participant, NotificationKind.TASK_COMMENT, f"task:{task.pk}:comment:{comment.pk}:{participant.pk}",
               f"Комментарий к задаче: {task.title}", f"{actor}: {text[:300]}", task_link(task))
    return comment


ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".txt", ".png", ".jpg",
                      ".jpeg", ".webp", ".zip"}


@transaction.atomic
def add_attachment(actor, task: Task, upload) -> TaskAttachment:
    import os

    from django.conf import settings

    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError({"file": "Недопустимый тип файла."})
    limit = getattr(settings, "OPERATIONS_ATTACHMENT_MAX_MB", 10) * 1024 * 1024
    if upload.size > limit:
        raise ValidationError({"file": f"Файл больше {limit // (1024 * 1024)} МБ."})
    attachment = TaskAttachment.objects.create(
        task=task, file=upload, original_name=os.path.basename(upload.name)[:255],
        content_type=(getattr(upload, "content_type", "") or "")[:120], size=upload.size, uploaded_by=actor,
    )
    log(task, actor, A.ATTACHMENT, changes={"added": attachment.original_name})
    return attachment


@transaction.atomic
def delete_attachment(actor, task: Task, attachment: TaskAttachment) -> None:
    if attachment.uploaded_by_id != actor.pk and not is_task_manager(actor, task):
        raise PermissionDenied("Удалить вложение может тот, кто его загрузил, или руководитель.")
    name = attachment.original_name
    attachment.file.delete(save=False)
    attachment.delete()
    log(task, actor, A.ATTACHMENT, changes={"removed": name})
