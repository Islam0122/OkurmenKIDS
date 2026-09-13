"""Read-only audit: reports GroupSchedule rows that already conflict on
Teacher, Room, or Group (overlapping weekday + time), without modifying
anything.

`GroupSchedule.clean()` rejects a *new* conflicting slot going forward (see
models.GroupSchedule and services.group_schedule_conflicts), but data saved
before that check existed — or written directly via `.save()`/`bulk_create`,
bypassing `full_clean()` — can still be sitting in the database. This
command finds and lists it so an admin can decide what to do; it never
deletes, deactivates, or edits a single row (per spec: no automatic cleanup
of production data).
"""
from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.academy.constants import WEEKDAY_LABELS_FULL
from apps.academy.models import Group, GroupSchedule
from apps.academy.services.group_schedule_conflicts import overlapping_groups


class Command(BaseCommand):
    help = (
        "Read-only: lists existing GroupSchedule rows that already conflict "
        "on Teacher, Room, or Group (overlapping weekday + time). Makes no "
        "changes to the database."
    )

    def handle(self, *args, **options):
        slots = list(
            GroupSchedule.objects.filter(is_active=True)
            .exclude(group__status=Group.Status.CANCELLED)
            .select_related("group", "teacher__user", "room", "subject")
        )

        by_teacher = defaultdict(list)
        by_room = defaultdict(list)
        by_group = defaultdict(list)
        for slot in slots:
            by_teacher[(slot.teacher_id, slot.day_of_week)].append(slot)
            if slot.room_id:
                by_room[(slot.room_id, slot.day_of_week)].append(slot)
            by_group[(slot.group_id, slot.day_of_week)].append(slot)

        total_problems = 0
        total_problems += self._report("Тренер", by_teacher, lambda s: str(s.teacher))
        total_problems += self._report("Аудитория", by_room, lambda s: str(s.room))
        total_problems += self._report("Группа", by_group, lambda s: str(s.group))

        if total_problems == 0:
            self.stdout.write(self.style.SUCCESS("Конфликтов в расписании не найдено."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"\nВсего найдено проблемных групп конфликтов: {total_problems}. "
                    "Ничего не изменено — исправьте расписание вручную (Group Workspace → "
                    "Программы/Расписание) там, где это нужно."
                )
            )

    def _report(self, label: str, buckets: dict, resource_label_fn) -> int:
        found = 0
        for (_, day_of_week), bucket in buckets.items():
            for group in overlapping_groups(bucket):
                found += 1
                day_label = WEEKDAY_LABELS_FULL.get(day_of_week, day_of_week)
                self.stdout.write(
                    self.style.ERROR(f"\n⚠ Конфликт: {label} — {resource_label_fn(group[0])} ({day_label})")
                )
                for slot in sorted(group, key=lambda s: s.start_time):
                    self.stdout.write(
                        f"    {slot.start_time:%H:%M}-{slot.end_time:%H:%M}  "
                        f"группа «{slot.group.name}»  "
                        f"тренер «{slot.teacher}»  "
                        f"предмет «{slot.subject.name if slot.subject_id else '—'}»  "
                        f"[schedule id={slot.pk}]"
                    )
        return found
