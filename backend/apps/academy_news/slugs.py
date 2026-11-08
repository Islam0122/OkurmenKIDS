"""Latin URL slugs for Russian / Kyrgyz titles («Наш хакатон» → «nash-hakaton»)."""
from __future__ import annotations

from django.utils.text import slugify

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "ң": "ng", "о": "o", "ө": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ү": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
MAX_LENGTH = 200


def transliterate(text: str) -> str:
    return "".join(_TRANSLIT.get(char, _TRANSLIT.get(char.lower(), char)) for char in text)


def unique_slug(model, title: str, exclude_pk=None) -> str:
    base = slugify(transliterate(title or ""))[:MAX_LENGTH].strip("-") or "news"
    slug, number = base, 2
    others = model.objects.exclude(pk=exclude_pk) if exclude_pk else model.objects.all()
    while others.filter(slug=slug).exists():
        slug = f"{base[:MAX_LENGTH - 6]}-{number}"
        number += 1
    return slug
