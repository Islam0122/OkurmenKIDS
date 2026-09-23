#!/bin/sh
set -e

# Railway mounts a Volume owned by root, but the image runs as the
# unprivileged "django" user (see Dockerfile), which then cannot write
# uploads to MEDIA_ROOT. When the container is started as root
# (RAILWAY_RUN_UID=0), hand the media directory to "django" and re-run this
# script as that user — migrations and gunicorn never run as root.
# Started as "django" (the image default), this block is skipped.
MEDIA_DIR="${MEDIA_ROOT:-/app/media}"
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$MEDIA_DIR"
    chown -R django:django "$MEDIA_DIR"
    exec python -c 'import os, pwd, sys; u = pwd.getpwnam("django"); os.setgroups([]); os.setgid(u.pw_gid); os.setuid(u.pw_uid); os.environ["HOME"] = u.pw_dir; os.execvp(sys.argv[1], sys.argv[1:])' sh "$0" "$@"
fi

# Without RAILWAY_RUN_UID=0 the block above is skipped and a root-owned
# Volume stays read-only for "django": every photo upload then fails with
# PermissionError (HTTP 500). Say so at boot instead of only at upload time.
if [ ! -d "$MEDIA_DIR" ]; then
    echo "WARNING: MEDIA_ROOT $MEDIA_DIR does not exist — is the Railway Volume mounted there?" >&2
elif [ ! -w "$MEDIA_DIR" ]; then
    echo "ERROR: MEDIA_ROOT $MEDIA_DIR is not writable by user $(id -un) (uid $(id -u))." >&2
    echo "ERROR: uploads will fail with PermissionError. Set RAILWAY_RUN_UID=0 in Railway Variables and redeploy." >&2
fi

python manage.py collectstatic --noinput
python manage.py migrate --noinput

python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'admin@example.com', 'admin')"

# Gunicorn >= 25.1 opens a control socket (for `gunicornc`) under
# $XDG_RUNTIME_DIR or $HOME/.gunicorn/. The "django" system user's HOME is
# /nonexistent, so that fails with "Control server error: Permission denied"
# on every boot. gunicornc is not used on Railway — disable the socket.
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --no-control-socket