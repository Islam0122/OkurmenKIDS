"""PDF-отчёты бухгалтерии (reportlab platypus). Шрифты DejaVu — те же, что
у остальных PDF проекта (встроенные шрифты reportlab без кириллицы)."""
from __future__ import annotations

import datetime as dt
import io
from xml.sax.saxutils import escape
from decimal import ROUND_HALF_UP, Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.academy.services.monthly_report_pdf import (
    BORDER,
    BRAND,
    BRAND_SOFT,
    INK,
    INK_SECONDARY,
    _BOLD,
    _REGULAR,
    _ensure_fonts,
)

from .money import plain
from .report_service import IndividualReport, PayrollReport

_NBSP = " "


def som(value) -> str:
    if value is None:
        return "—"
    amount = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, _, frac = f"{abs(amount):,.2f}".partition(".")
    sign = "−" if amount < 0 else ""
    return f"{sign}{whole.replace(',', _NBSP)},{frac}{_NBSP}сом"


def _styles():
    _ensure_fonts()
    return {
        "title": ParagraphStyle("t", fontName=_BOLD, fontSize=15, leading=19, textColor=INK, spaceAfter=4),
        "sub": ParagraphStyle("s", fontName=_REGULAR, fontSize=9, leading=12, textColor=INK_SECONDARY),
        "h": ParagraphStyle("h", fontName=_BOLD, fontSize=10.5, leading=14, textColor=INK, spaceBefore=8, spaceAfter=4),
        "cell": ParagraphStyle("c", fontName=_REGULAR, fontSize=8, leading=10, textColor=INK),
        "cell_b": ParagraphStyle("cb", fontName=_BOLD, fontSize=8, leading=10, textColor=INK),
    }


def _table(head, rows, widths, *, total_row=None, styles):
    data = [[Paragraph(h, styles["cell_b"]) for h in head]]
    for row in rows:
        data.append([Paragraph(escape(str(v)), styles["cell"]) for v in row])
    if total_row:
        data.append([Paragraph(escape(str(v)), styles["cell_b"]) for v in total_row])
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_SOFT),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if total_row:
        style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f4f7f5")))
    table.setStyle(TableStyle(style))
    return table


def _footer(generated_at):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(_REGULAR, 7.5)
        canvas.setFillColor(INK_SECONDARY)
        canvas.drawString(doc.leftMargin, 10 * mm, f"OkurmenKIDS · бухгалтерия · сформировано {generated_at:%d.%m.%Y %H:%M}")
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 10 * mm, f"стр. {doc.page}")
        canvas.setStrokeColor(BRAND)
        canvas.line(doc.leftMargin, doc.pagesize[1] - 12 * mm, doc.pagesize[0] - doc.rightMargin, doc.pagesize[1] - 12 * mm)
        canvas.restoreState()
    return draw


def render_period_pdf(report: PayrollReport) -> bytes:
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=report.title)
    t = report.totals
    story = [
        Paragraph(report.title, styles["title"]),
        Paragraph(f"Период: {report.range_label} · Валюта: KGS · Дата формирования: {report.generated_at:%d.%m.%Y %H:%M}", styles["sub"]),
        Spacer(1, 6),
        _table(
            ["Начислено", "Корректировки", "Итого к выплате", "Выплачено", "Задолженность", "Сотрудников"],
            [[som(t.accrued), som(t.adjustments), som(t.total), som(t.paid), som(t.due), len(report.rows)]],
            [44 * mm] * 6, styles=styles,
        ),
        Paragraph("Сотрудники", styles["h"]),
        _table(
            ["Сотрудник", "Должность", "Тип оплаты", "Период", "Начислено", "Корр.", "Выплачено", "Остаток", "Статус"],
            [[r.employee, r.position, r.salary_type, r.period, som(r.accrued), som(r.adjustments), som(r.paid),
              som(r.due), r.status] for r in report.rows],
            [40 * mm, 26 * mm, 30 * mm, 38 * mm, 27 * mm, 22 * mm, 27 * mm, 27 * mm, 28 * mm],
            total_row=["Итого", "", "", "", som(t.accrued), som(t.adjustments), som(t.paid), som(t.due), ""],
            styles=styles,
        ),
    ]
    if report.by_program:
        story += [
            Paragraph("Итоги по программам (начисления, привязанные к группам)", styles["h"]),
            _table(["Программа", "Сумма"], [[name, som(v)] for name, v in report.by_program], [120 * mm, 40 * mm],
                   styles=styles),
            Paragraph("Итоги по группам", styles["h"]),
            _table(["Группа", "Программа", "Сумма"], [[g, c, som(v)] for g, c, v in report.by_group],
                   [70 * mm, 70 * mm, 40 * mm], styles=styles),
        ]
    doc.build(story, onFirstPage=_footer(report.generated_at), onLaterPages=_footer(report.generated_at))
    return buf.getvalue()


