"""The site's safe content markup and small helpers.

`body` fields are plain text — no HTML is ever stored or rendered. The public
website renders this markup (src/features/content/RichText.tsx):

    ## Heading / ### Subheading
    - list item            1. numbered item
    > quote
    **bold**  *italic*  [link text](https://…)
    ![caption](https://…image…)      — an image on its own line
    https://youtu.be/…                — a YouTube / Vimeo link on its own line = video
    ---                               — divider
    :::note … :::                     — highlighted block

Blank line = new paragraph. The marketing editor in the LMS has a toolbar
for every element, so nobody has to type the markup by hand.
"""
from __future__ import annotations

import re

_YOUTUBE = re.compile(
    r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
_VIMEO = re.compile(r"^https?://(?:www\.|player\.)?vimeo\.com/(?:video/)?(\d{6,12})")


def video_embed(url: str) -> str | None:
    """The embed URL of a YouTube / Vimeo link, else None."""
    url = (url or "").strip()
    if match := _YOUTUBE.match(url):
        return f"https://www.youtube-nocookie.com/embed/{match.group(1)}"
    if match := _VIMEO.match(url):
        return f"https://player.vimeo.com/video/{match.group(1)}"
    return None


def phone_digits(phone: str) -> str:
    """Digits only, Kyrgyz local numbers normalised to 996… (0555 123456 → 996555123456)."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10 and digits.startswith("0"):
        digits = "996" + digits[1:]
    elif len(digits) == 9:
        digits = "996" + digits
    return digits[:20]


def lines(text: str) -> list[str]:
    """Non-empty lines without list markers («- », «• », «1. »)."""
    result = []
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s+", "", line).strip()
        if line:
            result.append(line)
    return result
