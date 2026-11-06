"""Read-only audit: does every existing Attendance / HomeworkResult reach
the attendance matrix? Writes nothing.

    python manage.py audit_attendance_matrix [--group ID]

Reports the stored status spellings, marks on cancelled lessons, marks of
students now in another group, lessons without a trainer, roles' access
(assistants without an assignment, team leads with directions) and, per
group, how many marks the database holds vs how many the matrix shows over
the group's whole history.
"""
from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import F, Max, Min

from apps.academy.models import Attendance, Group, HomeworkResult, Lesson
from apps.attendance_matrix import matrix
from apps.attendance_matrix.models import GroupAssistant, TeamLeadDirection
from apps.users.models import User


class Command(BaseCommand):
    help = "Проверка: все ли существующие отметки посещаемости и ДЗ видны в матрице (только чтение)."

    def add_arguments(self, parser):
        parser.add_argument("--group", type=int, help="Проверить одну группу")

    def handle(self, *args, **options):
        w = self.stdout.write
        attendance = Attendance.objects.all()
        groups = Group.objects.all().order_by("name")
        if options.get("group"):
            attendance = attendance.filter(lesson__group_id=options["group"])
            groups = groups.filter(pk=options["group"])

        w("== Отметки посещаемости ==")
        w(f"Всего записей: {attendance.count()}")
        unknown = Counter()
        for raw, n in Counter(attendance.values_list("status", flat=True)).most_common():
            canon = matrix.normalize_status(raw)
            w(f"  статус {raw!r}: {n}" + ("" if canon == raw else f"  → читается как {canon!r}" if canon else "  → НЕ РАСПОЗНАН"))
            if canon is None:
                unknown[raw] = n
        w(f"На отменённых занятиях: {attendance.filter(lesson__status=Lesson.Status.CANCELLED).count()} "
          "(показываются в таблице, в статистику не входят)")
        w(f"Студент сейчас в другой группе: {attendance.exclude(student__group_id=F('lesson__group_id')).count()} "
          "(показываются, только чтение)")
        w(f"Занятия без тренера (не видны тренерам, видны админу/Team Lead/директору): "
          f"{Lesson.objects.filter(teacher__isnull=True, group_teacher__isnull=True).count()}")
        w(f"Результатов ДЗ: {HomeworkResult.objects.count()}")

        w("== Доступ ==")
        assigned = set(GroupAssistant.objects.values_list("assistant_id", flat=True))
        assistants = User.objects.filter(role=User.Role.ASSISTANT, is_active=True)
        w(f"Ассистентов: {assistants.count()}, с назначением в группы: {len(assigned)} "
          "(без назначения — видят всё только для чтения)")
        leads = User.objects.filter(role=User.Role.TEAM_LEAD, is_active=True)
        with_dirs = set(TeamLeadDirection.objects.values_list("team_lead_id", flat=True))
        w(f"Team Lead: {leads.count()}, с направлениями: {len(with_dirs)} (без направлений — вся академия)")

        w("== Покрытие по группам (вся история) ==")
        missing_total = 0
        for group in groups:
            lessons = Lesson.objects.filter(group=group)
            bounds = lessons.aggregate(first=Min("date"), last=Max("date"))
            if not bounds["first"]:
                continue
            in_db = Attendance.objects.filter(lesson__group=group).exclude(status__in=list(unknown)).count()
            data = matrix.compute([group], lessons, settings=None)[group.pk]
            shown = sum(1 for r in data["rows"] for c in r["cells"] if c["attendance"])
            missing = in_db - shown
            missing_total += missing
            if in_db or missing:
                w(f"  {group.name}: в базе {in_db}, в таблице {shown}" + (f"  ← НЕ ХВАТАЕТ {missing}" if missing else ""))
        w(f"Не попало в таблицу: {missing_total}")
        if unknown:
            w(self.style.WARNING(f"Нераспознанные статусы (показаны как «нет данных»): {dict(unknown)}"))
