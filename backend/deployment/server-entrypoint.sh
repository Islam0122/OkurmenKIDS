#!/bin/sh
set -e

. .venv/bin/activate

python manage.py collectstatic --noinput
python manage.py migrate --noinput

python manage.py shell -c "from django.contrib.auth.models import User; User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'admin@example.com', 'admin')"

gunicorn config.wsgi:application --bind 0.0.0.0:$PORT