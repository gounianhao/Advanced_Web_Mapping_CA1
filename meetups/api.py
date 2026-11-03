"""
REST API views (controllers that return JSON instead of HTML pages).

Venues are public. Groups, friends and address search need a logged-in user,
and each user only ever sees their own groups (anyone else's give a 404).
Interactive documentation: /api/docs/
"""

from django.conf import settings
from django.db.models import Count
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, Throttled
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_gis.filters import InBBoxFilter

from .filters import VenueFilter
from .models import Friend, MeetupGroup, Venue
from .serializers import (
    FairVenueSearchSerializer,
    FriendSerializer,
    GeocodeQuerySerializer,
    GeocodeResponseSerializer,
    MeetingResultSerializer,
    MeetupGroupDetailSerializer,
    MeetupGroupSerializer,
    VenueSearchQuerySerializer,
    VenueSearchSerializer,
    VenueSerializer,
)
from .services import geocoding, meeting

DEFAULT_CATEGORIES = [Venue.Category.CAFE.value]


class NotReady(APIException):
    """The group can't be used for this yet (400)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Add at least two friends to find a meeting point."
    default_code = "not_ready"


class ServiceUnavailable(APIException):
    """An outside service (the address search) didn't answer (503)."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The address search isn't available right now. Try again later, or click the map instead."
    default_code = "service_unavailable"


# ---------------------------------------------------------------------------
# Venues
# ---------------------------------------------------------------------------
class VenueViewSet(viewsets.ReadOnlyModelViewSet):
    """
    OpenStreetMap cafés, restaurants and pubs as GeoJSON. Public, because it is
    open data, not user data.

    ?in_bbox=minLon,minLat,maxLon,maxLat  only venues inside a box
    ?category=cafe                        filter by type (repeat for several)
    ?name=...                             name contains (ignoring case)
    """

    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    permission_classes = [permissions.AllowAny]

    # in_bbox -> WHERE location @ <bbox polygon>, answered from the GiST index.
    filter_backends = [InBBoxFilter, DjangoFilterBackend]
    bbox_filter_field = "location"
    filterset_class = VenueFilter

    def list(self, request, *args, **kwargs):
        # No paging: the map needs every venue in view in one response.
        # VENUE_LIST_LIMIT caps the size if the whole area is requested.
        queryset = self.filter_queryset(self.get_queryset())[: settings.VENUE_LIST_LIMIT]
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------
class MeetupGroupViewSet(viewsets.ModelViewSet):
    """
    The logged-in user's groups.

    The meeting point, hull and fairness score are worked out by PostGIS and
    kept up to date whenever a friend is added, moved or removed.
    """

    serializer_class = MeetupGroupSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            # Only reached while the API docs are generated; real requests
            # from anonymous users are refused before this point.
            return MeetupGroup.objects.none()
        queryset = MeetupGroup.objects.filter(owner=user).annotate(friend_count=Count("friends"))
        if self.action != "list":
            queryset = queryset.prefetch_related("friends")
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return MeetupGroupDetailSerializer
        return MeetupGroupSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # --- helpers for the actions below --------------------------------------
    def _search_options(self, request, group):
        """Radius and categories from the query string, checked by VenueSearchQuerySerializer."""
        options = VenueSearchQuerySerializer(data=request.query_params)
        options.is_valid(raise_exception=True)
        radius = options.validated_data.get("radius", group.search_radius_m)
        categories = sorted(options.validated_data.get("category") or DEFAULT_CATEGORIES)
        return radius, categories

    @staticmethod
    def _require_meeting_point(group):
        if group.meeting_point is None:
            raise NotReady("This group has no meeting point yet. Add at least two friends first.")

    # --- actions --------------------------------------------------------------
    @extend_schema(
        request=None,
        parameters=[VenueSearchQuerySerializer],
        responses={200: MeetingResultSerializer, 400: OpenApiResponse(description="Fewer than two friends.")},
    )
    @action(detail=True, methods=["post"])
    def compute(self, request, pk=None):
        """
        Work out the meeting point, each friend's line and distance, the
        group's area and the fairness score, and list venues around the point.
        """
        group = self.get_object()
        radius, categories = self._search_options(request, group)
        try:
            area = meeting.compute_meeting(group)
        except meeting.NotEnoughFriends as error:
            raise NotReady(str(error)) from error

        group = self.get_object()  # reload with the saved results
        search = meeting.search_venues(group.meeting_point, radius, categories)
        result = {"group": group, "area": area, "venues": search}
        return Response(MeetingResultSerializer(result, context=self.get_serializer_context()).data)

    @extend_schema(
        parameters=[VenueSearchQuerySerializer],
        responses={200: VenueSearchSerializer, 400: OpenApiResponse(description="No meeting point yet, or a bad option.")},
    )
    @action(detail=True, methods=["get"])
    def venues(self, request, pk=None):
        """Venues within the radius of the meeting point, nearest first (the 5 nearest if none are in range)."""
        group = self.get_object()
        radius, categories = self._search_options(request, group)
        self._require_meeting_point(group)
        search = meeting.search_venues(group.meeting_point, radius, categories)
        return Response(VenueSearchSerializer(search, context=self.get_serializer_context()).data)

    @extend_schema(
        parameters=[VenueSearchQuerySerializer],
        responses={200: FairVenueSearchSerializer, 400: OpenApiResponse(description="No meeting point yet, or a bad option.")},
    )
    @action(detail=True, methods=["get"], url_path="fair-venues")
    def fair_venues(self, request, pk=None):
        """The same venues, ranked by how evenly the trip to each one is shared by the group."""
        group = self.get_object()
        radius, categories = self._search_options(request, group)
        self._require_meeting_point(group)
        search = meeting.search_fair_venues(group, radius, categories)
        return Response(FairVenueSearchSerializer(search, context=self.get_serializer_context()).data)


