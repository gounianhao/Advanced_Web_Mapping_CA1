"""
Load the OpenStreetMap venues from data/dublin_venues.geojson into PostGIS.

Safe to run more than once: venues are matched on their OpenStreetMap id and
updated instead of duplicated.

    docker compose exec web python manage.py load_venues
"""

import json
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import connection, transaction

from meetups.models import Venue

UPDATE_FIELDS = ["name", "category", "cuisine", "address", "opening_hours", "website", "location"]


class Command(BaseCommand):
    help = "Load venues from the GeoJSON file into the database (creates new ones, updates existing ones)."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(settings.VENUES_GEOJSON_PATH),
                            help="GeoJSON file to load.")
        parser.add_argument("--if-empty", action="store_true",
                            help="Do nothing if the venue table already has data.")

    def handle(self, *args, **options):
        if options["if_empty"] and Venue.objects.exists():
            self.stdout.write("Venues already loaded; nothing to do.")
            return

        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"{path} not found. Run 'python manage.py fetch_venues' first.")
        try:
            features = json.loads(path.read_text(encoding="utf-8"))["features"]
        except (ValueError, KeyError) as error:
            raise CommandError(f"{path} is not a valid GeoJSON FeatureCollection: {error}") from error

        venues_by_osm_id, skipped = {}, 0
        for feature in features:
            venue = self.to_venue(feature)
            if venue is None:
                skipped += 1
            else:
                venues_by_osm_id[venue.osm_id] = venue  # a repeated id keeps the last copy
        venues = list(venues_by_osm_id.values())

        with transaction.atomic():
            # One INSERT ... ON CONFLICT (osm_id) DO UPDATE per batch of 500 rows.
            Venue.objects.bulk_create(
                venues,
                batch_size=500,
                update_conflicts=True,
                unique_fields=["osm_id"],
                update_fields=UPDATE_FIELDS,
            )

        # Refresh the planner statistics so PostgreSQL knows to use the spatial indexes.
        with connection.cursor() as cursor:
            cursor.execute(f"ANALYZE {Venue._meta.db_table}")

        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(venues)} venues ({skipped} skipped). Total in database: {Venue.objects.count()}."
        ))

    @staticmethod
    def to_venue(feature):
        """Validate one GeoJSON feature and turn it into an unsaved Venue (None if invalid)."""
        min_lon, min_lat, max_lon, max_lat = settings.SERVICE_AREA_BBOX
        try:
            props = feature["properties"]
            geometry = feature["geometry"]
            if geometry["type"] != "Point":
                return None
            lon, lat = (float(value) for value in geometry["coordinates"][:2])
            name = str(props["name"]).strip()
            category = props["category"]
        except (KeyError, TypeError, ValueError):
            return None

        if not name or category not in Venue.Category.values:
            return None
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            return None

        website = props.get("website") or ""
        try:
            URLValidator(schemes=["http", "https"])(website)
        except ValidationError:
            website = ""  # drop broken or non-web links rather than the whole venue

        return Venue(
            osm_id=str(props.get("osm_id") or feature.get("id"))[:32],
            name=name[:200],
            category=category,
            cuisine=(props.get("cuisine") or "")[:100],
            address=(props.get("address") or "")[:255],
            opening_hours=(props.get("opening_hours") or "")[:255],
            website=website[:300],
            location=Point(lon, lat, srid=4326),
        )
