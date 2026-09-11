# Database: reset, seed, and production initialization

This project selects its settings module (and therefore its database) from
the `DJANGO_ENV` environment variable — `development` (default), `testing`,
or `production` (see `config/settings/__init__.py`). Every command below
reads that same variable and refuses to run outside the environment it's
meant for. There is no flag that overrides this.

| `DJANGO_ENV` | Database (see `config/settings/<env>.py`) |
|---|---|
| `development` (default) | SQLite file `backend/db.sqlite3` |
| `testing` | In-memory SQLite, created and destroyed per test run |
| `production` | PostgreSQL, configured via `PGHOST`/`PGUSER`/`PGDATABASE`/`PGPASSWORD`/`PGPORT` |

## Local development

Standard first-time setup:

```bash
cd backend
python manage.py migrate
python manage.py seed_dev_data   # optional — creates demo teachers/course/group/students
python manage.py createsuperuser # optional — if you'd rather not use the seeded demo admin
```

**Wiping and starting over** (destroys every row in your local dev database,
never touches anything else):

```bash
python manage.py reset_dev_db --confirm
python manage.py seed_dev_data
```

`reset_dev_db`:
- Refuses immediately if `DJANGO_ENV=production` — no flag can override this.
- Refuses without `--confirm`, even in development.
- For SQLite (the default local setup): deletes the `.sqlite3` file, then re-applies every migration from scratch.
- For a non-SQLite dev database: runs `flush` (truncates every table) instead of deleting a file, then re-applies migrations.

`seed_dev_data`:
- Refuses immediately if `DJANGO_ENV=production` (checked *before* any database connection is opened — see "Safety checks" below).
- Idempotent: re-running it reuses existing rows (matched by username/name) instead of duplicating them.
- Creates: one admin (`demo_admin`), two teachers (`demo.teacher1`, `demo.teacher2`) each running their own independent Teaching Program (`GroupTeacher`) in the same demo group — one using the shared course-wide lesson plan, the other its own individual lesson plan — five demo students, and the lessons generated from both.
- Every created object is named with a `[DEMO]` prefix or a `demo.`/`demo_` username, and the command prints a `=== DEVELOPMENT DEMO DATA ===` banner every time it runs.
- Prints the demo login credentials at the end (fixed dev-only password, never usable against production — the guard above makes that structurally impossible, not just a convention).

## Staging

Staging should be treated exactly like production for the purposes of this
document: run with `DJANGO_ENV=production` pointed at the staging database,
back up before any migration (below), and never run `seed_dev_data` or
`reset_dev_db` against it — both refuse to run in that environment anyway.
If staging genuinely needs demo/sample data, add it deliberately through the
admin UI, the same way you would in production, rather than reusing the dev
seed command.

## Production initialization (first deploy)

```bash
DJANGO_ENV=production python manage.py init_production
```

This:
- Refuses to run unless `DJANGO_ENV=production` (it's a production-only command — use the dev commands above for local work).
- Only applies migrations. It never drops, flushes, or seeds any data, and never creates a user itself.
- Prints the one manual next step:

```bash
DJANGO_ENV=production python manage.py createsuperuser
```

`apps.users.models.CustomUserManager` automatically marks a superuser created
this way as `role=ADMIN` and `is_verified=True` — no further setup is needed
for that first account. Run `createsuperuser` interactively (never pass
`--noinput` with a password on the command line, and never script a
production password into CI logs, shell history, or a Dockerfile).

No demo/seed data is ever created in production. Add real teachers, courses,
and groups through the admin UI once logged in.

## Backup requirements

Before **any** migration against a production or staging database — not just
a reset (which those environments' guards prevent you from running by
mistake, but a schema migration can still land there deliberately as part of
a normal deploy):

```bash
# Run on/against the database host, not from this repo — adjust for your
# actual hosting (Railway, RDS, a managed Postgres provider, etc).
pg_dump --format=custom --file="backup-$(date +%Y%m%d-%H%M%S).dump" \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" "$PGDATABASE"
```

Store the dump somewhere outside the database host itself before proceeding
(object storage, a backup service, or simply off-box). Confirm the dump file
is non-empty and its size is in the expected ballpark for your data volume
before trusting it as a rollback point.

## Rollback guidance

- **Migration rollback**: `python manage.py migrate <app_label> <previous_migration_name>` reverses a specific migration if it's a clean `reverse_code`-capable one. Always test the reverse migration against a copy of production data (e.g., a staging restore) before running it against production — not every migration this project writes is guaranteed reversible (check for `RunPython` steps with no `reverse_code`).
- **Data rollback**: restore the pre-migration `pg_dump` above:
  ```bash
  pg_restore --clean --if-exists --format=custom \
    --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
    --dbname="$PGDATABASE" backup-<timestamp>.dump
  ```
- Always take the backup above *before* running a migration you're not fully confident in, rather than relying on `migrate <app> <previous>` alone — some migrations (data backfills especially) aren't cleanly invertible even when Django lets you attempt it.

## Environment safety checks (what actually enforces all of the above)

- `reset_dev_db` and `seed_dev_data` both read `os.environ["DJANGO_ENV"]` directly (the same variable `config/settings/__init__.py` uses to choose the settings module) and raise `CommandError` immediately if it's `"production"` — before doing anything else.
- `seed_dev_data`'s guard runs *before* entering its `@transaction.atomic` block, deliberately — entering a transaction is what actually opens a real connection to the configured `DATABASES` host, so checking the environment first means a misconfigured `DJANGO_ENV=production` never even dials out to the production database, let alone writes to it.
- `reset_dev_db` additionally requires an explicit `--confirm` flag, independent of the environment check, so an accidental bare invocation in development still can't wipe your local data unattended.
- `init_production` is the mirror image: it refuses to run *unless* `DJANGO_ENV=production`, so it can't accidentally be used as a dev shortcut, and it never accepts or prints a password.
- All three guards are covered by automated tests: `apps/users/tests.py::ResetDevDbGuardTests`, `apps/users/tests.py::InitProductionGuardTests`, `apps/academy/tests.py::SeedDevDataTests`.
