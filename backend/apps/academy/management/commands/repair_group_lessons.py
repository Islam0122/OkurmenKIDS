"""Audit — and, only when explicitly asked, repair — a group's generated lessons.

Built for data produced before the lesson generator resolved trainers per
subject and before generation stopped firing on every single schedule-slot
save (see services.lesson_generator / signals.py): e.g. a group whose 144
lessons all landed on Mondays up to 2029, with Soft Skills/English lessons
owned by the IT trainer.

Read-only by default:

    python manage.py repair_group_lessons                # audit every non-cancelled group
    python manage.py repair_group_lessons --group 12     # audit one group in detail

Rebuild (one group at a time, inside one transaction):

    python manage.py repair_group_lessons --group 12 --apply [--from-date 2026-09-23]

`--apply` deletes only *untouched* lessons dated on/after `--from-date`
(default: today) — status "Запланирован", never started, no attendance, no
homework results, no homework other than the one auto-created from the plan
— and then runs the normal generator for the missing plan rows, placing them
only on/after `--from-date`. Every lesson with any real activity, and every
past lesson, is kept exactly as it is; ones that look wrong are listed for a
manual decision instead.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.academy.constants import WEEKDAY_CODES, WEEKDAY_LABELS_SHORT
from apps.academy.models import Group, GroupTeacher, Lesson
from apps.academy.services.lesson_generator import generate_lessons_for_group_with_report
from apps.academy.services.subject_assignments import STATUS_UNASSIGNED, subject_assignment_overview


def _annotated_lessons(group: Group):
    return (
        Lesson.objects.filter(group=group)
        .select_related("teacher__user", "group_teacher__teacher__user", "subject", "plan")
        .annotate(
            _attendance_count=Count("attendance_records", distinct=True),
            _result_count=Count("homeworks__results", distinct=True),
            _homework_count=Count("homeworks", distinct=True),
        )
    )


def _is_untouched(lesson: Lesson) -> bool:
    if lesson.status != Lesson.Status.SCHEDULED or lesson.started_at is not None:
        return False
    if lesson._attendance_count or lesson._result_count:
        return False
    # The generator auto-creates at most one Homework from the plan row;
    # anything beyond that was added by a person.
    return lesson._homework_count <= (1 if lesson.plan_id and lesson.plan.homework_title else 0)


def _expected_teacher_ids(group: Group) -> dict[int, set[int]]:
    """subject_id -> teacher ids an active assignment allows for it."""
    allowed: dict[int, set[int]] = {}
    for gt in GroupTeacher.objects.filter(group=group, is_active=True, subject__isnull=False):
        allowed.setdefault(gt.subject_id, set()).add(gt.teacher_id)
    return allowed


class Command(BaseCommand):
    help = "Проверка (и, с --apply, перестроение) сгенерированных занятий группы."

    def add_arguments(self, parser):
        parser.add_argument("--group", type=int, help="ID группы. Без него — краткий аудит всех групп.")
        parser.add_argument(
            "--apply", action="store_true",
            help="Удалить нетронутые будущие занятия группы и сгенерировать их заново. Требует --group.",
        )
        parser.add_argument(
            "--from-date", type=dt.date.fromisoformat,
            help="Дата (YYYY-MM-DD), с которой перестраивать занятия. По умолчанию — сегодня.",
        )

    def handle(self, *args, **options):
        group_id = options.get("group")
        apply = options.get("apply")
        from_date = options.get("from_date") or timezone.localdate()

        if apply and not group_id:
            raise CommandError("--apply работает только для одной группы: укажите --group <id>.")

        if not group_id:
            groups = Group.objects.exclude(status=Group.Status.CANCELLED).select_related("course").order_by("name")
            for group in groups:
                self._audit(group, from_date, verbose=False)
            return

        group = Group.objects.select_related("course").filter(pk=group_id).first()
        if group is None:
            raise CommandError(f"Группа с id={group_id} не найдена.")

        self._audit(group, from_date, verbose=True)
        if apply:
            self._apply(group, from_date)
        else:
            self.stdout.write("\nРежим проверки: ничего не изменено. Добавьте --apply, чтобы перестроить занятия.")

    # -- audit ------------------------------------------------------------

    def _audit(self, group: Group, from_date: dt.date, *, verbose: bool) -> None:
        lessons = list(_annotated_lessons(group).order_by("date", "start_time"))
        allowed = _expected_teacher_ids(group)
        problems = []

        outside = [
            l for l in lessons
            if l.date < group.start_date or (group.end_date and l.date > group.end_date)
        ]
        if outside:
            problems.append(f"вне периода группы: {len(outside)}")

        slot_days = set(group.schedules.filter(is_active=True).values_list("day_of_week", flat=True))
        weekday_counts = Counter(WEEKDAY_CODES[l.date.weekday()] for l in lessons)
        off_schedule = sum(n for day, n in weekday_counts.items() if day not in slot_days)
        if slot_days and off_schedule:
            problems.append(f"в дни без слота расписания: {off_schedule}")
        missing_days = [day for day in slot_days if not weekday_counts.get(day)]
        if lessons and missing_days:
            problems.append(
                "нет ни одного занятия в дни расписания: "
                + ", ".join(WEEKDAY_LABELS_SHORT[d] for d in sorted(missing_days, key=WEEKDAY_CODES.index))
            )

        wrong_teacher = [
            l for l in lessons
            if l.subject_id in allowed
            and (l.effective_teacher is None or l.effective_teacher.pk not in allowed[l.subject_id])
        ]
        if wrong_teacher:
            problems.append(f"тренер не совпадает с назначением на предмет: {len(wrong_teacher)}")

        unassigned = [row for row in subject_assignment_overview(group) if row.status == STATUS_UNASSIGNED]
        if unassigned:
            problems.append("предметы без тренера: " + ", ".join(row.subject_name for row in unassigned))

        span = f"{lessons[0].date:%d.%m.%Y} – {lessons[-1].date:%d.%m.%Y}" if lessons else "—"
        status = self.style.ERROR("ПРОБЛЕМЫ") if problems else self.style.SUCCESS("OK")
        self.stdout.write(
            f"[{status}] #{group.pk} «{group.name}» ({group.start_date:%d.%m.%Y} – "
            f"{group.end_date.strftime('%d.%m.%Y') if group.end_date else '…'}): "
            f"занятий {len(lessons)}, даты {span}"
            + (f"; {'; '.join(problems)}" if problems else "")
        )
        if not verbose:
            return

        by_day = ", ".join(
            f"{WEEKDAY_LABELS_SHORT[d]}={weekday_counts[d]}" for d in WEEKDAY_CODES if weekday_counts.get(d)
        )
        self.stdout.write(f"  По дням недели: {by_day or '—'}")
        for row in subject_assignment_overview(group):
            names = ", ".join(str(t) for t in (row.teachers or row.legacy_teachers)) or "—"
            self.stdout.write(f"  {row.subject_name}: {row.plan_lessons} занятий в плане → {names} [{row.status_label}]")

        rebuildable = [l for l in lessons if l.date >= from_date and _is_untouched(l)]
        kept_future = [l for l in lessons if l.date >= from_date and not _is_untouched(l)]
        self.stdout.write(
            f"  С {from_date:%d.%m.%Y}: нетронутых занятий (будут перестроены при --apply) — {len(rebuildable)}, "
            f"с активностью (останутся как есть) — {len(kept_future)}."
        )
        for lesson in wrong_teacher:
            if lesson.date < from_date or not _is_untouched(lesson):
                self.stdout.write(self.style.WARNING(
                    f"  Требует ручного решения: занятие №{lesson.lesson_number} {lesson.date:%d.%m.%Y} "
                    f"«{lesson.subject}» ведёт {lesson.effective_teacher or '—'} (статус: {lesson.get_status_display()})"
                ))

    # -- apply ------------------------------------------------------------

    def _apply(self, group: Group, from_date: dt.date) -> None:
        with transaction.atomic():
            doomed = [l.pk for l in _annotated_lessons(group).filter(date__gte=from_date) if _is_untouched(l)]
            deleted = Lesson.objects.filter(pk__in=doomed).delete()[1].get("academy.Lesson", 0)
            report = generate_lessons_for_group_with_report(group, not_before=from_date)
            if report.errors and not report.created:
                # Raising inside the atomic block rolls the deletions back:
                # the data stays exactly as it was rather than half-rebuilt.
                raise CommandError("Генерация не удалась, изменения отменены: " + " ".join(report.errors))

        self.stdout.write(self.style.SUCCESS(
            f"\nУдалено нетронутых занятий: {deleted}. Создано заново: {report.created}. "
            f"Всего занятий: {Lesson.objects.filter(group=group).count()} из {report.expected} по плану."
        ))
        for warning in report.warnings:
            self.stdout.write(self.style.WARNING(f"  {warning}"))
