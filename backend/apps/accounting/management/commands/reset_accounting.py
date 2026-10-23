"""Полный сброс бухгалтерии (зарплаты + оплата обучения) — с аудитом и копией.

    python manage.py reset_accounting                       # ТОЛЬКО аудит и план, ничего не меняет
    python manage.py reset_accounting --json audit.json     # то же + отчёт в файл

    python manage.py reset_accounting --execute --actor <суперпользователь> \\
        --backup-dir backups/ --confirm "DELETE ACCOUNTING" [--include-tariffs]

Удаляет только модели приложений `accounting` и `billing` (список и порядок —
`apps.accounting.services.maintenance`, тот же сервис, что «Очистка данных»
в Django Admin). Студенты, программы, курсы, группы, расписание, уроки,
посещаемость, сотрудники и другие модули не удаляются и не меняются — это
проверяется сравнением количеств всех их таблиц до и после, иначе откат.

Перед удалением обязательно:
* полная копия базы: PostgreSQL — `pg_dump -Fc` (нужен `pg_dump` той же
  версии), SQLite — копия файла; или `--db-backup-file` — уже сделанная
  копия (файл проверяется на существование и размер);
* JSON-выгрузка удаляемых данных (`dumpdata accounting billing`).
Удаление — одна транзакция; любая ошибка откатывает всё.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count

from apps.accounting.models import CoursePriceVersion, DemoSeedRecord
from apps.accounting.services import AccountingError, maintenance
from apps.billing.models import BillingPlan, BillingSettings
from apps.users.models import User


def tariffs_report() -> dict:
    """Тарифы и где они используются: ничего вне бухгалтерии на них не ссылается."""
    plans = []
    for plan in BillingPlan.objects.select_related("course", "subject", "created_by").annotate(
            n_profiles=Count("profiles", distinct=True), n_versions=Count("versions", distinct=True)).order_by("pk"):
        plans.append({
            "id": plan.pk, "name": plan.name, "course": plan.course.name if plan.course_id else None,
            "subject": plan.subject.name if plan.subject_id else None, "active": plan.is_active,
            "duration_months": plan.duration_months, "versions": plan.n_versions, "contracts": plan.n_profiles,
            "created_by": plan.created_by.username if plan.created_by_id else None,
            "created_at": plan.created_at.isoformat(), "demo": DemoSeedRecord.objects.filter(
                dataset="billing_demo", content_type__model="billingplan", object_id=plan.pk).exists(),
        })
    prices = [{"id": v.pk, "course": v.course.name, "price": str(v.price_per_student),
               "effective_from": v.effective_from.isoformat()}
              for v in CoursePriceVersion.objects.select_related("course").order_by("course__name", "effective_from")]
    return {"billing_plans": plans, "course_price_versions": prices}


def audit() -> dict:
    counts = maintenance.preview()
    rows = []
    for table in maintenance.PAYROLL_TABLES + maintenance.FULL_EXTRA_TABLES + maintenance.TARIFF_TABLES:
        rows.append({"key": table.key, "label": table.label, "db_table": table.db_table, "count": counts[table.key],
                     "action": "tariffs" if table in maintenance.TARIFF_TABLES else "delete", "note": table.note})
    demo = {d["dataset"]: d["n"] for d in DemoSeedRecord.objects.values("dataset").annotate(n=Count("pk"))}
    return {
        "database": {"engine": connection.vendor, "name": str(settings.DATABASES["default"].get("NAME"))},
        "tables": rows,
        "total_to_delete": sum(r["count"] for r in rows if r["action"] == "delete"),
        "tariffs": tariffs_report(),
        "kept": {
            "billing_settings": BillingSettings.objects.count(),
            "other_modules": maintenance.other_app_counts(),
        },
        "external_references": maintenance.external_references(),
        "demo_registry": demo,
    }


class Command(BaseCommand):
    help = "Аудит и полный сброс данных бухгалтерии (по умолчанию — только аудит)."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", help="Выполнить сброс (иначе — только аудит).")
        parser.add_argument("--actor", help="Суперпользователь, от имени которого выполняется сброс (журнал).")
        parser.add_argument("--confirm", default="", help=f"Фраза подтверждения: «{maintenance.CONFIRM_PHRASE}».")
        parser.add_argument("--include-tariffs", action="store_true",
                            help="Удалить и тарифы (история цен курсов, тарифы оплаты обучения с версиями).")
        parser.add_argument("--backup-dir", help="Каталог для копии базы и JSON-выгрузки бухгалтерии.")
        parser.add_argument("--db-backup-file", help="Уже сделанная полная копия базы (вместо pg_dump).")
        parser.add_argument("--json", help="Сохранить отчёт аудита в файл.")

    def handle(self, *args, **o):
        report = audit()
        self.print_audit(report)
        if o["json"]:
            Path(o["json"]).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            self.stdout.write(f"\nОтчёт аудита сохранён: {o['json']}")
        if not o["execute"]:
            self.stdout.write(self.style.WARNING(
                "\nЭто только аудит — ничего не удалено. Для сброса: --execute --actor <суперпользователь> "
                f"--backup-dir <каталог> --confirm \"{maintenance.CONFIRM_PHRASE}\" [--include-tariffs]"))
            return
        if os.environ.get("DJANGO_ENV") == "production" and not os.environ.get("ACCOUNTING_RESET_ALLOWED"):
            raise CommandError("Production: задайте ACCOUNTING_RESET_ALLOWED=1 на время сброса — защита от случайного запуска.")
        if o["confirm"] != maintenance.CONFIRM_PHRASE:
            raise CommandError(f"Нужно подтверждение: --confirm \"{maintenance.CONFIRM_PHRASE}\".")
        if report["external_references"]:
            raise CommandError("На бухгалтерию ссылаются другие модули — автоматический сброс остановлен: "
                               + "; ".join(report["external_references"]))
        actor = User.objects.filter(username=o["actor"] or "", is_superuser=True, is_active=True).first()
        if actor is None:
            raise CommandError("Укажите --actor — активного суперпользователя.")
        if not o["backup_dir"]:
            raise CommandError("Укажите --backup-dir: перед удалением делается копия базы и выгрузка бухгалтерии.")
        backup = self.backup(Path(o["backup_dir"]), o["db_backup_file"])
        try:
            deleted = maintenance.purge(maintenance.FULL, actor=actor, include_tariffs=o["include_tariffs"],
                                        reason=f"Полный сброс бухгалтерии (manage.py reset_accounting), копия: {backup}")
        except AccountingError as exc:
            raise CommandError(f"Сброс не выполнен, изменения отменены: {exc.message}")
        self.verify(report, deleted)

    # ------------------------------------------------------------------

    def print_audit(self, r: dict) -> None:
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(f"Аудит бухгалтерии — база {r['database']['engine']}: {r['database']['name']}"))
        w("\nБудет удалено (режим полного сброса):")
        for row in r["tables"]:
            if row["action"] == "delete":
                w(f"  {row['count']:>7}  {row['label']} [{row['db_table']}]" + (f" — {row['note']}" if row["note"] else ""))
        w(f"  {r['total_to_delete']:>7}  ИТОГО")
        w("\nТарифы (удаляются только с --include-tariffs):")
        for row in r["tables"]:
            if row["action"] == "tariffs":
                w(f"  {row['count']:>7}  {row['label']} [{row['db_table']}]")
        for p in r["tariffs"]["billing_plans"]:
            w(f"    тариф #{p['id']} «{p['name']}»: программа {p['course'] or '—'}, договоров {p['contracts']}, "
              f"версий {p['versions']}, {'действует' if p['active'] else 'отключён'}"
              f"{', DEMO' if p['demo'] else ''}, создал {p['created_by'] or '—'} {p['created_at'][:10]}")
        for v in r["tariffs"]["course_price_versions"]:
            w(f"    цена курса #{v['id']} «{v['course']}»: {v['price']} с {v['effective_from']}")
        w("\nСохраняется: настройки оплаты (BillingSettings), группы прав Accountant / BillingDirector, "
          "все данные других модулей:")
        others = r["kept"]["other_modules"]
        for label in ("academy.Student", "academy.Course", "academy.Group", "academy.GroupSchedule", "academy.Lesson",
                      "academy.Attendance", "users.User", "users.Teacher", "users.Subject"):
            if label in others:
                w(f"  {others[label]:>7}  {label}")
        w(f"  (всего моделей вне бухгалтерии под контролем: {len(others)})")
        refs = r["external_references"]
        w("\nСсылки других модулей на бухгалтерию: " + ("; ".join(refs) if refs else "нет — каскад на LMS невозможен"))
        if r["demo_registry"]:
            w(f"Реестр тестовых данных: {r['demo_registry']} — строки про удаляемые записи будут удалены, "
              "демо-студенты и демо-группы LMS останутся (их удаляет reset_billing_demo / seed_accounting_demo --clear).")

    def backup(self, folder: Path, db_backup_file: str | None) -> str:
        folder.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        db = settings.DATABASES["default"]
        if db_backup_file:
            path = Path(db_backup_file)
            if not path.exists() or path.stat().st_size == 0:
                raise CommandError(f"Копия базы {path} не найдена или пуста.")
            full = str(path)
        elif connection.vendor == "postgresql":
            if shutil.which("pg_dump") is None:
                raise CommandError("pg_dump не найден. Сделайте копию вручную (pg_dump -Fc) и передайте --db-backup-file.")
            full = str(folder / f"db-before-accounting-reset-{stamp}.dump")
            env = {**os.environ, "PGPASSWORD": str(db.get("PASSWORD") or "")}
            cmd = ["pg_dump", "-Fc", "-f", full, "-h", str(db.get("HOST") or "localhost"), "-p", str(db.get("PORT") or 5432),
                   "-U", str(db.get("USER") or "postgres"), str(db["NAME"])]
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if result.returncode != 0 or not Path(full).exists() or Path(full).stat().st_size == 0:
                raise CommandError(f"pg_dump не удался — сброс не выполнен: {result.stderr.strip()[:500]}")
        elif connection.vendor == "sqlite":
            full = str(folder / f"db-before-accounting-reset-{stamp}.sqlite3")
            shutil.copy2(db["NAME"], full)
        else:
            raise CommandError("Неизвестная СУБД — сделайте копию вручную и передайте --db-backup-file.")
        dump = folder / f"accounting-billing-{stamp}.json"
        with dump.open("w", encoding="utf-8") as fh:
            call_command("dumpdata", "accounting", "billing", natural_foreign=True, indent=1, stdout=fh)
        self.stdout.write(self.style.SUCCESS(f"\nКопия базы: {full}\nВыгрузка бухгалтерии: {dump}"))
        return full

    def verify(self, before: dict, deleted: dict) -> None:
        after = audit()
        left = {row["key"]: row["count"] for row in after["tables"] if row["action"] == "delete" and row["count"]}
        if left.get("payrollauditlog") == 1:
            left.pop("payrollauditlog")  # запись о самой операции сброса
        if left:
            raise CommandError(f"После сброса остались записи: {left}")
        changed = {k for k, v in after["kept"]["other_modules"].items() if before["kept"]["other_modules"].get(k) != v}
        if changed:
            raise CommandError(f"Изменились данные других модулей: {sorted(changed)}")
        if connection.vendor == "sqlite":
            connection.check_constraints()  # PostgreSQL проверяет внешние ключи сам
        self.stdout.write(self.style.SUCCESS("\nСброс выполнен. Удалено:"))
        for key, n in deleted.items():
            if n:
                self.stdout.write(f"  {n:>7}  {key}")
        self.stdout.write(f"  {sum(deleted.values()):>7}  ИТОГО")
        self.stdout.write("Данные других модулей не изменились; внешние ключи согласованы; в журнале аудита — "
                          "одна запись об операции.")
