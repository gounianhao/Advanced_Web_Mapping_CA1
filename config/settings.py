"""
Django settings for Meet Halfway.

Every value that changes between machines (passwords, debug mode, allowed
hosts) is read from environment variables. docker-compose.yml passes them in
from the .env file, so no secrets are written in the code.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers for reading environment variables
# ---------------------------------------------------------------------------
def env(name, default=None):
    """Return an environment variable, or stop with a clear error if a required one is missing."""
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value


def env_bool(name, default=False):
    """Read a true/false style variable ("1", "true", "yes", "on" mean True)."""
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    """Read a comma-separated variable into a list, skipping blanks."""
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Core settings
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",  # GeoDjango: spatial fields, lookups and functions
    # Third-party apps
    "rest_framework",
    "rest_framework_gis",  # GeoJSON serializers and bounding-box filter
    "django_filters",
    "drf_spectacular",  # OpenAPI schema and Swagger UI at /api/docs/
    # Project apps
    "meetups",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Database: PostgreSQL with the PostGIS extension
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", "db"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_REDIRECT_URL = "meetups:map"
LOGOUT_REDIRECT_URL = "meetups:map"


# ---------------------------------------------------------------------------
# Language and time
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/Dublin"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # filled by "manage.py collectstatic"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
# Stored in files so that every server process in the container shares it.
# Holds address-search results and the once-a-second limit for Nominatim.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": env("DJANGO_CACHE_DIR", "/tmp/meet-halfway-cache"),
    }
}


# ---------------------------------------------------------------------------
# Security headers that work over plain HTTP
# ---------------------------------------------------------------------------
# OpenStreetMap's tile servers reject tile requests that have no Referer
# header. Django's default policy ("same-origin") would strip it, so use the
# browser default, which sends only the site's origin to other sites.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"


# ---------------------------------------------------------------------------
# REST API (Django REST framework)
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Secure by default: endpoints need a logged-in user unless they say otherwise.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# API documentation (drf-spectacular)
SPECTACULAR_SETTINGS = {
    "TITLE": "Meet Halfway API",
    "DESCRIPTION": (
        "Find a fair meeting point for a group of friends in Dublin and the venues around it. "
        "Venues are public; everything else needs a logged-in user. "
        "Log in at /api-auth/login/ before using \"Try it out\"."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,  # separate request and response schemas
}


# ---------------------------------------------------------------------------
# Map and data settings
# ---------------------------------------------------------------------------
# Starting view: Dublin city centre (the Spire, O'Connell Street) as (lat, lon).
MAP_DEFAULT_CENTER = (53.3498, -6.2603)
MAP_DEFAULT_ZOOM = 13

# Area the app covers: Greater Dublin, as (min lon, min lat, max lon, max lat).
SERVICE_AREA_BBOX = (-6.55, 53.18, -5.99, 53.64)

# OpenStreetMap venues, downloaded by "manage.py fetch_venues".
VENUES_GEOJSON_PATH = BASE_DIR / "data" / "dublin_venues.geojson"

# Most venues the API returns in one response (protects the server and the browser).
VENUE_LIST_LIMIT = 5000

# Venue search around a meeting point: at most this many results, and how many
# of the nearest venues to show when there are none within the radius.
VENUE_SEARCH_LIMIT = 100
VENUE_FALLBACK_COUNT = 5


# ---------------------------------------------------------------------------
# Address search (OpenStreetMap Nominatim)
# ---------------------------------------------------------------------------
NOMINATIM_URL = env("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
# Nominatim's usage policy asks every app to identify itself.
NOMINATIM_USER_AGENT = env(
    "NOMINATIM_USER_AGENT",
    "MeetHalfway/1.0 (+https://github.com/gounianhao/Advanced_Web_Mapping_CA1)",
)
NOMINATIM_TIMEOUT_S = 8
NOMINATIM_MIN_INTERVAL_S = 1          # at most one request per second for the whole app
GEOCODE_CACHE_SECONDS = 60 * 60 * 24  # remember results for a day
GEOCODE_RESULT_LIMIT = 5
