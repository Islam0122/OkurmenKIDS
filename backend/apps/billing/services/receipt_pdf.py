"""PDF чека Okurmen Kids (reportlab, шрифты DejaVu — кириллица).

Логотип — настоящий логотип академии из репозитория
(`static/images/logo.png`, тот же файл, что во фронтенде). Два формата:
A4 и компактный (ширина 80 мм — чековый принтер). Данные — только из чека
(снимок на момент операции): печать не создаёт ни платежа, ни нового чека.
Документ — внутренний чек академии, не фискальный.
"""
from __future__ import annotations

import io
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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

from ..models import BillingSettings, Receipt

LOGO = Path(settings.BASE_DIR) / "static" / "images" / "logo.png"
NBSP = " "


def som(value) -> str:
    if value in (None, ""):
        return "—"
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, _, frac = f"{abs(amount):,.2f}".partition(".")
    sign = "−" if amount < 0 else ""
    return f"{sign}{whole.replace(',', NBSP)},{frac}{NBSP}сом"


def receipt_rows(receipt: Receipt) -> list[tuple[str, str]]:
    """Строки чека (общие для PDF и HTML-страницы)."""
    snap = receipt.snapshot or {}
    refund = receipt.kind == Receipt.Kind.REFUND
    rows = [
        ("Студент", snap.get("student") or ""),
        ("Программа", snap.get("program") or ""),
        ("Группа", snap.get("group") or ""),
    ]
    if snap.get("payer") or receipt.payer_name:
        rows.append(("Плательщик", receipt.payer_name or snap.get("payer")))
    rows.append(("Назначение", "; ".join(snap.get("purpose_lines") or []) or snap.get("purpose") or ""))
    rows.append(("Сумма возврата" if refund else "Сумма платежа", som(snap.get("amount"))))
    if snap.get("received_date"):
        day = snap["received_date"].split("-")
        rows.append(("Дата возврата" if refund else "Дата получения денег", ".".join(reversed(day))))
    if not snap.get("backfilled"):
        rows += [
            ("Уплачено ранее", som(snap.get("previously_paid"))),
            ("Остаток долга по договору", som(snap.get("outstanding"))),
        ]
        if snap.get("credit") and Decimal(snap["credit"]) > 0:
            rows.append(("Доступный аванс", som(snap.get("credit"))))
    rows += [
        ("Способ оплаты", snap.get("method_display") or snap.get("method") or ""),
        ("Принял(а)", snap.get("staff") or ""),
        ("Статус операции", "Проведена" if receipt.status == Receipt.Status.ISSUED else "Отменена (сторно), чек аннулирован"),
    ]
    return rows


def render_receipt_pdf(receipt: Receipt, *, compact: bool = False) -> bytes:
    _ensure_fonts()
    cfg = BillingSettings.load()
    buf = io.BytesIO()
    width = 80 * mm if compact else A4[0]
    margin = 5 * mm if compact else 18 * mm
    rows = receipt_rows(receipt)
    height = (75 + 8 * len(rows)) * mm if compact else A4[1]
    doc = SimpleDocTemplate(buf, pagesize=(width, height), leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin, title=f"Чек {receipt.number}",
                            author=cfg.academy_name)
    scale = 0.82 if compact else 1
    st = {
        "brand": ParagraphStyle("b", fontName=_BOLD, fontSize=16 * scale, leading=20 * scale, textColor=INK),
        "sub": ParagraphStyle("s", fontName=_REGULAR, fontSize=8.5 * scale, leading=11 * scale, textColor=INK_SECONDARY),
        "title": ParagraphStyle("t", fontName=_BOLD, fontSize=12 * scale, leading=15 * scale, textColor=INK),
        "k": ParagraphStyle("k", fontName=_REGULAR, fontSize=9 * scale, leading=12 * scale, textColor=INK_SECONDARY),
        "v": ParagraphStyle("v", fontName=_BOLD, fontSize=9 * scale, leading=12 * scale, textColor=INK),
        "amount": ParagraphStyle("a", fontName=_BOLD, fontSize=18 * scale, leading=22 * scale, textColor=BRAND),
        "foot": ParagraphStyle("f", fontName=_REGULAR, fontSize=7.5 * scale, leading=10 * scale,
                               textColor=INK_SECONDARY),
    }
    inner = width - 2 * margin
    logo_size = (12 if compact else 18) * mm
    head_text = [Paragraph(escape(cfg.academy_name), st["brand"])]
    if cfg.academy_details:
        head_text.append(Paragraph(escape(cfg.academy_details).replace("\n", "<br/>"), st["sub"]))
    logo = Image(str(LOGO), width=logo_size, height=logo_size * 213 / 236) if LOGO.exists() else ""
    head = Table([[logo, head_text]], colWidths=[logo_size + 3 * mm, inner - logo_size - 3 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    kind = "Чек возврата" if receipt.kind == Receipt.Kind.REFUND else "Чек об оплате"
    issued = timezone.localtime(receipt.issued_at)
    story = [
        head, Spacer(1, 4 * mm),
        Paragraph(f"{kind} № {escape(receipt.number or '')}", st["title"]),
        Paragraph(f"{issued:%d.%m.%Y %H:%M}", st["sub"]),
        Spacer(1, 3 * mm),
        Paragraph(som(receipt.snapshot.get("amount")), st["amount"]),
        Spacer(1, 3 * mm),
    ]
    key_w = inner * (0.42 if compact else 0.36)
    table = Table(
        [[Paragraph(escape(k), st["k"]), Paragraph(escape(str(v)), st["v"])] for k, v in rows],
        colWidths=[key_w, inner - key_w],
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(table)
    if receipt.status == Receipt.Status.CANCELLED:
        story += [Spacer(1, 3 * mm), Paragraph(
            f"ЧЕК АННУЛИРОВАН: {escape(receipt.cancel_reason or 'операция отменена')}",
            ParagraphStyle("x", parent=st["v"], backColor=BRAND_SOFT),
        )]
    story += [
        Spacer(1, 5 * mm),
        Paragraph(escape(cfg.receipt_footer or ""), st["foot"]),
        Paragraph("Внутренний документ академии об оплате обучения. Не является фискальным чеком.", st["foot"]),
    ]
    doc.build(story)
    return buf.getvalue()
