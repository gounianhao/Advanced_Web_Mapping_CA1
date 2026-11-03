"""
Download Dublin cafés, restaurants and pubs from OpenStreetMap and save them
as GeoJSON in data/dublin_venues.geojson.

The file is kept in the repository so the app works without internet access.
Run this again only to refresh the data:

    docker compose exec web python manage.py fetch_venues
"""

import json
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Public Overpass API servers (the second one is used if the first fails).
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "MeetHalfway/1.0 (Location-Based Services student project)"
CATEGORIES = ("cafe", "restaurant", "pub")
ATTRIBUTION = "© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)"


def build_query(bbox):
    """Overpass QL: every named café/restaurant/pub in the bounding box.

    "nwr" means nodes, ways (buildings) and relations; "out center" returns a
    single centre point for buildings, so every result can be stored as a point.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    pattern = "|".join(CATEGORIES)
    return (
        "[out:json][timeout:180];"
        f'nwr["amenity"~"^({pattern})$"]["name"]({min_lat},{min_lon},{max_lat},{max_lon});'
        "out center;"
    )


def build_address(tags):
    """Turn OpenStreetMap addr:* tags into one line, e.g. "12 Dame Street, Dublin 2"."""
    street = " ".join(part for part in (tags.get("addr:housenumber"), tags.get("addr:street")) if part)
    parts = [tags.get("addr:housename"), street, tags.get("addr:city") or tags.get("addr:suburb"),
             tags.get("addr:postcode")]
    return ", ".join(part for part in parts if part)


def to_feature(element):
    """Convert one Overpass element into a GeoJSON Feature, or None if it is unusable."""
    tags = element.get("tags", {})
    if element["type"] == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        centre = element.get("center", {})
        lat, lon = centre.get("lat"), centre.get("lon")
    name = tags.get("name", "").strip()
    if lat is None or lon is None or not name or tags.get("amenity") not in CATEGORIES:
        return None

    osm_id = f"{element['type']}/{element['id']}"
    return {
        "type": "Feature",
        "id": osm_id,
        "geometry": {"type": "Point", "coordinates": [round(lon, 7), round(lat, 7)]},
        "properties": {
            "osm_id": osm_id,
            "name": name[:200],
            "category": tags["amenity"],
            "cuisine": tags.get("cuisine", "").replace(";", ", ")[:100],
            "address": build_address(tags)[:255],
            "opening_hours": tags.get("opening_hours", "")[:255],
            "website": (tags.get("website") or tags.get("contact:website") or "")[:300],
        },
    }


class Command(BaseCommand):
    help = "Download cafés, restaurants and pubs in Greater Dublin from OpenStreetMap into a GeoJSON file."

    def add_arguments(self, parser):
        parser.add_argument("--output", default=str(settings.VENUES_GEOJSON_PATH),
                            help="Where to write the GeoJSON file.")

    def handle(self, *args, **options):
        query = build_query(settings.SERVICE_AREA_BBOX)
        elements = self.run_query(query)

        features = [feature for feature in map(to_feature, elements) if feature]
        features.sort(key=lambda feature: feature["id"])  # stable order = small git diffs
        if not features:
            raise CommandError("OpenStreetMap returned no venues; the file was not changed.")

        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        self.write_geojson(output, features)

        counts = {category: sum(f["properties"]["category"] == category for f in features)
                  for category in CATEGORIES}
        summary = ", ".join(f"{count} {category}s" for category, count in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Saved {len(features)} venues ({summary}) to {output}"))

    def run_query(self, query):
        """Send the query to Overpass, trying the next server if one fails."""
        last_error = None
        for url in OVERPASS_URLS:
            self.stdout.write(f"Querying {url} …")
            try:
                response = requests.post(url, data={"data": query},
                                         headers={"User-Agent": USER_AGENT}, timeout=200)
                response.raise_for_status()
                return response.json()["elements"]
            except (requests.RequestException, ValueError, KeyError) as error:
                last_error = error
                self.stderr.write(f"  failed: {error}")
        raise CommandError(f"Could not download venues from OpenStreetMap: {last_error}")

    @staticmethod
    def write_geojson(path, features):
        """Write a valid GeoJSON FeatureCollection with one feature per line."""
        with path.open("w", encoding="utf-8") as file:
            file.write('{"type": "FeatureCollection",\n')
            file.write(f'"attribution": {json.dumps(ATTRIBUTION, ensure_ascii=False)},\n')
            file.write('"features": [\n')
            file.write(",\n".join(json.dumps(feature, ensure_ascii=False) for feature in features))
            file.write("\n]}\n")
