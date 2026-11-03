"""
Show how PostgreSQL runs the "venues within the radius" search.

    docker compose exec web python manage.py explain_venue_search

Runs EXPLAIN ANALYZE on the same SQL the API uses (spatial.VENUES_WITHIN_SQL).
A line such as "Index Scan using meetups_venue_location_geog_idx" (or a
"Bitmap Index Scan" on it) shows that the GiST index on location::geography
is used instead of reading every venue.
"""

from django.core.management.base import BaseCommand
from django.db import connection

from meetups.models import Venue
from meetups.services.spatial import VENUES_WITHIN_SQL


class Command(BaseCommand):
    help = "Print the query plan (EXPLAIN ANALYZE) of the venue radius search."

    def add_arguments(self, parser):
        # Default: the Spire on O'Connell Street.
        parser.add_argument("--lat", type=float, default=53.3498)
        parser.add_argument("--lon", type=float, default=-6.2603)
        parser.add_argument("--radius", type=int, default=300, help="Radius in metres.")
        parser.add_argument("--category", default=Venue.Category.CAFE.value,
                            choices=Venue.Category.values)

    def handle(self, *args, **options):
        params = {
            "lon": options["lon"],
            "lat": options["lat"],
            "radius": options["radius"],
            "categories": [options["category"]],
            "limit": 100,
        }
        with connection.cursor() as cursor:
            cursor.execute("EXPLAIN (ANALYZE, BUFFERS) " + VENUES_WITHIN_SQL, params)
            for (line,) in cursor.fetchall():
                self.stdout.write(line)
