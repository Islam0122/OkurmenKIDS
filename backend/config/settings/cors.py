import os

CORS_ALLOWED_ORIGINS = [
    "https://okurmen-kids-drab.vercel.app",
    "https://training-portal-theta.vercel.app",
    # The public training portal (training-portal/, React): its deployed
    # origin(s), comma-separated, e.g. https://train.okurmen.kg
    *[o.strip().rstrip("/") for o in os.getenv("TRAINING_PORTAL_ORIGINS", "https://training-portal-theta.vercel.app/").split(",") if o.strip()],
]

CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    # Public training API: the signed token of the student's own attempt.
    "x-attempt-token",
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://127\.0\.0\.1(:\d+)?$",
    r"^http://localhost(:\d+)?$",
]