"""Serializers: convert between model objects and JSON / GeoJSON for the REST API."""

from django.contrib.gis.geos import Point
from rest_framework import serializers
from rest_framework_gis.fields import GeometryField
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import Friend, MeetupGroup, Venue
from .services.fairness import fairness_label
from .validators import in_service_area

# Decimal places kept in coordinates sent to the browser (6 is about 10 cm).
PRECISION = 6


class MetresField(serializers.FloatField):
    """A read-only distance (m) or area (m²), rounded to one decimal place."""

    def __init__(self, **kwargs):
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        return round(float(value), 1)


# ---------------------------------------------------------------------------
# Venues
# ---------------------------------------------------------------------------
class VenueSerializer(GeoFeatureModelSerializer):
    """A venue as a GeoJSON Feature (a list of them becomes a FeatureCollection)."""

    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Venue
        geo_field = "location"
        fields = ("id", "osm_id", "name", "category", "category_label", "cuisine",
                  "address", "opening_hours", "website", "location")


class NearbyVenueSerializer(VenueSerializer):
    """A venue found near a meeting point, with its straight-line distance from it."""

    distance_m = MetresField()

    class Meta(VenueSerializer.Meta):
        fields = VenueSerializer.Meta.fields + ("distance_m",)


class FairVenueSerializer(NearbyVenueSerializer):
    """A nearby venue plus how fair it is: the friends' trips to it and the 0-100 score."""

    mean_trip_m = MetresField(help_text="Average distance from each friend to the venue.")
    longest_trip_m = MetresField(help_text="Distance for the friend who is furthest away.")
    fairness_score = serializers.FloatField(read_only=True)
    fairness_label = serializers.SerializerMethodField()

    class Meta(NearbyVenueSerializer.Meta):
        fields = NearbyVenueSerializer.Meta.fields + (
            "mean_trip_m", "longest_trip_m", "fairness_score", "fairness_label",
        )

    def get_fairness_label(self, venue) -> str:
        return fairness_label(venue.fairness_score)


# ---------------------------------------------------------------------------
# Groups and friends
# ---------------------------------------------------------------------------
class FriendSerializer(serializers.ModelSerializer):
    """
    One friend. `location` is a GeoJSON Point in [longitude, latitude] order,
    e.g. {"type": "Point", "coordinates": [-6.2546, 53.3438]}.
    """

    location = GeometryField(precision=PRECISION)
    line_to_meeting = GeometryField(precision=PRECISION, read_only=True)
    distance_m = MetresField(allow_null=True)

    class Meta:
        model = Friend
        fields = ("id", "group", "name", "place_name", "location",
                  "line_to_meeting", "distance_m", "created_at")
        read_only_fields = ("created_at",)
        # "One name per group" is checked in validate(), which gives a clearer message.
        validators = []

    def get_fields(self):
        fields = super().get_fields()
        # Friends can only be added to the logged-in user's own groups.
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            fields["group"].queryset = MeetupGroup.objects.filter(owner=user)
        else:
            fields["group"].queryset = MeetupGroup.objects.none()
        return fields

    def validate_location(self, value):
        if value.geom_type != "Point" or value.empty:
            raise serializers.ValidationError(
                'Send a GeoJSON Point, e.g. {"type": "Point", "coordinates": [-6.26, 53.35]}.'
            )
        if value.srid is None:
            value.srid = 4326
        elif value.srid != 4326:
            value = value.transform(4326, clone=True)
        if not in_service_area(value.x, value.y):
            raise serializers.ValidationError(
                "This place is outside the Greater Dublin area that Meet Halfway covers. "
                "Coordinates go in [longitude, latitude] order."
            )
        return Point(value.x, value.y, srid=4326)  # drops any height value

    def validate(self, attrs):
        friend = self.instance
        group = attrs.get("group", friend.group if friend else None)
        name = attrs.get("name", friend.name if friend else None)

        if friend is not None and group != friend.group:
            raise serializers.ValidationError({"group": "A friend can't be moved to another group."})

        others = group.friends.exclude(pk=friend.pk) if friend else group.friends.all()
        if name and others.filter(name__iexact=name).exists():
            raise serializers.ValidationError({"name": f"{group.name} already has a friend called {name}."})

        if friend is None and group.friends.count() >= MeetupGroup.MAX_FRIENDS:
            raise serializers.ValidationError(
                {"group": f"A group can have at most {MeetupGroup.MAX_FRIENDS} friends."}
            )
        return attrs


