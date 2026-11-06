"""Excel (.xlsx) exports with the matrix colours kept: one group's table and
the overview of many groups (a direction or the whole academy)."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FILLS = {
    "done": ("2F8F5B", "FFFFFF", "✓"),
    "partial": ("CFE7DA", "1F5F3C", "✓ без ДЗ"),
    "excused": ("F6D365", "6B4A00", "!"),
    "absent": ("E5533D", "FFFFFF", "✕"),
    "empty": ("EEF1EF", "89938D", "—"),
    "planned": ("FFFFFF", "B0B8B3", ""),
    "no_lesson": ("F7F9F7", "B0B8B3", "·"),
}
HW_MARK = {"done": "ДЗ ✓", "missed": "ДЗ ✕", "pending": "ДЗ …", "none": ""}
LEVEL_FILL = {"critical": "FBEAE7", "attention": "FBF1DF", "warning": "FFF8E1"}
LEVEL_LABEL = {"critical": "Критично", "attention": "Внимание", "warning": "Предупреждение"}

THIN = Side(style="thin", color="E1E7E2")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="E7F3EC")
TOTAL_FILL = PatternFill("solid", fgColor="E7F3EC")
BOLD = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def _pct(value) -> str:
    return "—" if value is None else f"{value}%"


def _head(ws, row: int, values: list) -> None:
    for col, value in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=value)
        cell.font = BOLD
        cell.fill = HEAD_FILL
        cell.alignment = CENTER
        cell.border = BORDER


def _save(wb: Workbook) -> bytes:
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def group_workbook(data: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Посещаемость"
    group, period, columns, rows, summary = data["group"], data["period"], data["columns"], data["rows"], data["summary"]

    ws.cell(row=1, column=1, value=f"{group['name']} — посещаемость и ДЗ").font = Font(bold=True, size=14)
    ws.cell(row=2, column=1, value=f"{group['course']} · {period['label']} · студентов: {len(rows)}")
    ws.cell(row=3, column=1, value=(
        f"Общая посещаемость: {_pct(summary['percent'])} · ДЗ сдано: {_pct(summary['hw_percent'])} · "
        f"пропусков: {summary['absent']} · уважительных: {summary['excused']} · несданных ДЗ: {summary['hw_missed']}"
    ))

    head_row = 5
    head = ["№", "Студент"] + [f"{c['weekday']}\n{c['date']:%d.%m}" for c in columns] + [
        "Прис.", "Уваж.", "Отс.", "Нет данных", "ДЗ сдано", "ДЗ не сдано", "%", "Предупреждения",
    ]
    _head(ws, head_row, head)
    ws.row_dimensions[head_row].height = 32

    for i, row in enumerate(rows, start=1):
        r = head_row + i
        ws.cell(row=r, column=1, value=i).border = BORDER
        name = ws.cell(row=r, column=2, value=row["student"]["name"])
        name.border = BORDER
        if row["level"]:
            name.fill = _fill(LEVEL_FILL[row["level"]])
        for j, cell in enumerate(row["cells"]):
            bg, fg, symbol = FILLS[cell["code"]]
            hw = HW_MARK.get(cell["homework"], "") if cell["code"] in ("done", "partial", "excused", "absent") else ""
            text = symbol if not hw or cell["code"] in ("done", "partial") else f"{symbol}\n{hw}"
            c = ws.cell(row=r, column=3 + j, value=text)
            c.fill = _fill(bg)
            c.font = Font(color=fg, bold=True)
            c.alignment = CENTER
            c.border = BORDER
        s = row["stats"]
        tail = [s["present"], s["excused"], s["absent"], s["unmarked"], s["hw_done"], s["hw_missed"], _pct(s["percent"]),
                "; ".join(w["label"] for w in row["warnings"])]
        for k, value in enumerate(tail):
            c = ws.cell(row=r, column=3 + len(columns) + k, value=value)
            c.border = BORDER
            c.alignment = CENTER if k < 7 else Alignment(vertical="center", wrap_text=True)

    total_row = head_row + len(rows) + 1
    ws.cell(row=total_row, column=2, value="Итого по группе").font = BOLD
    for j, col in enumerate(columns):
        ws.cell(row=total_row, column=3 + j, value=_pct(col["stats"]["percent"]) if col["stats"]["marked"] else "—")
    tail = [summary["present"], summary["excused"], summary["absent"], summary["unmarked"], summary["hw_done"],
            summary["hw_missed"], _pct(summary["percent"]), ""]
    for k, value in enumerate(tail):
        ws.cell(row=total_row, column=3 + len(columns) + k, value=value)
    for col in range(1, len(head) + 1):
        c = ws.cell(row=total_row, column=col)
        c.fill = TOTAL_FILL
        c.font = BOLD
        c.border = BORDER
        c.alignment = CENTER if col != 2 else Alignment(vertical="center")

    legend_row = total_row + 2
    ws.cell(row=legend_row, column=2, value="Обозначения").font = BOLD
    for i, item in enumerate(data["legend"], start=1):
        bg, fg, symbol = FILLS[item["code"]]
        c = ws.cell(row=legend_row + i, column=1, value=symbol)
        c.fill = _fill(bg)
        c.font = Font(color=fg, bold=True)
        c.alignment = CENTER
        c.border = BORDER
        ws.cell(row=legend_row + i, column=2, value=item["label"])

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 30
    for j in range(len(columns)):
        ws.column_dimensions[get_column_letter(3 + j)].width = 8
    for k in range(8):
        ws.column_dimensions[get_column_letter(3 + len(columns) + k)].width = 11 if k < 7 else 40
    ws.freeze_panes = ws.cell(row=head_row + 1, column=3)

    # Second sheet: the students ranked by attendance, with their status.
    _ranking_sheet(wb, rows)
    return _save(wb)


def _ranking_sheet(wb: Workbook, rows: list[dict]) -> None:
    ws = wb.create_sheet("Рейтинг")
    _head(ws, 1, ["Место", "Студент", "Посещаемость", "Присутствовал", "Пропусков", "Уважительных", "ДЗ сдано", "ДЗ %", "Статус"])
    ranked = sorted(rows, key=lambda r: (-(r["stats"]["percent"] or 0), r["stats"]["absent"], r["student"]["name"]))
    for i, row in enumerate(ranked, start=1):
        s = row["stats"]
        values = [i, row["student"]["name"], _pct(s["percent"]), s["present"], s["absent"], s["excused"], s["hw_done"],
                  _pct(s["hw_percent"]), LEVEL_LABEL.get(row["level"], "Норма")]
        for col, value in enumerate(values, start=1):
            c = ws.cell(row=i + 1, column=col, value=value)
            c.border = BORDER
            if col == 9 and row["level"]:
                c.fill = _fill(LEVEL_FILL[row["level"]])
    for col, width in zip("ABCDEFGHI", (8, 30, 14, 14, 12, 14, 10, 10, 16)):
        ws.column_dimensions[col].width = width


def overview_workbook(data: dict, title: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Группы"
    s = data["summary"]
    ws.cell(row=1, column=1, value=f"{title} — {data['period']['label']}").font = Font(bold=True, size=14)
    ws.cell(row=2, column=1, value=(
        f"Групп: {s['groups']} · студентов: {s['students']} · посещаемость: {_pct(s['percent'])} · "
        f"ДЗ: {_pct(s['hw_percent'])} · пропусков: {s['absent']} · несданных ДЗ: {s['hw_missed']}"
    ))
    _head(ws, 4, ["Группа", "Курс", "Тренеры", "Студентов", "Занятий", "Посещаемость", "ДЗ", "Прис.", "Уваж.", "Отс.",
                  "Нет данных", "ДЗ не сдано", "Критично", "Внимание"])
    for i, g in enumerate(data["groups"], start=5):
        values = [g["name"], g["course"], ", ".join(g["trainers"]), g["students"], g["lessons"], _pct(g["percent"]),
                  _pct(g["hw_percent"]), g["present"], g["excused"], g["absent"], g["unmarked"], g["hw_missed"],
                  g["warnings"]["critical"], g["warnings"]["attention"]]
        for col, value in enumerate(values, start=1):
            c = ws.cell(row=i, column=col, value=value)
            c.border = BORDER
        percent = g["percent"]
        if percent is not None:
            color = "CFE7DA" if percent >= 85 else ("FBF1DF" if percent >= 70 else "FBEAE7")
            ws.cell(row=i, column=6).fill = _fill(color)
    for col, width in zip("ABCDEFGHIJKLMN", (22, 20, 30, 10, 10, 14, 10, 8, 8, 8, 11, 12, 10, 10)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "B5"

    tr = wb.create_sheet("Тренеры")
    _head(tr, 1, ["Тренер", "Группы", "Занятий", "Посещаемость", "ДЗ", "Заполнено отметок", "Пропусков"])
    for i, t in enumerate(data["trainers"], start=2):
        values = [t["name"], ", ".join(t["groups"]), t["lessons"], _pct(t["percent"]), _pct(t["hw_percent"]),
                  _pct(t["fill_rate"]), t["absent"]]
        for col, value in enumerate(values, start=1):
            tr.cell(row=i, column=col, value=value).border = BORDER
    for col, width in zip("ABCDEFG", (26, 34, 10, 14, 10, 18, 10)):
        tr.column_dimensions[col].width = width

    ps = wb.create_sheet("Проблемные студенты")
    _head(ps, 1, ["Студент", "Группа", "Статус", "Пропусков", "Подряд", "ДЗ не сдано", "Посещаемость", "Причины"])
    for i, p in enumerate(data["problem_students"], start=2):
        st = p["stats"]
        values = [p["student"]["name"], p["group"]["name"], LEVEL_LABEL[p["level"]], st["absent"], st["consecutive_absences"],
                  st["hw_missed"], _pct(st["percent"]), "; ".join(w["label"] for w in p["warnings"])]
        for col, value in enumerate(values, start=1):
            c = ps.cell(row=i, column=col, value=value)
            c.border = BORDER
        ps.cell(row=i, column=3).fill = _fill(LEVEL_FILL[p["level"]])
    for col, width in zip("ABCDEFGH", (28, 20, 16, 10, 10, 12, 14, 50)):
        ps.column_dimensions[col].width = width

    dyn = wb.create_sheet("Динамика")
    _head(dyn, 1, ["Месяц", "Посещаемость", "Отметок", "Пропусков"])
    for i, m in enumerate(data["trend"], start=2):
        for col, value in enumerate([m["label"], _pct(m["percent"]), m["marked"], m["absent"]], start=1):
            dyn.cell(row=i, column=col, value=value).border = BORDER
    dyn.column_dimensions["A"].width = 14
    return _save(wb)
