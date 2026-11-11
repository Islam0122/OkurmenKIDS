"""Safe reading of an uploaded XLSX / CSV file into sheets of rows.

Protections: extension and magic-byte check, size limit, zip-bomb check for
XLSX (total uncompressed size and entry count), macro workbooks refused,
formulas read as their cached values only (never evaluated), row / column /
cell-length limits. Cells are plain strings; nothing in a file is executed or
fetched (image URLs are kept as text).
"""
from __future__ import annotations

import csv
import io
import zipfile

from openpyxl import load_workbook

from apps.users.import_export.formats import _cell_to_str

from .schema import SHEET_ALIASES, TYPES

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024
MAX_ZIP_ENTRIES = 400
MAX_ROWS_PER_SHEET = 1000
MAX_COLUMNS = 80
MAX_CELL_CHARS = 20_000


class FileRejected(Exception):
    """The file itself is unacceptable (format, size, structure)."""


def _check_size(uploaded) -> None:
    size = getattr(uploaded, "size", None)
    if size is None:
        uploaded.seek(0, io.SEEK_END)
        size = uploaded.tell()
        uploaded.seek(0)
    if not size:
        raise FileRejected("Файл пустой.")
    if size > MAX_FILE_BYTES:
        raise FileRejected(f"Файл больше {MAX_FILE_BYTES // (1024 * 1024)} МБ.")


def kind_from_sheet(name: str) -> str | None:
    key = (name or "").strip().casefold()
    return next((kind for kind, names in SHEET_ALIASES.items() if key in names), None)


def kind_from_filename(name: str) -> str | None:
    lower = (name or "").casefold()
    return next((kind for kind in TYPES if kind in lower or any(alias in lower for alias in SHEET_ALIASES[kind])), None)


def _cell(value) -> str:
    text = _cell_to_str(value)
    return text[:MAX_CELL_CHARS + 1]


def _rows(iterable) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    rows_iter = iter(iterable)
    try:
        header = [(_cell(c) if c is not None else "") for c in next(rows_iter)]
    except StopIteration:
        return [], []
    if len(header) > MAX_COLUMNS:
        raise FileRejected(f"Слишком много колонок (больше {MAX_COLUMNS}).")
    out = []
    for number, raw in enumerate(rows_iter, start=2):
        if raw is None or not any(c not in (None, "") for c in raw):
            continue
        if len(out) >= MAX_ROWS_PER_SHEET:
            raise FileRejected(f"На одном листе больше {MAX_ROWS_PER_SHEET} строк — разделите файл.")
        out.append((number, {h: (_cell(raw[i]) if i < len(raw) else "") for i, h in enumerate(header) if h}))
    return header, out


def read_xlsx(uploaded) -> dict[str, tuple[list[str], list[tuple[int, dict[str, str]]]]]:
    head = uploaded.read(4)
    uploaded.seek(0)
    if head[:2] != b"PK":
        raise FileRejected("Это не файл Excel (.xlsx).")
    try:
        with zipfile.ZipFile(uploaded) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES or sum(e.file_size for e in entries) > MAX_UNCOMPRESSED_BYTES:
                raise FileRejected("Файл Excel слишком большой после распаковки.")
            if any(e.filename.lower().endswith("vbaproject.bin") for e in entries):
                raise FileRejected("Файлы с макросами не принимаются.")
    except zipfile.BadZipFile:
        raise FileRejected("Файл Excel повреждён.")
    uploaded.seek(0)
    try:
        workbook = load_workbook(uploaded, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 — any parser error is a bad file
        raise FileRejected("Не удалось прочитать файл Excel.")
    sheets: dict[str, tuple[list[str], list[tuple[int, dict[str, str]]]]] = {}
    try:
        for ws in workbook.worksheets:
            kind = kind_from_sheet(ws.title)
            if kind and kind not in sheets:
                sheets[kind] = _rows(ws.iter_rows(values_only=True))
    finally:
        workbook.close()
    if not sheets:
        raise FileRejected("В файле нет листов Events / Achievements / News (или Мероприятия / Достижения / Новости).")
    return sheets


def read_csv(uploaded, kind: str) -> dict[str, tuple[list[str], list[tuple[int, dict[str, str]]]]]:
    raw = uploaded.read()
    if b"\x00" in raw[:4096]:
        raise FileRejected("Это не текстовый CSV-файл.")
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise FileRejected("Не удалось определить кодировку CSV (сохраните в UTF-8).")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return {kind: _rows(csv.reader(io.StringIO(text), dialect))}


def read_upload(uploaded, *, csv_kind: str | None = None):
    """{kind: (header, [(row_number, {header: value})])}"""
    name = (getattr(uploaded, "name", "") or "").lower()
    _check_size(uploaded)
    uploaded.seek(0)
    if name.endswith(".xlsx"):
        return read_xlsx(uploaded)
    if name.endswith(".csv"):
        kind = csv_kind or kind_from_filename(name)
        if kind not in TYPES:
            raise FileRejected("Для CSV выберите тип контента: мероприятия, достижения или новости.")
        return read_csv(uploaded, kind)
    raise FileRejected("Поддерживаются только .xlsx и .csv.")
