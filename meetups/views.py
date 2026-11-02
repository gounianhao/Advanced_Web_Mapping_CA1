"""
Page views (the "Controller" in MVC; Django calls this layer "views").

The templates in templates/ and meetups/templates/ are the "View" layer.
"""

from django.conf import settings
from django.views.generic import TemplateView


class MapView(TemplateView):
    """The main page: a full-screen map with the group sidebar."""

    template_name = "meetups/map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Passed to the browser as JSON (see json_script in the template),
        # so the JavaScript never has settings hard-coded in it.
        context["map_config"] = {
            "center": list(settings.MAP_DEFAULT_CENTER),
            "zoom": settings.MAP_DEFAULT_ZOOM,
        }
        return context
