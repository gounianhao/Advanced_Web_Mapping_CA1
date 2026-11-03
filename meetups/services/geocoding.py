"""
Address search with OpenStreetMap's Nominatim service.

The browser never calls Nominatim itself. It calls GET /api/geocode/?q=...
and this module forwards the search, which lets the app follow the Nominatim
usage policy (https://operations.osmfoundation.org/policies/nominatim/):

* every request sends a User-Agent that identifies the app;
* the whole app makes at most one request per second;
* results are cached, so a repeated search never reaches Nominatim;
* the page only searches when the user presses Enter (no search-as-you-type).

Results are limited to the Greater Dublin service area.
"""

import hashlib
import time

import requests
from django.conf import settings
from django.core.cache import cache

from ..validators import in_service_area

RATE_LIMIT_KEY = "geocode:last-request"
MAX_WAIT_S = 3  # how long a search waits for its turn before giving up


class GeocodingError(Exception):
    """Nominatim could not be reached or sent back something unusable."""


class GeocodingBusy(Exception):
    """Too many searches at the same moment; try again shortly."""


def _wait_for_turn():
    """Wait until the app may call Nominatim again (at most once per second)."""
    deadline = time.monotonic() + MAX_WAIT_S
    # cache.add only stores the key if it isn't there already, and the key
    # expires after the interval, so only one request per interval gets through.
    while not cache.add(RATE_LIMIT_KEY, True, timeout=settings.NOMINATIM_MIN_INTERVAL_S):
        if time.monotonic() >= deadline:
            raise GeocodingBusy
        time.sleep(0.2)


def _clean(place):
    """Keep only what the page needs from one Nominatim result, or None if it's unusable."""
    try:
        lat, lon = float(place["lat"]), float(place["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not in_service_area(lon, lat):
        return None
    return {
        "name": place.get("display_name", ""),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "type": place.get("type", ""),
    }


def search(query):
    """Up to GEOCODE_RESULT_LIMIT places in Dublin matching the query, best match first."""
    query = " ".join(query.split())
    cache_key = "geocode:" + hashlib.sha256(query.casefold().encode()).hexdigest()
    results = cache.get(cache_key)
    if results is not None:
        return results

    _wait_for_turn()
    min_lon, min_lat, max_lon, max_lat = settings.SERVICE_AREA_BBOX
    try:
        response = requests.get(
            settings.NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "limit": settings.GEOCODE_RESULT_LIMIT,
                "countrycodes": "ie",
                "viewbox": f"{min_lon},{max_lat},{max_lon},{min_lat}",  # left, top, right, bottom
                "bounded": 1,  # only places inside the viewbox
            },
            headers={
                "User-Agent": settings.NOMINATIM_USER_AGENT,
                "Accept-Language": "en",
            },
            timeout=settings.NOMINATIM_TIMEOUT_S,
        )
        response.raise_for_status()
        places = response.json()
    except (requests.RequestException, ValueError) as error:
        raise GeocodingError(str(error)) from error

    if not isinstance(places, list):
        raise GeocodingError("Unexpected answer from Nominatim.")
    results = [place for place in map(_clean, places) if place is not None]
    cache.set(cache_key, results, settings.GEOCODE_CACHE_SECONDS)
    return results
