"""
Spatial queries, written in SQL so that every PostGIS function is visible.

Everything is stored in WGS 84 (SRID 4326, longitude/latitude in degrees).
Two techniques keep the maths in metres:

* Shapes (the centroid and the search circle) are worked out in Irish
  Transverse Mercator (ITM, SRID 2157), a flat projection in metres made for
  Ireland, and then transformed back to 4326 for Leaflet.
* Distances use the geography type (location::geography), which measures on
  the curved Earth and returns metres. The venue table has a GiST index on
  location::geography (migration 0002), so venue searches use that index.

Queries
    meeting_point      ST_Centroid + ST_Collect   the middle of the group
    lines_to_point     ST_MakeLine + ST_Length    each friend's line and distance to it
    group_hull         ST_ConvexHull + ST_Area    the area the group covers
    search_area        ST_Buffer                  the circle searched for venues
    venues_within      ST_DWithin + ST_Distance   venues within the radius, nearest first
    nearest_venues     <-> (KNN)                  the nearest venues when none are in range
    rank_by_fairness   ST_Distance + stddev_pop   venues ranked by how fair they are for everyone
    venues_in_hull     ST_Contains                venues inside the group's area
"""

from django.contrib.gis.geos import GEOSGeometry
from django.db import connection

from ..models import Venue


