"""Permissions for the news app.

News has no roles of its own — it reuses the Teacher-facing permission
already defined in apps.users. Kept as a re-export so news.views never has
to reach into another app's permissions module directly.
"""
from __future__ import annotations

from apps.users.permissions import IsTeacher  # noqa: F401
