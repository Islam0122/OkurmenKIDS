"""The one place that defines what counts as scholarship DEMO data.

Nothing in the LMS models has an "is_demo" flag, so every row this
generator creates carries an explicit, collision-proof marker in a natural
field, and `--clear` deletes only rows that carry it:

* Groups / Courses:  name starts with ``SCH-DEMO-``
* Teacher accounts:  username starts with ``schdemo_`` AND email ends with
                     ``@scholarship-demo.invalid`` (both must match; the
                     ``.invalid`` TLD is reserved and can never be a real
                     address — RFC 2606)
* Students:          phone starts with ``+000-SCHDEMO-`` (+000 is not a
                     valid country code, so no real phone number can match)
* Scholarship periods: ``generated_by`` is the demo admin account
                     (``schdemo_admin`` / ``@scholarship-demo.invalid``)

Subjects are shared catalogue data and are reused/created by name but never
deleted (same rule as the project's existing clear_demo_data command).
"""
from __future__ import annotations

from django.db.models import Q

PREFIX = "SCH-DEMO-"
USERNAME_PREFIX = "schdemo_"
EMAIL_DOMAIN = "@scholarship-demo.invalid"
PHONE_PREFIX = "+000-SCHDEMO-"
ADMIN_USERNAME = "schdemo_admin"


def demo_user_q() -> Q:
    return Q(username__startswith=USERNAME_PREFIX) & Q(email__endswith=EMAIL_DOMAIN)


def demo_student_q(prefix: str = "") -> Q:
    return Q(**{f"{prefix}phone__startswith": PHONE_PREFIX})


def demo_group_q(prefix: str = "") -> Q:
    return Q(**{f"{prefix}name__startswith": PREFIX})


def student_phone(key: str) -> str:
    return f"{PHONE_PREFIX}{key}"
