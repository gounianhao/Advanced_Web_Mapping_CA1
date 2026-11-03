# Meet Halfway - Django / GeoDjango application image (served by gunicorn behind Nginx)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# GeoDjango needs the GDAL, GEOS and PROJ system libraries.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        binutils \
        gdal-bin \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages first so this layer is cached between code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the project code. It stays owned by root, so the app can't change its own code.
COPY . .

# The app runs as an ordinary user, not root. It only needs to write the
# collected static files (shared with Nginx through a volume).
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home --home-dir /app app \
    && mkdir -p /app/staticfiles \
    && chown app:app /app/staticfiles \
    && chmod +x /app/docker/entrypoint.sh
USER app

EXPOSE 8000

# entrypoint.sh prepares the database and static files, then runs the command below.
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--config", "docker/gunicorn.conf.py"]