def render_individual_pdf(report: IndividualReport) -> bytes:
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=f"Расчётный лист — {report.employee}")
    story = [
        Paragraph("Расчётный лист", styles["title"]),
        Paragraph(
            f"{escape(report.employee)} · {escape(report.position or '—')} · {report.salary_type or '—'}<br/>"
            f"Период: {report.period} · Статус: {report.payroll.get_status_display()} · "
            f"Дата формирования: {report.generated_at:%d.%m.%Y %H:%M}",
            styles["sub"],
        ),
        Paragraph("Начисления", styles["h"]),
        _table(
            ["Начисление", "Кол-во", "Ставка", "%", "База", "Сумма"],
            [[l.description, plain(l.quantity) if l.quantity is not None else "—", som(l.rate) if l.rate is not None else "—",
              plain(l.percentage) if l.percentage is not None else "—",
              som(l.base_amount) if l.base_amount is not None else "—", som(l.amount)] for l in report.lines],
            [66 * mm, 14 * mm, 30 * mm, 10 * mm, 30 * mm, 32 * mm],
            total_row=["Начислено", "", "", "", "", som(report.accrued)], styles=styles,
        ),
    ]
    if report.adjustments:
        story += [
            Paragraph("Корректировки", styles["h"]),
            _table(["Тип", "Причина", "Сумма"], [[a.get_kind_display(), a.reason, som(a.amount)] for a in report.adjustments],
                   [36 * mm, 110 * mm, 36 * mm], total_row=["Итого", "", som(report.adjustments_total)], styles=styles),
        ]
    story += [
        Paragraph("Выплаты", styles["h"]),
        _table(
            ["Дата", "Способ", "Документ", "Сумма"],
            [[f"{p.payment_date:%d.%m.%Y}", p.get_payment_method_display() + (" (аванс)" if p.is_advance else ""),
              p.reference or "—", som(p.amount)] for p in report.payments] or [["—", "", "", ""]],
            [30 * mm, 60 * mm, 56 * mm, 36 * mm], total_row=["Выплачено", "", "", som(report.paid)], styles=styles,
        ),
        Spacer(1, 8),
        _table(
            ["Начислено", "Корректировки", "Выплачено", "Остаток к выплате"],
            [[som(report.accrued), som(report.adjustments_total), som(report.paid), som(report.due)]],
            [45.5 * mm] * 4, styles=styles,
        ),
    ]
    doc.build(story, onFirstPage=_footer(report.generated_at), onLaterPages=_footer(report.generated_at))
    return buf.getvalue()


def render_my_salary_pdf(data: dict, generated_at) -> bytes:
    """Личный отчёт «Моя зарплата» — те же данные, что видит сотрудник на странице."""
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title=f"Моя зарплата — {data['employee_name']}")
    profile = data["profile"]
    rates = "; ".join(
        (f"{plain(r['percentage'])}%" if r["percentage"] else som(r["amount"])) + (f" ({r['scope']})" if r["scope"] else "")
        for r in (profile or {}).get("rates", [])
    ) or "—"
    f = data["filters"]
    scope = ", ".join(x for x in (
        f"год {f['year']}" if f.get("year") else "", f"месяц {f['month']:02d}" if f.get("month") else "",
        {"FIRST_HALF": "1–15", "SECOND_HALF": "16–конец месяца"}.get(f.get("period_type") or "", ""),
    ) if x) or "все периоды"
    t = data["totals"]
    story = [
        Paragraph("Моя зарплата", styles["title"]),
        Paragraph(
            f"{escape(data['employee_name'])} · {escape((profile or {}).get('position') or '—')}<br/>"
            f"Тип оплаты: {escape((profile or {}).get('salary_type_display') or 'не настроен')} · ставка: {escape(rates)}<br/>"
            f"История: {scope} · Дата формирования: {generated_at:%d.%m.%Y %H:%M}",
            styles["sub"],
        ),
        Spacer(1, 6),
        _table(["Начислено (утверждено)", "Выплачено", "Остаток к выплате", "Ожидает утверждения"],
               [[som(t["accrued"]), som(t["paid"]), som(t["due"]), som(t["pending_approval"])]],
               [45.5 * mm] * 4, styles=styles),
        Paragraph("История начислений", styles["h"]),
        _table(
            ["Период", "Статус", "Начислено", "Выплачено", "Остаток"],
            [[r["period_label"], r["status_display"], som(r["accrued"]), som(r["paid"]), som(r["due"])]
             for r in data["history"]] or [["Начислений пока нет", "", "", "", ""]],
            [40 * mm, 52 * mm, 30 * mm, 30 * mm, 30 * mm], styles=styles,
        ),
        Paragraph("Выплаты", styles["h"]),
        _table(
            ["Дата", "Период", "Способ", "Сумма"],
            [[f"{dt.date.fromisoformat(p['payment_date']):%d.%m.%Y}", p["period_label"],
              p["method"] + (" (аванс)" if p["is_advance"] else ""), som(p["amount"])] for p in data["payments"]]
            or [["Выплат пока нет", "", "", ""]],
            [30 * mm, 50 * mm, 62 * mm, 40 * mm], styles=styles,
        ),
    ]
    doc.build(story, onFirstPage=_footer(generated_at), onLaterPages=_footer(generated_at))
    return buf.getvalue()


