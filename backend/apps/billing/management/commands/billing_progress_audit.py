"""Сверка учебного месяца и уроков IT академии и бухгалтерии — только чтение.

    python manage.py billing_progress_audit --plan "Next 3"
    python manage.py billing_progress_audit --student Суеркулов
    python manage.py billing_progress_audit --group PRO-03 --json report.json

По каждому договору: проведённые уроки предмета в группе (академия), засчитанные
уроки и строка «Все студенты» (бухгалтерия), месяц по правилу «12 уроков на
месяц», деньги (стадия, к оплате, просрочка, аванс, начисления по месяцам) и
коды расхождений с объяснением. Ничего не меняет."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.billing.services.progress_audit import progress_audit


class Command(BaseCommand):
    help = "Сверка учебного прогресса академии и бухгалтерии (только чтение)."

    def add_arguments(self, parser):
        parser.add_argument("--student", help="Часть имени / фамилии.")
        parser.add_argument("--group", help="Часть названия группы.")
        parser.add_argument("--plan", help="Часть названия тарифа (например, Next 3).")
        parser.add_argument("--profile", type=int)
        parser.add_argument("--json", help="Сохранить полный отчёт в файл.")

    def handle(self, *args, **o):
        report = progress_audit(student=o["student"], group=o["group"], plan=o["plan"], profile_id=o["profile"])
        if o["json"]:
            Path(o["json"]).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        w = self.stdout.write
        w(f"Договоров: {report['total']}, с расхождениями: {report['with_findings']} {report['by_finding']}")
        for r in report["rows"]:
            a, b, rule, m = r["academy"], r["billing"], r["rule"], r["money"]
            w(f"\n{r['student']} · {r['group']} · {r['plan']} · договор с {r['contract_start']} · {r['absence_policy']}")
            w(f"  академия: проведено {r['subject']} {a['held_all_time']} (с начала договора {a['held_since_contract']})"
              f" из плана {a['course_plan']}")
            w(f"  бухгалтерия: засчитано {b['counted']} · показано «{b['shown']}» · не засчитаны: {b['excluded'] or '—'}")
            w(f"  по правилу: {rule['shown']} · курс {rule['course_progress']}")
            w(f"  деньги: {m['stage']} · к оплате {m['due_now']} (просрочено {m['overdue']}, срок сегодня "
              f"{m['due_today']}, срок не наступил {m['not_due']}) · аванс {m['credit']}"
              f" (не распределён {m['credit_unapplied']}) · получено {m['received']}, распределено {m['allocated']}")
            w("  начисления:")
            for i in m["invoices"]:
                due = f"{i['due_lesson']}-й урок (в месяце {i['month_lessons_used']})" if i["due_lesson"] else i["due_date"]
                w(f"    {i['number']} {'весь курс' if i['kind'] == 'COURSE' else 'месяц ' + str(i['month'])}: "
                  f"период {i['period_date']}, создано {i['created_at'][:10]}, {i['amount']}, оплачено {i['paid']}, "
                  f"остаток {i['balance']}, {i['status']}, срок {due}")
            w("  платежи:")
            for p in m["payments"] or [{"id": None}]:
                if p["id"] is None:
                    w("    —")
                    continue
                parts = "; ".join(f"{a['invoice']} {a['amount']} ({a['status']})" for a in p["allocations"]) or "—"
                w(f"    №{p['id']} {p['kind']} {p['status']} {p['amount']} от {p['received_date']} (внесён "
                  f"{p['created_at'][:10]}), чек {p['receipt'] or '—'}, назначение {p['purpose'] or '—'} · "
                  f"распределения: {parts} · не распределено {p['unallocated'] or '—'}")
            for f in r["findings"]:
                w(f"  ! {f['code']}: {f['detail']}")
