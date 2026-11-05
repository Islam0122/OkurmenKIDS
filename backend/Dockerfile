FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system django \
    && adduser --system --ingroup django django

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Headless Chromium for the parent report PNGs (apps.reports, Playwright).
# Installed to a shared path so the unprivileged "django" user can run it;
# --with-deps pulls the system libraries and fonts Chromium needs.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install --with-deps chromium \
    && chmod -R a+rx /ms-playwright

COPY . .

RUN chown -R django:django /app

USER django

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]