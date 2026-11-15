"""Bulk generation of Student & Parent Portal accounts (Assistant Workspace).

Every account is created by `accounts.provision_account` — the same audited
function the single-student flow uses — so the role, the password hashing,
the first-login password change and the student link all come from there.
This module only decides *which* students get an account, *what login* they
get, and what happens to the temporary passwords afterwards:

* Scope — all active students, or the students of selected groups (one group
  is just a selection of one).
* Skipped — a student who already has a portal account (a StudentLink) is
  recorded as «already existed» and never touched: no new user, no new
  password, no reset.
* Logins — `begaly01`, `begaly02`… : the transliterated first name plus the
  first free two-digit number. The number is the duplicate suffix, so two
  Begalys get begaly01 and begaly02 and no login is ever reused.
* Batches — a run is processed a few students per call (`process_batch`), so
  no HTTP request waits for a long series of password hashes. Each student is
  its own transaction: one failure is recorded with its reason and the rest
  carry on. A failed student is retried by a new run (`create_retry_run`) that
  only contains students who still have no account.
* Passwords — kept only as Fernet tokens until the XLSX is downloaded (one
  time) or 24 hours pass, then wiped. See apps.portal.models.

Nothing here reads or writes an existing account's password.
"""
from __future__ import annotations

import base64
import datetime as dt
import io
import logging
import re

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.academy.models import Group, Student
from ..models import BulkAccountRun, BulkAccountRunItem, PortalAccount, StudentLink
from . import accounts

logger = logging.getLogger(__name__)

SECRET_TTL = dt.timedelta(hours=24)
BATCH_MAX = 25
RUN_LOCK_TIMEOUT = dt.timedelta(hours=2)
EXPORT_HEADERS = (
    "Student ID", "Student Full Name", "Group", "Username", "Temporary Password",
    "Account Status", "Creation Date",
)
ACCOUNT_STATUS_LABELS = {"pending": "Ожидает первого входа", "active": "Активен", "disabled": "Отключён"}


class RunConflict(Exception):
    """Another batch is still running — only one at a time."""


# ---------------------------------------------------------------------------
# Sealing of temporary passwords (Fernet, key derived from SECRET_KEY)
# ---------------------------------------------------------------------------

