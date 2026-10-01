"""Search / sort / paginate report rows — shared by the admin pages and
the API, so `?q=...&sort=-kpi&page=2` means the same thing in both.

Rows are already fully aggregated (one per group/teacher), so this works
on the small in-memory list instead of issuing more queries.
"""
from __future__ import annotations

import dataclasses
import math

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200

GROUP_SORTS = {
    "name": lambda r: r["name"].lower(),
    "program": lambda r: r["program"].lower(),
    "teacher": lambda r: r["teacher_names"].lower(),
    "total": lambda r: r["students"]["total"],
    "active": lambda r: r["students"]["active"],
    "left": lambda r: r["students"]["left"],
    "attendance": lambda r: r["attendance_rate"],
    "homework": lambda r: r["homework_rate"],
    "activity": lambda r: r["activity_rate"],
    "progress": lambda r: r["progress_rate"],
    "kpi": lambda r: r["kpi"],
}
GROUP_SEARCH = ("name", "program", "teacher_names")

TEACHER_SORTS = {
    "name": lambda r: r["name"].lower(),
    "groups": lambda r: r["groups_count"],
    "students": lambda r: r["students"]["total"],
    "active": lambda r: r["students"]["active"],
    "left": lambda r: r["students"]["left"],
    "attendance": lambda r: r["attendance_rate"],
    "homework": lambda r: r["homework_rate"],
    "activity": lambda r: r["activity_rate"],
    "progress": lambda r: r["progress_rate"],
    "kpi": lambda r: r["kpi"],
}


SUBJECT_SORTS = {
    "name": lambda r: r["name"].lower(),
    "teachers": lambda r: r["teachers_count"],
    "groups": lambda r: r["groups_count"],
    "students": lambda r: r["students"]["total"],
    "attendance": lambda r: r["attendance_rate"],
    "homework": lambda r: r["homework_rate"],
    "activity": lambda r: r["activity_rate"],
    "progress": lambda r: r["progress_rate"],
    "kpi": lambda r: r["kpi"],
}


def _subject_search_text(row) -> str:
    return " ".join([row["name"], *(t["name"] for t in row["teachers"]), *(g["name"] for g in row["groups"])])


def _teacher_search_text(row) -> str:
    return " ".join([row["name"], *row["subjects"], *(g["name"] for g in row["groups"])])


@dataclasses.dataclass
class TablePage:
    rows: list
    total: int
    page: int
    pages: int
    page_size: int
    query: str
    sort: str

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def start_index(self) -> int:
        return (self.page - 1) * self.page_size + 1 if self.total else 0

    @property
    def end_index(self) -> int:
        return min(self.page * self.page_size, self.total)

    def as_dict(self) -> dict:
        return {
            "count": self.total,
            "page": self.page,
            "pages": self.pages,
            "page_size": self.page_size,
            "search": self.query,
            "sort": self.sort,
            "results": self.rows,
        }


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def paginate_rows(rows: list, params, *, sorts: dict, default_sort: str, search) -> TablePage:
    query = (params.get("q") or params.get("search") or "").strip()
    if query:
        needle = query.lower()
        rows = [row for row in rows if needle in search(row).lower()]

    sort = (params.get("sort") or default_sort).strip()
    key = sort.lstrip("-")
    if key not in sorts:
        sort, key = default_sort, default_sort.lstrip("-")
    descending = sort.startswith("-")
    getter = sorts[key]
    # Rows without data ("—") always sink to the bottom, in either direction.
    with_value = [row for row in rows if getter(row) is not None]
    without_value = [row for row in rows if getter(row) is None]
    rows = sorted(with_value, key=getter, reverse=descending) + without_value

    page_size = min(max(_int(params.get("page_size"), DEFAULT_PAGE_SIZE), 1), MAX_PAGE_SIZE)
    total = len(rows)
    pages = max(math.ceil(total / page_size), 1)
    page = min(max(_int(params.get("page"), 1), 1), pages)
    start = (page - 1) * page_size
    return TablePage(rows=rows[start:start + page_size], total=total, page=page, pages=pages,
                     page_size=page_size, query=query, sort=sort)


def paginate_groups(rows, params) -> TablePage:
    status = (params.get("status") or "").strip()
    if status:
        rows = [row for row in rows if row["status"] == status]
    return paginate_rows(rows, params, sorts=GROUP_SORTS, default_sort="name",
                         search=lambda r: " ".join(r[f] for f in GROUP_SEARCH))


def paginate_teachers(rows, params) -> TablePage:
    return paginate_rows(rows, params, sorts=TEACHER_SORTS, default_sort="name", search=_teacher_search_text)


def paginate_subjects(rows, params) -> TablePage:
    return paginate_rows(rows, params, sorts=SUBJECT_SORTS, default_sort="name", search=_subject_search_text)


STUDENT_SORTS = {
    "name": lambda r: r["name"].lower(),
    # Active students first, then by name — the roster's natural order.
    "status": lambda r: (not r["is_active"], r["name"].lower()),
    "attendance": lambda r: r["attendance_rate"],
    "homework": lambda r: r["homework_rate"],
    "progress": lambda r: r["progress_rate"],
}


def paginate_students(rows, params) -> TablePage:
    return paginate_rows(rows, params, sorts=STUDENT_SORTS, default_sort="status",
                         search=lambda r: f"{r['name']} {r['group']}")
