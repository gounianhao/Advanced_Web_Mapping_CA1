"""URL routes for the REST API (mounted at /api/)."""

from rest_framework import permissions, routers

from .api import VenueViewSet


class PublicAPIRootView(routers.APIRootView):
    """Meet Halfway REST API. Lists the available endpoints."""

    permission_classes = [permissions.AllowAny]


class Router(routers.DefaultRouter):
    APIRootView = PublicAPIRootView


app_name = "api"

router = Router()
router.register("venues", VenueViewSet, basename="venue")

urlpatterns = router.urls