def _fernet() -> Fernet:
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"okurmen.portal.bulk-account-credentials.v1",
    ).derive(settings.SECRET_KEY.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def seal(password: str) -> str:
    return _fernet().encrypt(password.encode()).decode()


def unseal(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


# ---------------------------------------------------------------------------
# Scope and logins
# ---------------------------------------------------------------------------

def parse_scope(scope: str, group_ids) -> tuple[str, list[int]]:
    if scope == BulkAccountRun.Scope.ALL:
        return scope, []
    ids = sorted({int(g) for g in group_ids or []})
    if not ids:
        raise ValidationError({"group_ids": "Выберите хотя бы одну группу."})
    found = set(Group.objects.filter(pk__in=ids).values_list("pk", flat=True))
    missing = [g for g in ids if g not in found]
    if missing:
        raise ValidationError({"group_ids": "Группа не найдена."})
    return scope, ids


def target_students(scope: str, group_ids: list[int]):
    qs = Student.objects.filter(is_active=True).select_related("group")
    if scope == BulkAccountRun.Scope.GROUPS:
        qs = qs.filter(group_id__in=group_ids)
    return qs.order_by("last_name", "first_name", "pk")


def plan_login(first_name: str, *, reserved: set[str] | None = None) -> str:
    """`begaly01`, `begaly02`… — the first name in Latin letters and digits,
    then the first number that no account (or planned login) uses yet."""
    base = re.sub(r"[^a-z0-9]", "", accounts.transliterate(first_name))[:30] or "student"
    reserved = reserved or set()
    number = 1
    while True:
        candidate = f"{base}{number:02d}"
        if candidate not in reserved and not accounts._login_taken(candidate):
            return candidate
        number += 1


def group_names(group_ids: list[int]) -> list[str]:
    return list(Group.objects.filter(pk__in=group_ids).order_by("name").values_list("name", flat=True))


def preview(scope: str, group_ids) -> dict:
    """What a run would do right now, without writing anything."""
    scope, group_ids = parse_scope(scope, group_ids)
    students = list(target_students(scope, group_ids))
    linked = dict(
        StudentLink.objects.filter(student__in=students)
        .select_related("account__user").values_list("student_id", "account__user__username")
    )
    reserved: set[str] = set()
    rows = []
    for student in students:
        if student.pk in linked:
            login, has_account = linked[student.pk], True
        else:
            login = plan_login(student.first_name, reserved=reserved)
            reserved.add(login)
            has_account = False
        rows.append({
            "id": student.pk, "full_name": str(student), "group": student.group.name if student.group else "",
            "has_account": has_account, "login": login,
        })
    existing = sum(1 for r in rows if r["has_account"])
    return {
        "scope": scope,
        "group_ids": group_ids,
        "group_names": group_names(group_ids),
        "total": len(rows),
        "existing": existing,
        "to_create": len(rows) - existing,
        "students": rows,
    }


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def _ensure_no_active_run() -> None:
    cutoff = timezone.now() - RUN_LOCK_TIMEOUT
    active = BulkAccountRun.objects.filter(
        status__in=[BulkAccountRun.Status.PENDING, BulkAccountRun.Status.RUNNING], created_at__gte=cutoff,
    ).order_by("-pk").first()
    if active is not None:
        raise RunConflict(
            f"Пакет №{active.pk} ещё не завершён. Продолжите его или дождитесь завершения, "
            "прежде чем запускать новый."
        )


def _log(actor, obj, message: str) -> None:
    if actor is None or not getattr(actor, "pk", None):
        return
    LogEntry.objects.log_actions(
        user_id=actor.pk, queryset=[obj], action_flag=CHANGE, change_message=message, single_object=True,
    )


def _finish_if_done(run: BulkAccountRun) -> None:
    if run.items.filter(status=BulkAccountRunItem.Status.PENDING).exists():
        return
    run.status = BulkAccountRun.Status.COMPLETED
    run.finished_at = timezone.now()
    if run.items.filter(sealed_password__gt="").exists():
        run.export_state = BulkAccountRun.ExportState.READY
        run.secrets_expire_at = timezone.now() + SECRET_TTL
    else:
        run.export_state = BulkAccountRun.ExportState.NONE


def _new_run(*, scope, group_ids, performed_by, retry_of=None) -> BulkAccountRun:
    return BulkAccountRun.objects.create(
        scope=scope, group_ids=group_ids, group_names=group_names(group_ids),
        retry_of=retry_of, created_by=performed_by,
    )


def create_run(scope: str, group_ids, *, performed_by) -> BulkAccountRun:
    """Record every active student in scope: those with an account are marked
    «already existed» at once, the rest wait in the queue."""
    scope, group_ids = parse_scope(scope, group_ids)
    with transaction.atomic():
        _ensure_no_active_run()
        run = _new_run(scope=scope, group_ids=group_ids, performed_by=performed_by)
        students = list(target_students(scope, group_ids))
        _add_items(run, students)
        _finish_if_done(run)
        run.save()
        _log(performed_by, performed_by,
             f"Кабинеты учеников: пакет №{run.pk} запущен (охват: {_scope_label(run)}, студентов: {run.items.count()}).")
    return run


def create_retry_run(run: BulkAccountRun, *, performed_by) -> BulkAccountRun:
    """New run with only the failed students of `run` who still have no account."""
    with transaction.atomic():
        _ensure_no_active_run()
        failed = [
            item.student for item in run.items.filter(status=BulkAccountRunItem.Status.FAILED).select_related("student__group")
            if item.student is not None and item.student.is_active
        ]
        retry = _new_run(scope=run.scope, group_ids=run.group_ids, performed_by=performed_by, retry_of=run)
        _add_items(retry, failed)
        if not retry.items.filter(status=BulkAccountRunItem.Status.PENDING).exists():
            # Raising rolls the whole transaction back, so nothing of the empty retry is kept.
            raise ValidationError({"detail": "Нет неудачных аккаунтов для повтора."})
        _finish_if_done(retry)
        retry.save()
        _log(performed_by, performed_by, f"Кабинеты учеников: повтор пакета №{run.pk} → пакет №{retry.pk}.")
    return retry


def _add_items(run: BulkAccountRun, students) -> None:
    students = list(students)
    linked = set(StudentLink.objects.filter(student__in=students).values_list("student_id", flat=True))
    BulkAccountRunItem.objects.bulk_create([
        BulkAccountRunItem(
            run=run, student=student, student_name=str(student)[:300],
            group_name=(student.group.name if student.group else "")[:150],
            status=(BulkAccountRunItem.Status.EXISTING if student.pk in linked
                    else BulkAccountRunItem.Status.PENDING),
        )
        for student in students
    ])


def _scope_label(run: BulkAccountRun) -> str:
    if run.scope == BulkAccountRun.Scope.ALL:
        return "все активные студенты"
    return "группы: " + ", ".join(run.group_names)


def process_batch(run: BulkAccountRun, *, performed_by, limit: int = 10) -> BulkAccountRun:
    """Create accounts for the next `limit` pending students of the run."""
    limit = max(1, min(int(limit or 10), BATCH_MAX))
    with transaction.atomic():
        run = BulkAccountRun.objects.select_for_update().get(pk=run.pk)
        purge_expired_secrets(run)
        if run.status == BulkAccountRun.Status.COMPLETED:
            return run
        pending = list(run.items.filter(status=BulkAccountRunItem.Status.PENDING).select_related("student")[:limit])
        if run.status == BulkAccountRun.Status.PENDING:
            run.status = BulkAccountRun.Status.RUNNING
            run.save(update_fields=["status"])
        for item in pending:
            _process_item(item, performed_by=performed_by)
        _finish_if_done(run)
        run.save()
        if not run.items.filter(status=BulkAccountRunItem.Status.PENDING).exists():
            _log(performed_by, performed_by,
                 f"Кабинеты учеников: пакет №{run.pk} завершён — создано {run.items.filter(status='created').count()}, "
                 f"уже были {run.items.filter(status='existing').count()}, ошибок {run.items.filter(status='failed').count()}.")
    return run


def _process_item(item: BulkAccountRunItem, *, performed_by) -> None:
    student = item.student
    if student is None:
        _fail(item, "Студент удалён из системы.")
        return
    try:
        with transaction.atomic():
            student = Student.objects.select_for_update().get(pk=student.pk)
            if StudentLink.objects.filter(student=student).exists():
                item.status = BulkAccountRunItem.Status.EXISTING
                item.error = ""
                item.save(update_fields=["status", "error", "updated_at"])
                return
            login = plan_login(student.first_name)
            issued = accounts.provision_account(student, performed_by=performed_by, login=login)
            item.status = BulkAccountRunItem.Status.CREATED
            item.login = issued.login
            item.account = issued.account
            item.sealed_password = seal(issued.password)
            item.issued_at = timezone.now()
            item.error = ""
            item.save()
    except ValidationError as exc:
        _fail(item, " ".join(exc.messages)[:500])
    except Exception:  # noqa: BLE001 — one student must not stop the batch; the reason is logged server-side.
        logger.exception("Bulk account creation failed for student %s", item.student_id)
        _fail(item, "Не удалось создать аккаунт. Попробуйте повторить.")


def _fail(item: BulkAccountRunItem, reason: str) -> None:
    item.status = BulkAccountRunItem.Status.FAILED
    item.error = reason
    item.sealed_password = ""
    item.save(update_fields=["status", "error", "sealed_password", "updated_at"])


# ---------------------------------------------------------------------------
# One-time export and secret lifetime
# ---------------------------------------------------------------------------

def purge_expired_secrets(run: BulkAccountRun) -> None:
    if run.export_state == BulkAccountRun.ExportState.READY and run.secrets_expire_at and run.secrets_expire_at <= timezone.now():
        run.items.update(sealed_password="")
        run.export_state = BulkAccountRun.ExportState.EXPIRED
        run.save(update_fields=["export_state"])


def purge_all_expired() -> None:
    for run in BulkAccountRun.objects.filter(
        export_state=BulkAccountRun.ExportState.READY, secrets_expire_at__lte=timezone.now(),
    ):
        purge_expired_secrets(run)


def export_xlsx(run_pk: int, *, performed_by) -> bytes:
    """The run's credentials as XLSX — once. Afterwards every password of the
    run is wiped, whatever the file was used for. Only this run's accounts."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    with transaction.atomic():
        run = BulkAccountRun.objects.select_for_update().get(pk=run_pk)
        purge_expired_secrets(run)
        if run.export_state != BulkAccountRun.ExportState.READY:
            raise ValidationError({"detail": "Учётные данные этого пакета уже выгружены или срок их хранения истёк."})
        items = list(run.items.filter(status=BulkAccountRunItem.Status.CREATED).exclude(sealed_password="")
                     .select_related("account__user").order_by("pk"))
        wb = Workbook()
        ws = wb.active
        ws.title = "Учётные данные"
        ws.append(list(EXPORT_HEADERS))
        for item in items:
            password = unseal(item.sealed_password) or "— не удалось прочитать, сбросьте пароль —"
            account = item.account
            status_label = ACCOUNT_STATUS_LABELS.get(account.credentials_status, "") if account else ""
            created = timezone.localtime(item.issued_at).strftime("%d.%m.%Y %H:%M") if item.issued_at else ""
            ws.append([
                item.student_id or "", item.student_name, item.group_name, item.login, password, status_label, created,
            ])
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="1F4E79")
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        widths = [12, 34, 18, 18, 22, 24, 18]
        for index, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(index)].width = width
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:G{max(ws.max_row, 1)}"
        wb.properties.title = f"Учётные данные кабинетов — пакет №{run.pk}"
        wb.properties.creator = "OkurmenKIDS"
        buffer = io.BytesIO()
        wb.save(buffer)
        data = buffer.getvalue()

        run.items.update(sealed_password="")
        run.export_state = BulkAccountRun.ExportState.DOWNLOADED
        run.exported_at = timezone.now()
        run.exported_by = performed_by
        run.save(update_fields=["export_state", "exported_at", "exported_by"])
        _log(performed_by, performed_by,
             f"Кабинеты учеников: пакет №{run.pk} выгружен в Excel ({len(items)} учётных записей, одноразово).")
    return data


def can_download(run: BulkAccountRun, user) -> bool:
    from apps.users.permissions import is_admin_user

    return bool(run.created_by_id == getattr(user, "pk", None) or is_admin_user(user))


def export_filename(run: BulkAccountRun) -> str:
    return f"okurmen_kids_accounts_run{run.pk}_{timezone.localdate():%Y%m%d}.xlsx"


__all__ = [
    "RunConflict", "create_run", "create_retry_run", "process_batch", "export_xlsx", "preview",
    "purge_all_expired", "can_download", "export_filename", "parse_scope", "seal", "unseal",
]
