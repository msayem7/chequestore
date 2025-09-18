FROM python:3.10.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install build deps, install python deps, then remove build deps
COPY requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev libpq-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y --auto-remove gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy project
COPY . .

# Create non-root user and set permissions
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

# Collect static at build time only if STATIC settings don't require DB.
RUN python manage.py collectstatic --noinput || true

EXPOSE 8080

ENTRYPOINT ["gunicorn", "--bind", "0.0.0.0:8000", "src.wsgi:application", \
           "--workers", "3", "--timeout", "120"]