class MeetupGroupSerializer(serializers.ModelSerializer):
    """A group and the results PostGIS has worked out for it (null until it has two friends)."""

    friend_count = serializers.SerializerMethodField()
    meeting_point = GeometryField(precision=PRECISION, read_only=True)
    hull = GeometryField(precision=PRECISION, read_only=True)
    fairness_label = serializers.SerializerMethodField()

    class Meta:
        model = MeetupGroup
        fields = ("id", "name", "search_radius_m", "friend_count", "meeting_point", "hull",
                  "fairness_score", "fairness_label", "created_at", "updated_at")
        read_only_fields = ("fairness_score", "created_at", "updated_at")

    def get_friend_count(self, group) -> int:
        count = getattr(group, "friend_count", None)  # added by .annotate() in the view
        return count if count is not None else group.friends.count()

    def get_fairness_label(self, group) -> str:
        return fairness_label(group.fairness_score)


class MeetupGroupDetailSerializer(MeetupGroupSerializer):
    """A group with all its friends."""

    friends = FriendSerializer(many=True, read_only=True)

    class Meta(MeetupGroupSerializer.Meta):
        fields = MeetupGroupSerializer.Meta.fields + ("friends",)


# ---------------------------------------------------------------------------
# Venue searches around a meeting point
# ---------------------------------------------------------------------------
class VenueSearchQuerySerializer(serializers.Serializer):
    """Query-string options for the venue searches."""

    radius = serializers.IntegerField(
        required=False,
        min_value=MeetupGroup.MIN_RADIUS_M,
        max_value=MeetupGroup.MAX_RADIUS_M,
        help_text="Search radius in metres. Defaults to the group's own radius.",
    )
    category = serializers.MultipleChoiceField(
        choices=Venue.Category.choices,
        required=False,
        help_text="Type of venue; repeat for several. Defaults to cafe.",
    )


class VenueSearchSerializer(serializers.Serializer):
    meeting_point = GeometryField(precision=PRECISION)
    radius_m = serializers.IntegerField()
    categories = serializers.ListField(child=serializers.CharField())
    search_area = GeometryField(precision=PRECISION, help_text="The circle that was searched (ST_Buffer).")
    fallback = serializers.BooleanField(
        help_text="True if nothing was within the radius, so the nearest venues are listed instead."
    )
    count = serializers.SerializerMethodField()
    venues = NearbyVenueSerializer(many=True)

    def get_count(self, search) -> int:
        return len(search.venues)


class FairVenueSearchSerializer(VenueSearchSerializer):
    venues = FairVenueSerializer(many=True)


class GroupAreaSerializer(serializers.Serializer):
    area_m2 = MetresField(help_text="Area of the group's convex hull in square metres (0 for a line).")
    venues_inside = serializers.DictField(
        child=serializers.IntegerField(), help_text="Number of venues of each type inside the hull."
    )


class MeetingResultSerializer(serializers.Serializer):
    group = MeetupGroupDetailSerializer()
    area = GroupAreaSerializer()
    venues = VenueSearchSerializer()


# ---------------------------------------------------------------------------
# Address search
# ---------------------------------------------------------------------------
class GeocodeQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=3, max_length=200,
                              help_text="An address or place, e.g. Heuston Station.")


class GeocodeResultSerializer(serializers.Serializer):
    name = serializers.CharField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    type = serializers.CharField()


class GeocodeResponseSerializer(serializers.Serializer):
    query = serializers.CharField()
    results = GeocodeResultSerializer(many=True)
