"""Celery проекта. Сейчас используется оплатой обучения (apps.billing.tasks).

Воркер и Beat:
    celery -A config worker -l info
    celery -A config beat -l info

Без брокера (`CELERY_BROKER_URL` пуст) задачи выполняются синхронно в
процессе вызова — для хостинга без Redis есть `manage.py billing_autorun`.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("okurmenkids")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
