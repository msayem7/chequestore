#!/bin/sh
set -e

echo "Running entrypoint script as $(whoami)..."

# Wait for database to be ready (optional but recommended)
echo "Waiting for database..."
while ! nc -z db 5432; do
  sleep 0.5
done
echo "Database is ready!"

# Run Django management commands
echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn server..."
exec gunicorn --bind 0.0.0.0:9000 src.wsgi:application \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    "$@"