def _fetch_one(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def _fetch_all(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _geometry(value):
    """PostGIS sends geometries as hex EWKB text; turn that into a GEOS geometry."""
    return GEOSGeometry(value) if value is not None else None


def _lon_lat(point):
    """Parameters for ST_MakePoint(lon, lat). The point must be in SRID 4326."""
    return {"lon": point.x, "lat": point.y}


# ---------------------------------------------------------------------------
# The group: meeting point, lines and area
# ---------------------------------------------------------------------------
def meeting_point(group_id):
    """The centroid of all the friends in a group, or None if it has no friends."""
    sql = """
        SELECT ST_Transform(
                   ST_Centroid(                              -- centre of the points
                       ST_Collect(                           -- all friends as one MultiPoint
                           ST_Transform(f.location, 2157))), -- in metres (ITM)
                   4326)                                     -- back to lon/lat
        FROM meetups_friend AS f
        WHERE f.group_id = %(group_id)s
    """
    (value,) = _fetch_one(sql, {"group_id": group_id})
    return _geometry(value)


def lines_to_point(group_id, point):
    """A straight line from each friend to the point and its length: {friend_id: (line, metres)}."""
    sql = """
        SELECT f.id,
               ST_MakeLine(f.location, target.geom) AS line,
               -- length on the curved Earth (geography), in metres
               ST_Length(ST_MakeLine(f.location, target.geom)::geography) AS metres
        FROM meetups_friend AS f
        CROSS JOIN (SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326) AS geom) AS target
        WHERE f.group_id = %(group_id)s
    """
    rows = _fetch_all(sql, {"group_id": group_id, **_lon_lat(point)})
    return {friend_id: (_geometry(line), metres) for friend_id, line, metres in rows}


def group_hull(group_id):
    """
    The convex hull of the friends (the smallest shape without dents that
    holds them all) and its area in square metres.

    With three or more friends that are not in a straight line the hull is a
    polygon. With one friend it is a point, and with two friends (or friends
    in a line) it is a line. Those have no area, so (None, 0.0) is returned.
    """
    sql = """
        SELECT hull.geom,
               ST_Area(hull.geom::geography) AS area_m2
        FROM (SELECT ST_ConvexHull(ST_Collect(f.location)) AS geom
              FROM meetups_friend AS f
              WHERE f.group_id = %(group_id)s) AS hull
    """
    value, area_m2 = _fetch_one(sql, {"group_id": group_id})
    hull = _geometry(value)
    if hull is None or hull.geom_type != "Polygon":
        return None, 0.0
    return hull, area_m2


def search_area(point, radius_m):
    """A circle of radius_m metres around the point, as a polygon to draw on the map."""
    sql = """
        SELECT ST_Transform(
                   ST_Buffer(
                       ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 2157),
                       %(radius)s,         -- radius in metres, because ITM is in metres
                       'quad_segs=16'),    -- 64 sides: smooth enough to look round
                   4326)
    """
    (value,) = _fetch_one(sql, {"radius": radius_m, **_lon_lat(point)})
    return _geometry(value)


# ---------------------------------------------------------------------------
# Venues around the meeting point
# ---------------------------------------------------------------------------
# Kept as a constant so "manage.py explain_venue_search" can show the plan of this exact query.
VENUES_WITHIN_SQL = """
    SELECT v.*,
           ST_Distance(v.location::geography,
                       ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) AS distance_m
    FROM meetups_venue AS v
    WHERE v.category = ANY(%(categories)s)
      -- true distance in metres, answered from the GiST index on location::geography
      AND ST_DWithin(v.location::geography,
                     ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
                     %(radius)s)
    ORDER BY distance_m, v.name
    LIMIT %(limit)s
"""


def venues_within(point, radius_m, categories, limit):
    """Venues of the given categories within radius_m of the point, nearest first, each with .distance_m."""
    params = {"categories": list(categories), "radius": radius_m, "limit": limit, **_lon_lat(point)}
    return list(Venue.objects.raw(VENUES_WITHIN_SQL, params))


def nearest_venues(point, categories, count):
    """The `count` venues closest to the point, however far away they are, each with .distance_m."""
    sql = """
        SELECT v.*,
               ST_Distance(v.location::geography,
                           ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) AS distance_m
        FROM meetups_venue AS v
        WHERE v.category = ANY(%(categories)s)
        -- <-> is the nearest-neighbour (KNN) operator: the GiST index returns
        -- venues in order of distance, so only the first few rows are read
        ORDER BY v.location::geography <-> ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography
        LIMIT %(count)s
    """
    params = {"categories": list(categories), "count": count, **_lon_lat(point)}
    venues = list(Venue.objects.raw(sql, params))
    # <-> on geography measures on a sphere and ST_Distance on the spheroid, so
    # sort again by the exact distance that is shown to the user.
    return sorted(venues, key=lambda venue: venue.distance_m)


def rank_by_fairness(group_id, point, venue_ids):
    """
    The given venues ranked by how fair each one is for the whole group.

    For every venue the distance from each friend is measured. A venue where
    everyone travels about the same distance gets a high score (same formula
    as fairness.fairness_score). Each venue gets .distance_m (from the
    meeting point), .mean_trip_m, .longest_trip_m and .fairness_score.
    """
    if not venue_ids:
        return []
    sql = """
        SELECT v.*,
               ST_Distance(v.location::geography,
                           ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) AS distance_m,
               trips.mean_m AS mean_trip_m,
               trips.longest_m AS longest_trip_m,
               -- 100 x (1 - spread / mean), kept between 0 and 100;
               -- a mean of 0 means everyone is already there, which is perfectly fair
               COALESCE(GREATEST(0, LEAST(100,
                   100 * (1 - trips.spread_m / NULLIF(trips.mean_m, 0)))), 100) AS fairness_score
        FROM meetups_venue AS v
        CROSS JOIN LATERAL (
            -- every friend's straight-line trip to this venue
            SELECT avg(trip.metres) AS mean_m,
                   max(trip.metres) AS longest_m,
                   stddev_pop(trip.metres) AS spread_m
            FROM (SELECT ST_Distance(f.location::geography, v.location::geography) AS metres
                  FROM meetups_friend AS f
                  WHERE f.group_id = %(group_id)s) AS trip
        ) AS trips
        WHERE v.id = ANY(%(venue_ids)s)
        ORDER BY fairness_score DESC, longest_trip_m, v.name
    """
    params = {"group_id": group_id, "venue_ids": list(venue_ids), **_lon_lat(point)}
    venues = list(Venue.objects.raw(sql, params))
    for venue in venues:
        venue.fairness_score = round(venue.fairness_score, 1)
    return venues


def venues_in_hull(group_id):
    """How many venues of each category are inside the group's saved hull: {"cafe": 12, ...}."""
    sql = """
        SELECT v.category, count(*)
        FROM meetups_meetupgroup AS g
        -- uses the GiST index on the venue locations
        JOIN meetups_venue AS v ON ST_Contains(g.hull, v.location)
        WHERE g.id = %(group_id)s
        GROUP BY v.category
    """
    counts = dict.fromkeys(Venue.Category.values, 0)
    counts.update(dict(_fetch_all(sql, {"group_id": group_id})))
    return counts
