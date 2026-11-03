"""Django admin pages, with OpenStreetMap map widgets for the spatial fields."""

from django.conf import settings
from django.contrib.gis import admin
from django.db.models import Count

from .models import Friend, MeetupGroup, Venue

_lat, _lon = settings.MAP_DEFAULT_CENTER


class DublinMapAdmin(admin.GISModelAdmin):
    """Admin base class whose map widgets open over Dublin instead of (0, 0)."""

    gis_widget_kwargs = {
        "attrs": {"default_lat": _lat, "default_lon": _lon, "default_zoom": 12},
    }


@admin.register(Venue)
class VenueAdmin(DublinMapAdmin):
    list_display = ("name", "category", "cuisine", "address")
    list_filter = ("category",)
    search_fields = ("name", "address", "cuisine", "osm_id")


class FriendInline(admin.TabularInline):
    """Read-only list of a group's friends. Friends are added on their own page, which has a map."""

    model = Friend
    fields = ("name", "place_name", "distance_m")
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MeetupGroup)
class MeetupGroupAdmin(DublinMapAdmin):
    list_display = ("name", "owner", "friend_count", "fairness_score", "updated_at")
    list_filter = ("owner",)
    search_fields = ("name", "owner__username")
    readonly_fields = ("fairness_score", "created_at", "updated_at")
    inlines = [FriendInline]
    fieldsets = [
        (None, {"fields": ["name", "owner", "search_radius_m"]}),
        (
            "Calculated by PostGIS",
            {
                "classes": ["collapse"],
                "description": "Filled in automatically from the friends' locations.",
                "fields": ["meeting_point", "hull", "fairness_score", "created_at", "updated_at"],
            },
        ),
    ]

    def get_queryset(self, request):
        # Count friends in the same query instead of one query per row.
        return super().get_queryset(request).select_related("owner").annotate(_friend_count=Count("friends"))

    @admin.display(description="friends", ordering="_friend_count")
    def friend_count(self, obj):
        return obj._friend_count


@admin.register(Friend)
class FriendAdmin(DublinMapAdmin):
    list_display = ("name", "group", "place_name", "distance_m")
    list_filter = ("group",)
    list_select_related = ("group",)
    search_fields = ("name", "place_name", "group__name")
    readonly_fields = ("distance_m", "created_at")
    fieldsets = [
        (None, {"fields": ["group", "name", "place_name", "location"]}),
        (
            "Calculated by PostGIS",
            {
                "classes": ["collapse"],
                "fields": ["line_to_meeting", "distance_m", "created_at"],
            },
        ),
    ]