def render_teacher_report_pdf(report: dict) -> bytes:
    styles = _styles()
    buf = io.BytesIO()
    generated = report["generated_at"]
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title="Отчёт по сотрудникам")
    t = report["totals"]

    def d(value):
        return f"{value:%d.%m.%Y}" if value else "—"

    def num(value):
        return "—" if value is None else plain(value)

    rows = []
    for p in report["payrolls"]:
        for line in p["lines"]:
            rows.append([p["employee_name"], p["department_display"], line["group_name"] or "—", p["period_label"],
                         p["salary_type_display"], num(line["students"]),
                         som(line["price_per_student"]) if line["price_per_student"] is not None else "—",
                         f"{num(line['percentage'])}%" if line["percentage"] is not None else "—",
                         f"{num(line['lessons_done'])}/{num(line['target_lessons'])}" if line["lessons_done"] else "—",
                         som(line["accrued"]), "", "", d(p["planned_payment_date"]), p["status_display"]])
        rows.append([f"Итого: {p['employee_name']}", "", "", "", "", "", "", "", "", som(p["total"]), som(p["paid"]),
                     som(p["due"]), d(p["planned_payment_date"]), p["status_display"]])
    story = [
        Paragraph("Отчёт по сотрудникам", styles["title"]),
        Paragraph(f"Месяц: {report['range_label']} · Валюта: KGS · Дата формирования: {generated:%d.%m.%Y %H:%M}<br/>"
                  f"{escape(report['note'])}", styles["sub"]),
        Spacer(1, 6),
        _table(["Начислено", "Выплачено", "Остаток", "Расчётов"],
               [[som(t["total"]), som(t["paid"]), som(t["due"]), len(report["payrolls"])]], [50 * mm] * 4,
               styles=styles),
        Paragraph("Сотрудники", styles["h"]),
        _table(
            ["Сотрудник", "Направл.", "Группа", "Период", "Тип оплаты", "Учен.", "Цена", "%", "Уроки",
             "Начислено", "Выплачено", "Остаток", "План. выплата", "Статус"],
            rows or [["Начислений нет"] + [""] * 13],
            [34 * mm, 18 * mm, 22 * mm, 30 * mm, 24 * mm, 11 * mm, 20 * mm, 10 * mm, 13 * mm, 22 * mm, 22 * mm,
             22 * mm, 18 * mm, 21 * mm],
            total_row=["Итого", "", "", "", "", "", "", "", "", som(t["total"]), som(t["paid"]), som(t["due"]), "", ""],
            styles=styles,
        ),
        Paragraph("Итоги по направлениям", styles["h"]),
        _table(["Направление", "Начислено", "Выплачено", "Остаток"],
               [[r["label"], som(r["accrued"]), som(r["paid"]), som(r["due"])] for r in report["by_department"]]
               or [["—", "", "", ""]],
               [70 * mm, 40 * mm, 40 * mm, 40 * mm],
               total_row=["Итого", som(t["total"]), som(t["paid"]), som(t["due"])], styles=styles),
    ]
    doc.build(story, onFirstPage=_footer(generated), onLaterPages=_footer(generated))
    return buf.getvalue()
