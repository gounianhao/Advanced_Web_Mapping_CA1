"""
Spatial index on the venue location cast to geography.

The "venues within X metres" search uses
    ST_DWithin(location::geography, <point>::geography, <metres>)
so that distances are measured in metres on the Earth's surface. The normal
GiST index on the geometry column can't be used for that expression, so this
expression index lets PostgreSQL use an index scan instead of checking every
venue.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("meetups", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE INDEX meetups_venue_location_geog_idx ON meetups_venue USING GIST ((location::geography));",
            reverse_sql="DROP INDEX IF EXISTS meetups_venue_location_geog_idx;",
        ),
    ]
