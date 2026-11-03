"""URL routes for the REST API (mounted at /api/)."""

from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, routers
from rest_framework.reverse import reverse

from .api import FriendViewSet, GeocodeView, MeetupGroupViewSet, VenueViewSet


@extend_schema(exclude=True)
class PublicAPIRootView(routers.APIRootView):
    """Meet Halfway REST API. Lists the available endpoints."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Endpoints that aren't viewsets, so the router doesn't list them itself.
        response.data["geocode"] = reverse("api:geocode", request=request)
        response.data["docs"] = reverse("api-docs", request=request)
        return response


class Router(routers.DefaultRouter):
    APIRootView = PublicAPIRootView


app_name = "api"

router = Router()
router.register("venues", VenueViewSet, basename="venue")
router.register("groups", MeetupGroupViewSet, basename="group")
router.register("friends", FriendViewSet, basename="friend")

urlpatterns = router.urls + [
    path("geocode/", GeocodeView.as_view(), name="geocode"),
]
