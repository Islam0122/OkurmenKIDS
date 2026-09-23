# Media files (uploads) in production

Uploaded files — currently `Teacher.image` (`upload_to="teachers/"`) — are
stored on the local filesystem under `MEDIA_ROOT` and served under
`MEDIA_URL` (`/media/`).

| Environment | Who serves `/media/` |
|---|---|
| development (`DEBUG=True`) | `django.conf.urls.static.static()` |
| production (`DEBUG=False`, `SERVE_MEDIA=True`) | `django.views.static.serve` (see `config/urls.py`) |
| production with `SERVE_MEDIA=False` | nothing in Django — use external storage/CDN |

WhiteNoise only serves collected static files (`STATIC_ROOT`), never
uploads.

## Settings (`config/settings/production.py`)

| Env var | Default | Meaning |
|---|---|---|
| `MEDIA_ROOT` | `/app/media` | Where uploads are written. Must be a persistent volume. |
| `SERVE_MEDIA` | `True` | Let Django serve `MEDIA_URL`. Set `False` once media moves to R2/S3. |

`serve()` only resolves paths inside `MEDIA_ROOT`: `..`, absolute paths and
directory listings are rejected (400/404).

## Railway Volume

The container filesystem is recreated on every deploy, so without a volume
every uploaded photo disappears on redeploy (the database keeps the file
name, the URL then returns 404).

1. Service → **Settings → Volumes → Add Volume**.
2. **Mount path: `/app/media`** (the image's `WORKDIR` is `/app`, so this is
   exactly the default `MEDIA_ROOT`). If you mount it elsewhere, set
   `MEDIA_ROOT` to the same path.
3. Service → **Variables**: add `RAILWAY_RUN_UID=0`. Railway mounts the
   volume owned by root, while the image runs as the unprivileged `django`
   user, which cannot write to it. With this variable the container starts
   as root, `deployment/server-entrypoint.sh` does `chown` on `MEDIA_ROOT`
   and immediately re-runs itself as `django` — migrations and gunicorn
   still never run as root.
4. Redeploy.

Limitations of a volume: it is attached to a single service instance (no
horizontal replicas), and deploys of a service with a volume have a short
downtime while the volume is re-attached.

Files uploaded *before* the volume existed were lost on earlier redeploys and
cannot be recovered; re-upload those photos. To list teachers whose photo
file is missing:

```bash
python manage.py shell -c "import os; from apps.users.models import Teacher; print([t.pk for t in Teacher.objects.exclude(image='') if not os.path.exists(t.image.path)])"
```

## Moving to R2/S3 later

Switching `STORAGES["default"]` to `storages.backends.s3.S3Storage` needs:

- `apps/academy/services/monthly_report_pdf.py` — `teacher.image.path` is
  filesystem-only; read through `teacher.image.open("rb")` instead.
- `SERVE_MEDIA=False` (URLs then come from the storage backend).
- Copy the existing volume contents to the bucket with the same keys
  (`teachers/<file>`), so database values stay valid.
