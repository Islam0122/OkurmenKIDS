"""What a student may not publish: contact details and links.

Children must not be reachable through the community. Texts (posts and
comments) are refused — with the reason, so the student can fix it — when
they contain a phone number, an e-mail, a messenger / social network contact
or handle, or a web link. A project link is allowed only in its own field
and only to a site where student projects live (PROJECT_HOSTS).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

PROJECT_HOSTS = (
    "github.com", "gitlab.com", "github.io", "replit.com", "repl.co", "codepen.io", "codesandbox.io",
    "scratch.mit.edu", "figma.com", "vercel.app", "netlify.app", "glitch.me", "stackblitz.com",
    "okurmenkids.com", "canva.com", "tinkercad.com", "itch.io", "pages.dev", "onrender.com",
)

_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s\-().]*){9,}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.UNICODE)
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|ru|kg|org|net|io|me|app|dev|site|xyz|online|info)\b(?:/\S*)?",
                  re.IGNORECASE)
_HANDLE = re.compile(r"(?<![\w.])@[A-Za-z0-9_.]{3,}")
_CONTACT_WORDS = re.compile(
    r"\b(telegram|телеграм|телега|tg|whats\s?app|ватсап|вотсап|insta(?:gram)?|инст(?:а|аграм)|tiktok|тикток|"
    r"vk\.com|вконтакте|snapchat|discord|дискорд|imo|viber|вайбер|facebook|фейсбук)\b",
    re.IGNORECASE,
)
_ADDRESS = re.compile(r"\b(?:ул\.|улица|көчө|мкр\.?|микрорайон|кв\.|квартира|дом\s+№?\s*\d+)\s*\S+", re.IGNORECASE)

MESSAGES = {
    "phone": "Без номеров телефонов — личные контакты в сообществе не публикуются.",
    "email": "Без адресов электронной почты.",
    "link": "Без ссылок в тексте. Ссылку на свой проект добавьте в поле «Ссылка на проект».",
    "handle": "Без никнеймов и аккаунтов в соцсетях.",
    "messenger": "Без контактов в мессенджерах и соцсетях.",
    "address": "Без домашнего адреса.",
}


def problems(text: str) -> list[str]:
    """Codes of what is not allowed in `text` (empty = fine)."""
    text = text or ""
    found = []
    if _PHONE.search(text):
        found.append("phone")
    if _EMAIL.search(text):
        found.append("email")
    if _URL.search(_EMAIL.sub(" ", text)):
        found.append("link")
    if _HANDLE.search(_EMAIL.sub(" ", text)):
        found.append("handle")
    if _CONTACT_WORDS.search(text):
        found.append("messenger")
    if _ADDRESS.search(text):
        found.append("address")
    return found


def explain(codes: list[str]) -> str:
    return " ".join(MESSAGES[code] for code in codes)


def project_url_problem(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return "Ссылка на проект должна начинаться с https://"
    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in PROJECT_HOSTS):
        return "Ссылка на проект — только на сайты для проектов: GitHub, Replit, Scratch, CodePen, Figma, Vercel, Netlify…"
    return None
