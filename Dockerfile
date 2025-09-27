FROM python:3.10.14-slim-bookworm as builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.10.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /root/.local /root/.local

# Create non-root user and set permissions
RUN addgroup --system app && adduser --system --ingroup app app

# Copy project code
COPY . .

# Collect static as root (ensure proper permissions)
RUN python manage.py collectstatic --noinput || true

# Change ownership of the app directory
RUN chown -R app:app /app

USER app

EXPOSE 9000

# Use CMD instead of ENTRYPOINT for flexibility
CMD ["gunicorn", "--bind", "0.0.0.0:9000", "src.wsgi:application", \
     "--workers", "3", "--timeout", "120"]