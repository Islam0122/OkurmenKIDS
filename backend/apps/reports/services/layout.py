"""Page layout of the group report image: how many student rows fit a page.

Every block of the 1600×1100 page has a fixed height in the template
(templates/reports/_styles.html — keep the two in sync), so the number of
rows per page is plain arithmetic. A large group gets more pages instead of
smaller text: the text size never changes with the group size.
"""
from __future__ import annotations

import dataclasses

PAGE_WIDTH = 1600
PAGE_HEIGHT = 1100

PAD_Y = 40           # .page top/bottom padding
HEADER = 88          # .header
HEADER_COMPACT = 64  # .header.compact (continuation pages)
GAP = 20             # vertical gap between blocks
KPI = 116            # .kpis
TABLE_HEAD = 40      # thead row
ROW = 40             # tbody row
SECTIONS = 250       # .sections — the most they may need (3 long statements per card)
SECTIONS_MIN = 150
SECTIONS_MAX = 320   # a section card never grows taller than this
FOOTER = 24          # .footer

INNER = PAGE_HEIGHT - 2 * PAD_Y
SAFETY = 8           # px of slack against sub-pixel rounding


@dataclasses.dataclass
class Page:
    number: int
    first: bool
    students: list[dict]
    show_kpis: bool
    show_sections: bool
    row_offset: int


# Section card text metrics (templates/reports/_styles.html: .section li / .section.dense li).
_CARD_CHROME = 34 + 37   # padding + border, title row + its margin
_ITEM_GAP = 8
_TEXT = {False: (50, 20), True: (54, 18)}  # dense → (characters per line, line height px)


def sections_height(sections: list[dict] | None) -> int:
    """Height the three section cards need for their text — estimated from
    the text length, rounded up generously; the render checks for overflow."""
    if not sections:
        return 0
    needed = []
    for section in sections:
        per_line, line_height = _TEXT[bool(section.get("dense"))]
        lines = [max(1, -(-len(text) // per_line)) for text in section["items"]]
        needed.append(_CARD_CHROME + sum(lines) * line_height + _ITEM_GAP * max(0, len(lines) - 1) + 12)
    return max(SECTIONS_MIN, min(SECTIONS, max(needed)))


def _capacity(*, first: bool, kpis: bool, sections: bool, sections_px: int = SECTIONS) -> int:
    # header → … → footer: one GAP after the header and one before the footer.
    used = (HEADER if first else HEADER_COMPACT) + GAP + GAP + FOOTER
    if first and kpis:
        used += KPI + GAP
    used += TABLE_HEAD
    if sections:
        used += GAP + sections_px
    return max(1, (INNER - used - SAFETY) // ROW)


def paginate(
    students: list[dict], *, table: bool, kpis: bool, sections: bool, sections_px: int = SECTIONS,
) -> list[Page]:
    """Fill pages in order. The table is never split when it fits one page:
    if the rows fit but the bottom sections do not, the sections get a page
    of their own instead of the rows being spread thin over two pages."""
    if not table or not students:
        return [Page(1, True, [], kpis, sections, 0)]

    pages: list[Page] = []
    remaining = list(students)
    offset = 0
    while remaining:
        first = not pages
        with_sections = _capacity(first=first, kpis=kpis and first, sections=sections, sections_px=sections_px)
        without_sections = _capacity(first=first, kpis=kpis and first, sections=False)
        if len(remaining) <= with_sections:
            pages.append(Page(len(pages) + 1, first, remaining, kpis and first, sections, offset))
            return pages
        take = min(len(remaining), without_sections)
        pages.append(Page(len(pages) + 1, first, remaining[:take], kpis and first, False, offset))
        remaining, offset = remaining[take:], offset + take
    if sections:
        # Every row is placed; the sections did not fit next to the last rows.
        pages.append(Page(len(pages) + 1, False, [], False, True, offset))
    return pages
