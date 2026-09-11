"""One-time production bootstrap: migrate + guidance for creating the first admin.

Deliberately does *not* create any user itself and does *not* accept a
password on the command line (which would land in shell history / process
list / CI logs). It only runs migrations — which are additive and safe to
re-run — and prints the exact next manual step. No demo/seed data is ever
created here; see `seed_dev_data` for that, which itself refuses to run in
production.
"""
from __future__ import annotations

import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = (
        "Production bootstrap: applies migrations and prints the steps to create "
        "the first admin account. Never seeds demo data, never touches an "
        "existing database destructively, never prints or accepts a password."
    )

    def handle(self, *args, **options):
        env = os.environ.get("DJANGO_ENV", "development")
        if env != "production":
            raise CommandError(
                f"init_production is meant to run with DJANGO_ENV=production, "
                f"but DJANGO_ENV={env!r}. Use `reset_dev_db` / `seed_dev_data` for "
                "development instead."
            )

        db = connection.settings_dict
        self.stdout.write(self.style.WARNING(
            f"Initializing production database '{db.get('NAME')}' (engine={db['ENGINE']})..."
        ))
        self.stdout.write(
            "This only applies migrations. It never drops, flushes, or seeds data."
        )

        call_command("migrate", interactive=False)

        self.stdout.write(self.style.SUCCESS("Migrations applied."))
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Next step (run manually, interactively):"))
        self.stdout.write("  python manage.py createsuperuser")
        self.stdout.write(
            "This project's User manager (apps.users.models.CustomUserManager) "
            "automatically marks a superuser created this way as role=ADMIN and "
            "is_verified=True — no extra setup is needed for that first account."
        )
        self.stdout.write("")
        self.stdout.write(
            "No demo/seed data is created in production. Add teachers/courses/groups "
            "through the admin UI once logged in."
        )
