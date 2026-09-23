#!/bin/sh
set -e

# Railway mounts a Volume owned by root, but the image runs as the
# unprivileged "django" user (see Dockerfile), which then cannot write
# uploads to MEDIA_ROOT. When the container is started as root
# (RAILWAY_RUN_UID=0), hand the media directory to "django" and re-run this
# script as that user — migrations and gunicorn never run as root.
# Started as "django" (the image default), this block is skipped.
if [ "$(id -u)" = "0" ]; then
    MEDIA_DIR="${MEDIA_ROOT:-/app/media}"
    mkdir -p "$MEDIA_DIR"
    chown -R django:django "$MEDIA_DIR"
    exec python -c 'import os, pwd, sys; u = pwd.getpwnam("django"); os.setgroups([]); os.setgid(u.pw_gid); os.setuid(u.pw_uid); os.environ["HOME"] = u.pw_dir; os.execvp(sys.argv[1], sys.argv[1:])' sh "$0" "$@"
fi

python manage.py collectstatic --noinput
python manage.py migrate --noinput

python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'admin@example.com', 'admin')"

exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}