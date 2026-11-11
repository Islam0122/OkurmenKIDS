"""Downloadable templates: an XLSX workbook (README + Events + Achievements +
News, with drop-down lists for category and status) and one CSV per type.
They contain headers only — no sample records that could be imported by
mistake."""
from __future__ import annotations

import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .schema import COLUMNS, TYPE_LABEL, TYPES, choices_for

SHEET = {"events": "Events", "achievements": "Achievements", "news": "News"}
STATUSES = {"events": "draft,review,archived", "achievements": "draft,review,archived", "news": "draft"}
HEAD = PatternFill("solid", fgColor="29136D")


def xlsx_template() -> bytes:
    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    lines = [
        ("Okurmen Kids — массовое заполнение контента", True),
        ("Заполните листы Events, Achievements, News (один или несколько). Одна строка — одна запись.", False),
        ("Все импортированные записи остаются неопубликованными: публикация — вручную после проверки.", False),
        ("Не придумывайте даты, награды, победителей, места и участников: оставьте ячейку пустой и опишите, "
         "что нужно уточнить, в колонке «verification_note».", False),
        ("Изображения не загружаются из файла: укажите ссылку или имя файла в «cover», а саму обложку "
         "добавьте в редакторе.", False),
        ("Языки: _ru — русский (обязателен заголовок), _ky — кыргызский (KG), _en — английский.", False),
        ("Даты: ГГГГ-ММ-ДД или ДД.ММ.ГГГГ; время — ЧЧ:ММ. Можно использовать ячейки формата «дата».", False),
        ("", False),
    ]
    for text, bold in lines:
        readme.append([text])
        if bold:
            readme.cell(readme.max_row, 1).font = Font(bold=True, size=14)
    for kind in TYPES:
        readme.append([])
        readme.append([f"Лист {SHEET[kind]} — {TYPE_LABEL[kind]}"])
        readme.cell(readme.max_row, 1).font = Font(bold=True, size=12)
        readme.append(["Колонка", "Название", "Обязательно", "Описание", "Допустимые значения"])
        for cell in readme[readme.max_row]:
            cell.font = Font(bold=True)
        for col in COLUMNS[kind]:
            readme.append([col.key, col.label, "да" if col.required else "", col.help, col.example_values])
        readme.append(["", "Категории:", "", "; ".join(f"{v} — {label}" for v, label in choices_for(kind))])
    for letter, width in zip("ABCDE", (24, 32, 12, 80, 50)):
        readme.column_dimensions[letter].width = width
    for row in readme.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    for kind in TYPES:
        ws = wb.create_sheet(SHEET[kind])
        columns = COLUMNS[kind]
        ws.append([c.key for c in columns])
        for i, col in enumerate(columns, start=1):
            cell = ws.cell(1, i)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = HEAD
            ws.column_dimensions[get_column_letter(i)].width = 40 if col.key.startswith("body") else 22
        ws.freeze_panes = "A2"
        keys = [c.key for c in columns]
        lists = {"category": ",".join(v for v, _ in choices_for(kind)), "status": STATUSES[kind]}
        if kind == "events":
            lists["registration_enabled"] = "да,нет"
        for key, options in lists.items():
            letter = get_column_letter(keys.index(key) + 1)
            dv = DataValidation(type="list", formula1=f'"{options}"', allow_blank=True)
            dv.error = "Выберите значение из списка"
            ws.add_data_validation(dv)
            dv.add(f"{letter}2:{letter}1000")
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def csv_template(kind: str) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer).writerow([c.key for c in COLUMNS[kind]])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _safe(value) -> str:
    """No spreadsheet formula injection in the error report."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def error_report_csv(batch) -> bytes:
    """Every row with errors / warnings / its import result."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Лист", "Строка", "Название", "Результат", "Ошибки", "Предупреждения", "Сообщение импорта",
                     "Заметка для проверки"])
    results = batch.report.get("rows", {})
    for row in batch.rows:
        result = results.get(row["key"], {})
        if not (row["errors"] or row["warnings"] or result.get("result") in ("failed", "skipped")):
            continue
        writer.writerow([_safe(x) for x in (
            SHEET[row["kind"]], row["row"], row["title"],
            {"created": "создано", "updated": "обновлено", "skipped": "пропущено", "failed": "ошибка"}.get(
                result.get("result", ""), "не выбрано" if batch.finished_at else ""),
            " | ".join(e["message"] for e in row["errors"]),
            " | ".join(w["message"] for w in row["warnings"]),
            result.get("message", ""),
            row.get("verification_note", ""),
        )])
    return ("﻿" + buffer.getvalue()).encode("utf-8")
