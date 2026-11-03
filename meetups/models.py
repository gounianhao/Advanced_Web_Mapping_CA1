"""
Database models (the "Model" in MVC).

All geometries are stored in WGS 84 (SRID 4326), the latitude/longitude system
used by GPS, GeoJSON and Leaflet. GeoDjango creates a GiST spatial index on
every geometry column automatically.
"""

from django.conf import settings
from django.contrib.gis.db import models
from django.core.validators import MaxValueValidator, MinValueValidator


class Venue(models.Model):
    """A café, restaurant or pub imported from OpenStreetMap."""

    class Category(models.TextChoices):
        CAFE = "cafe", "Café"
        RESTAURANT = "restaurant", "Restaurant"
        PUB = "pub", "Pub"

    osm_id = models.CharField(max_length=32, unique=True)  # e.g. "node/278857702"
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    cuisine = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=255, blank=True)
    opening_hours = models.CharField(max_length=255, blank=True)
    website = models.URLField(max_length=300, blank=True)
    location = models.PointField(srid=4326)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class MeetupGroup(models.Model):
    """A group of friends planning to meet, plus the results PostGIS calculates for it."""

    MIN_FRIENDS = 2      # needed for a meeting point
    MAX_FRIENDS = 15
    MIN_RADIUS_M = 50
    MAX_RADIUS_M = 2000

    name = models.CharField(max_length=100)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meetup_groups",
    )
    search_radius_m = models.PositiveIntegerField(
        "search radius (m)",
        default=300,
        validators=[MinValueValidator(MIN_RADIUS_M), MaxValueValidator(MAX_RADIUS_M)],
    )

    # Calculated from the friends' locations.
    meeting_point = models.PointField(srid=4326, null=True, blank=True)
    hull = models.PolygonField("group area", srid=4326, null=True, blank=True)
    fairness_score = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class Friend(models.Model):
    """One person in a group and the place they are starting from."""

    group = models.ForeignKey(MeetupGroup, on_delete=models.CASCADE, related_name="friends")
    name = models.CharField(max_length=60)
    place_name = models.CharField(max_length=255, blank=True)  # e.g. "Heuston Station"
    location = models.PointField(srid=4326)

    # Calculated: straight line to the meeting point and its length in metres.
    line_to_meeting = models.LineStringField(srid=4326, null=True, blank=True)
    distance_m = models.FloatField("distance (m)", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["group", "name"], name="unique_friend_name_per_group"),
        ]

    def __str__(self):
        return f"{self.name} ({self.group})"
