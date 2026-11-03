"""Serializers: turn model objects into GeoJSON for the REST API."""

from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import Venue


class VenueSerializer(GeoFeatureModelSerializer):
    """A venue as a GeoJSON Feature (a list of them becomes a FeatureCollection)."""

    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Venue
        geo_field = "location"
        fields = ("id", "osm_id", "name", "category", "category_label", "cuisine",
                  "address", "opening_hours", "website", "location")
