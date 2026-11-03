"""
REST API views (controllers that return JSON instead of HTML pages).

GET /api/venues/                    all venues as a GeoJSON FeatureCollection
GET /api/venues/?in_bbox=W,S,E,N    only venues inside a bounding box (lon/lat)
GET /api/venues/?category=cafe      filter by type (repeat for several types)
GET /api/venues/<id>/               one venue
"""

from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework_gis.filters import InBBoxFilter

from .filters import VenueFilter
from .models import Venue
from .serializers import VenueSerializer


class VenueViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only venue data. Public: it is OpenStreetMap data, not user data."""

    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    permission_classes = [permissions.AllowAny]

    # in_bbox=min_lon,min_lat,max_lon,max_lat -> WHERE location @ <bbox polygon>,
    # answered from the GiST index on the location column.
    filter_backends = [InBBoxFilter, DjangoFilterBackend]
    bbox_filter_field = "location"
    filterset_class = VenueFilter

    def list(self, request, *args, **kwargs):
        # No paging: the map needs every venue in view in one response.
        # VENUE_LIST_LIMIT caps the size if the whole area is requested.
        queryset = self.filter_queryset(self.get_queryset())[: settings.VENUE_LIST_LIMIT]
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
