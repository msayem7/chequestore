# ...existing code...
FROM python:3.10.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
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

# Collect static
RUN python manage.py collectstatic --noinput

EXPOSE 8080

# production command: consistent port, set workers/timeouts as needed
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "src.wsgi:application", "--workers", "3", "--timeout", "120"]
# ...existing code...





# ---------------- First Version ----------------
# FROM python:3.10-slim-bookworm

# # Rest remains the same as before
# ENV PYTHONDONTWRITEBYTECODE 1
# ENV PYTHONUNBUFFERED 1
# WORKDIR /app

# # Install system deps + PostgreSQL support
# RUN apt-get update && \
#     apt-get install -y --no-install-recommends gcc python3-dev libpq-dev && \
#     rm -rf /var/lib/apt/lists/*

# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# COPY . .

# RUN python manage.py collectstatic --noinput

# EXPOSE 8080

# CMD ["gunicorn", "--bind", "0.0.0.0:8000", "src.wsgi:application"]