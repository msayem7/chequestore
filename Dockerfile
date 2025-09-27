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
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.10.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime dependencies including netcat
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user and set permissions
RUN addgroup --system app && adduser --system --ingroup app app

# Create staticfiles directory with proper permissions BEFORE copying code
RUN mkdir -p /app/staticfiles && chown -R app:app /app/staticfiles

# Copy project code and entrypoint script
COPY . .
COPY entrypoint.sh /entrypoint.sh

# Set execute permissions and fix ownership
RUN chmod +x /entrypoint.sh && \
    chown -R app:app /app

USER app

EXPOSE 9000

ENTRYPOINT ["/entrypoint.sh"]