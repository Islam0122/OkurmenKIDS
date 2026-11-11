from config.settings.development import *  # noqa  (локальная PostgreSQL для демо-стенда)
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": "localhost", "USER": "postgres", "PASSWORD": "postgres", "NAME": "okurmen", "PORT": 5432}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
