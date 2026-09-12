"""Tiny helpers shared by every adapter's ``validate_row`` — not business
logic itself (that stays per-adapter, since it's genuinely different per
model), just the plumbing every one of them needs.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator


def flatten_validation_error(exc: DjangoValidationError) -> list[str]:
    """Turn a Django ValidationError (field-keyed or flat) into row messages."""
    message_dict = getattr(exc, "message_dict", None)
    if message_dict:
        out: list[str] = []
        for field, messages in message_dict.items():
            prefix = "" if field == "__all__" else f"{field}: "
            out.extend(f"{prefix}{message}" for message in messages)
        return out
    return list(exc.messages)


def parse_int(raw: str, *, field_label: str, min_value: int | None = None) -> tuple[int | None, str | None]:
    """Parse a required integer cell. Returns (value, error_message)."""
    try:
        value = int(raw)
    except ValueError:
        return None, f"«{field_label}» должно быть целым числом, получено «{raw}»."
    if min_value is not None and value < min_value:
        return None, f"«{field_label}» должно быть не меньше {min_value}."
    return value, None


_url_validator = URLValidator()


def parse_url_list(raw: str, *, field_label: str, separator: str = ";") -> tuple[list[str], list[str]]:
    """Parse a ``;``-separated list of URLs. Returns (urls, error_messages)."""
    urls = [part.strip() for part in raw.split(separator) if part.strip()]
    errors: list[str] = []
    for url in urls:
        try:
            _url_validator(url)
        except DjangoValidationError:
            errors.append(f"«{field_label}» содержит некорректную ссылку: «{url}».")
    return urls, errors
