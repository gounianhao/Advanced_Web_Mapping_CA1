"""Shared validation rules."""

from django.conf import settings


def in_service_area(lon, lat):
    """True if the longitude/latitude is inside the Greater Dublin area the app covers."""
    min_lon, min_lat, max_lon, max_lat = settings.SERVICE_AREA_BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
