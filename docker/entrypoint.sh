#!/bin/sh
# Runs every time the web container starts, before gunicorn.
set -e

# The database container reports healthy before it accepts every connection,
# so retry the migrations for a short while.
tries=0
until python manage.py migrate --noinput; do
    tries=$((tries + 1))
    if [ "$tries" -ge 10 ]; then
        echo "The database is still not ready. Giving up." >&2
        exit 1
    fi
    echo "Waiting for the database..."
    sleep 3
done

# Copy CSS, JavaScript and admin files to the volume Nginx serves them from.
python manage.py collectstatic --noinput --verbosity 0

# Load the OpenStreetMap venues the first time the stack starts.
python manage.py load_venues --if-empty

exec "$@"
