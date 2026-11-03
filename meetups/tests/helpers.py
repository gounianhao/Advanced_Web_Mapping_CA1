"""Small geometry helpers for the tests."""

import math

from django.contrib.gis.geos import Point

# The Spire on O'Connell Street.
CENTRE = Point(-6.2603, 53.3498, srid=4326)


def shifted(point, north_m=0.0, east_m=0.0):
    """A point moved north and/or east by a number of metres (accurate to well under a metre here)."""
    # Length of one degree on the WGS 84 ellipsoid at Dublin's latitude.
    metres_per_degree_lat = 111_293
    metres_per_degree_lon = 111_561 * math.cos(math.radians(point.y))
    return Point(point.x + east_m / metres_per_degree_lon,
                 point.y + north_m / metres_per_degree_lat, srid=4326)


def metres_between(a, b):
    """Distance between two 4326 points in metres, measured in ITM."""
    return a.transform(2157, clone=True).distance(b.transform(2157, clone=True))


def geojson(point):
    """A point as the GeoJSON the API expects."""
    return {"type": "Point", "coordinates": [point.x, point.y]}
