import os

ENV = os.getenv("DJANGO_ENV", "development")

match ENV:
    case "production":
        from .production import *
    case "testing":
        from .testing import *
    case _:
        from .development import *