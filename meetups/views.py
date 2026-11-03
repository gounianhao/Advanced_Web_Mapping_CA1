"""
Page views (the "Controller" in MVC; Django calls this layer "views").

The templates in templates/ and meetups/templates/ are the "View" layer.
"""

from django.conf import settings
from django.db import connection
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.views.generic import TemplateView

from .models import MeetupGroup, Venue


class MapView(TemplateView):
    """The main page: a full-screen map with the group sidebar."""

    template_name = "meetups/map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        # Passed to the browser as JSON (see json_script in the template),
        # so the JavaScript never has settings or URLs hard-coded in it.
        context["map_config"] = {
            "center": list(settings.MAP_DEFAULT_CENTER),
            "zoom": settings.MAP_DEFAULT_ZOOM,
            "user": user.username if user.is_authenticated else None,
            "csrfToken": get_token(self.request),
            "urls": {
                "venues": reverse("api:venue-list"),
                "groups": reverse("api:group-list"),
                "friends": reverse("api:friend-list"),
                "geocode": reverse("api:geocode"),
            },
            "radius": {
                "min": MeetupGroup.MIN_RADIUS_M,
                "max": MeetupGroup.MAX_RADIUS_M,
                "default": MeetupGroup._meta.get_field("search_radius_m").default,
            },
            "maxFriends": MeetupGroup.MAX_FRIENDS,
        }
        context["venue_categories"] = Venue.Category.choices
        return context


def health(request):
    """Used by the Docker health checks: answers "ok" when Django and the database are working."""
    connection.ensure_connection()
    return HttpResponse("ok", content_type="text/plain")
