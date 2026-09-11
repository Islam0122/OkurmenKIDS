"""Danger zone: wipes the DEVELOPMENT/TESTING database and re-applies migrations.

Hard-refuses to run whenever DJANGO_ENV=production, independent of any flag
the caller passes — there is no override. This mirrors the same DJANGO_ENV
switch `config/settings/__init__.py` uses to pick development/testing/
production settings, so "which environment am I in" is answered exactly the
same way here as everywhere else in the project.
"""
from __future__ import annotations

import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = (
        "Destroys ALL data in the currently configured database and re-applies "
        "migrations from scratch. Development/testing only — refuses to run "
        "when DJANGO_ENV=production. Requires --confirm."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required. Acknowledges this destroys all data in the configured database.",
        )

    def handle(self, *args, **options):
        env = os.environ.get("DJANGO_ENV", "development")

        if env == "production":
            raise CommandError(
                "Refusing to run: DJANGO_ENV=production. reset_dev_db never touches "
                "a production database, no flag can override this."
            )

        db = connection.settings_dict
        db_name = db.get("NAME")

        if not options["confirm"]:
            raise CommandError(
                f"This destroys ALL data in database '{db_name}' (DJANGO_ENV={env}). "
                "Re-run with --confirm to proceed."
            )

        self.stdout.write(self.style.WARNING(
            f"Resetting database '{db_name}' (engine={db['ENGINE']}, DJANGO_ENV={env})..."
        ))

        if db["ENGINE"] == "django.db.backends.sqlite3":
            connection.close()
            if db_name != ":memory:" and os.path.exists(db_name):
                os.remove(db_name)
                self.stdout.write(f"Deleted SQLite file: {db_name}")
            else:
                self.stdout.write("No SQLite file to delete (already absent or in-memory).")
        else:
            self.stdout.write(
                "Non-SQLite engine detected — flushing all tables instead of dropping the database."
            )
            call_command("flush", interactive=False)

        self.stdout.write("Applying migrations...")
        call_command("migrate", interactive=False)

        self.stdout.write(self.style.SUCCESS(
            "Development database reset complete. Run `seed_dev_data` for demo data, "
            "or `createsuperuser` for a bare admin account."
        ))