# ---------------------------------------------------------------------------
# Friends
# ---------------------------------------------------------------------------
class FriendViewSet(viewsets.ModelViewSet):
    """
    Friends in the logged-in user's groups. Use ?group=<id> for one group.

    Adding, moving or removing a friend updates the group's meeting point
    straight away.
    """

    serializer_class = FriendSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["group"]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Friend.objects.none()  # only while the API docs are generated
        return Friend.objects.filter(group__owner=user).select_related("group")

    def perform_create(self, serializer):
        friend = serializer.save()
        self._refresh(friend)

    def perform_update(self, serializer):
        friend = serializer.save()
        if "location" in serializer.validated_data:
            self._refresh(friend)

    def perform_destroy(self, instance):
        group = instance.group
        instance.delete()
        meeting.refresh_meeting(group)

    @staticmethod
    def _refresh(friend):
        meeting.refresh_meeting(friend.group)
        # Show the new line and distance in the response.
        friend.refresh_from_db(fields=["line_to_meeting", "distance_m"])


# ---------------------------------------------------------------------------
# Address search
# ---------------------------------------------------------------------------
class GeocodeView(APIView):
    """
    Find an address or place in Greater Dublin with OpenStreetMap Nominatim.

    Results are cached and Nominatim is asked at most once per second.
    """

    throttle_scope = "geocode"  # its own per-user limit (see DEFAULT_THROTTLE_RATES)

    @extend_schema(
        parameters=[GeocodeQuerySerializer],
        responses={
            200: GeocodeResponseSerializer,
            429: OpenApiResponse(description="Too many searches at the same moment."),
            503: OpenApiResponse(description="Nominatim could not be reached."),
        },
    )
    def get(self, request):
        options = GeocodeQuerySerializer(data=request.query_params)
        options.is_valid(raise_exception=True)
        query = options.validated_data["q"]
        try:
            results = geocoding.search(query)
        except geocoding.GeocodingBusy as error:
            raise Throttled(wait=1, detail="Too many address searches right now.") from error
        except geocoding.GeocodingError as error:
            raise ServiceUnavailable() from error
        return Response({"query": query, "results": results})
