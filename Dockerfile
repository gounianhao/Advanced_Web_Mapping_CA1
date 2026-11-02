# Meet Halfway - Django / GeoDjango application image
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

# Copy the project code.
COPY . .

EXPOSE 8000

# Django development server (reloads automatically when the code changes).
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
